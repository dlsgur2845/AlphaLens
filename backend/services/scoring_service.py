"""멀티팩터 스코어링 서비스 - 7팩터 모델.

팩터 구성:
  Tech 23% + Fund 19% + Signal 19% + Macro 14% + Risk 15% + Related 5% + News 5%
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)
import pandas as pd

from backend.models.schemas import ScoreBreakdown, ScoringResult
from backend.services.cache_service import cache
from backend.services.news_service import get_stock_news
from backend.services.related_company_service import find_related_companies
from backend.services.stock_service import (
    get_price_history,
    get_stock_detail,
    get_stock_name,
)
from backend.utils.sentiment import sentiment_to_score
from backend.utils.technical import calc_technical_score
from backend.services.signal_service import calc_signal_score
from backend.services.macro_service import get_macro_score
from backend.services.risk_service import calc_risk_score

try:
    from backend.services.credit_service import get_credit_balance
except ImportError:
    get_credit_balance = None

# 7팩터 가중치
W_TECHNICAL = 0.23
W_FUNDAMENTAL = 0.19
W_SIGNAL = 0.19
W_MACRO = 0.14
W_RISK = 0.15
W_RELATED = 0.05
W_NEWS = 0.05


# ── 섹터별 밸류에이션 기준 ──

SECTOR_PER_STANDARDS = {
    "반도체": {"low": 8, "mid": 15, "high": 25},
    "2차전지": {"low": 15, "mid": 30, "high": 50},
    "바이오": {"low": 20, "mid": 40, "high": 80},
    "제약": {"low": 15, "mid": 25, "high": 40},
    "은행": {"low": 4, "mid": 7, "high": 12},
    "금융": {"low": 5, "mid": 8, "high": 15},
    "유틸리티": {"low": 6, "mid": 10, "high": 18},
    "통신": {"low": 8, "mid": 12, "high": 20},
    "IT": {"low": 12, "mid": 20, "high": 35},
    "게임": {"low": 10, "mid": 18, "high": 30},
    "자동차": {"low": 5, "mid": 10, "high": 18},
    "화학": {"low": 6, "mid": 12, "high": 20},
    "철강": {"low": 4, "mid": 8, "high": 15},
    "default": {"low": 8, "mid": 15, "high": 30},
}


def _get_per_standard(sector: str | None) -> dict:
    if not sector:
        return SECTOR_PER_STANDARDS["default"]
    for key, std in SECTOR_PER_STANDARDS.items():
        if key in sector:
            return std
    return SECTOR_PER_STANDARDS["default"]


def _signal_label(score: float) -> str:
    """점수를 7단계 시그널 라벨로 변환."""
    if score >= 80:
        return "강력매수"
    elif score >= 65:
        return "매수"
    elif score >= 55:
        return "관망(매수우위)"
    elif score >= 45:
        return "중립"
    elif score >= 35:
        return "관망(매도우위)"
    elif score >= 20:
        return "매도"
    else:
        return "강력매도"


def _calc_fundamental_score(detail, sector: str | None = None) -> tuple[float, dict]:
    """펀더멘탈 점수 계산 (PER, PBR, ROE 기반 + 섹터 보정)."""
    details: dict = {}
    score = 50.0

    if not detail:
        return score, details

    per = detail.per
    pbr = detail.pbr
    roe = detail.roe

    # 섹터별 PER 기준
    per_std = _get_per_standard(sector)

    if per is not None:
        details["per"] = per
        if per < 0:
            score -= 12
        elif per == 0:
            pass
        elif per < per_std["low"]:
            score += 15  # 저평가
        elif per < per_std["mid"]:
            score += 8   # 적정
        elif per < per_std["high"]:
            pass          # 보통
        elif per < per_std["high"] * 1.5:
            score -= 5   # 고평가
        else:
            score -= 10  # 심한 고평가

    if pbr is not None:
        details["pbr"] = pbr
        if pbr < 0:
            score -= 8
        elif pbr < 0.7:
            score += 12
        elif pbr < 1.0:
            score += 8
        elif pbr < 1.5:
            score += 3
        elif pbr < 3.0:
            score -= 3
        else:
            score -= 8

    # ROE 활용 (스키마에 필드 존재)
    if roe is not None:
        details["roe"] = roe
        if roe > 20:
            score += 10  # 우수한 자본 수익률
        elif roe > 15:
            score += 7
        elif roe > 10:
            score += 4
        elif roe > 5:
            score += 1
        elif roe < 0:
            score -= 8  # 적자
        elif roe < 3:
            score -= 3  # 저조

    details["sector_standard"] = per_std.get("mid")

    return float(np.clip(score, 0, 100)), details


async def _calc_related_score(code: str) -> tuple[float, dict]:
    """관련기업 모멘텀 점수 (민감도 축소: ×0.5, ±3 cap → ×5→×0.5)."""
    related = await find_related_companies(code, max_depth=1, max_companies=10)
    details: dict = {"related_count": len(related), "companies": []}

    if not related:
        return 50.0, details

    changes = []
    for comp in related:
        if comp.change_pct is not None:
            changes.append(comp.change_pct)
            details["companies"].append({
                "name": comp.name,
                "change_pct": comp.change_pct,
            })

    if not changes:
        return 50.0, details

    avg_change = sum(changes) / len(changes)
    details["avg_change_pct"] = round(avg_change, 2)

    # 민감도 ×0.5 (기존 ×5에서 대폭 축소) + ±3점 캡
    raw_adj = avg_change * 0.5
    capped_adj = float(np.clip(raw_adj, -3, 3))
    score = 50.0 + capped_adj
    return float(np.clip(score, 0, 100)), details


async def calculate_score(code: str) -> ScoringResult:
    """종합 스코어링 계산 - 6팩터 모델."""
    cache_key = f"scoring:{code}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # 이름 조회
    name = await get_stock_name(code)

    # 병렬 로드 (개별 타임아웃 + return_exceptions=True)
    async def _with_timeout(coro, timeout_sec: float):
        return await asyncio.wait_for(coro, timeout=timeout_sec)

    # 신용잔고 데이터 병렬 조회 (선택적)
    credit_coro = (
        _with_timeout(get_credit_balance(code), 10.0)
        if get_credit_balance
        else asyncio.sleep(0)
    )

    results = await asyncio.gather(
        _with_timeout(get_price_history(code, days=200), 15.0),
        _with_timeout(get_stock_detail(code), 10.0),
        _with_timeout(get_stock_news(code, stock_name=name, max_articles=15), 10.0),
        _with_timeout(_calc_related_score(code), 20.0),
        credit_coro,
        return_exceptions=True,
    )

    price_history = None if isinstance(results[0], BaseException) else results[0]
    detail = None if isinstance(results[1], BaseException) else results[1]

    # 신용잔고 데이터
    credit_data = None
    if get_credit_balance and not isinstance(results[4], BaseException):
        credit_data = results[4]

    # 섹터 정보
    sector = detail.sector if detail else None

    # 펀더멘탈: 섹터 보정 적용
    fund_score, fund_details = _calc_fundamental_score(detail, sector)

    all_details: dict = {}

    # closes/volumes 준비
    closes = pd.Series(dtype=float)
    volumes = pd.Series(dtype=float)
    if price_history and len(price_history.prices) >= 5:
        closes = pd.Series([p.close for p in price_history.prices], dtype=float)
        volumes = pd.Series([p.volume for p in price_history.prices], dtype=float)

    # 1) 기술적 분석 점수 (30%)
    if len(closes) >= 5:
        tech_score, tech_details = calc_technical_score(closes, volumes)
        all_details["technical"] = tech_details
    else:
        tech_score = 50.0
        all_details["technical"] = {"error": "insufficient_data"}

    # 시간외/NXT 가격 보조 신호 (보정폭 축소: ×0.5, ±3 제한)
    if detail and detail.over_market and detail.price > 0:
        nxt_diff_pct = ((detail.over_market.price - detail.price) / detail.price) * 100
        all_details["over_market"] = {
            "krx_price": detail.price,
            "nxt_price": detail.over_market.price,
            "diff_pct": round(nxt_diff_pct, 2),
            "session": detail.over_market.session_type,
        }
        nxt_adj = float(np.clip(nxt_diff_pct * 0.5, -3, 3))
        tech_score = float(np.clip(tech_score + nxt_adj, 0, 100))

    # 2) 뉴스 감성 점수 (참고)
    if isinstance(results[2], BaseException):
        news_score = 50.0
        all_details["news"] = {"error": "fetch_failed"}
    else:
        news_result = results[2]
        news_score = sentiment_to_score(news_result.overall_sentiment)
        all_details["news"] = {
            "overall_sentiment": news_result.overall_sentiment,
            "positive": news_result.positive_count,
            "negative": news_result.negative_count,
            "neutral": news_result.neutral_count,
            "total_articles": len(news_result.articles),
        }

    all_details["fundamental"] = fund_details

    # 3) 관련기업 점수 (5%)
    if isinstance(results[3], BaseException):
        related_score = 50.0
        all_details["related"] = {"related_count": 0, "companies": [], "error": "fetch_failed"}
    else:
        related_score, related_details = results[3]
        all_details["related"] = related_details

    # 신용잔고 상세
    if credit_data:
        all_details["credit"] = credit_data

    # 4) 시그널 점수 (20%)
    signal_score = 50.0
    try:
        if len(closes) >= 20:
            signal_result = calc_signal_score(closes, volumes, credit_data=credit_data)
            signal_score = signal_result.score
            all_details["signal"] = {
                "score": signal_result.score,
                "action_label": signal_result.action_label,
                "regime": signal_result.breakdown.regime,
                "buy_signals": signal_result.buy_signals,
                "sell_signals": signal_result.sell_signals,
                "breakdown": {
                    "momentum": signal_result.breakdown.momentum,
                    "mean_reversion": signal_result.breakdown.mean_reversion,
                    "breakout": signal_result.breakdown.breakout,
                },
            }
    except Exception as e:
        logger.warning("시그널 점수 계산 실패 (%s): %s", code, e)
        all_details["signal"] = {"error": "calculation_failed"}

    # 5) 매크로 점수 (15%)
    macro_score = 50.0
    try:
        macro_result = await asyncio.wait_for(get_macro_score(sector), timeout=20.0)
        macro_score = macro_result.score
        all_details["macro"] = {
            "score": macro_result.score,
            "breakdown": {
                "us_market": macro_result.breakdown.us_market,
                "fx": macro_result.breakdown.fx,
                "rates": macro_result.breakdown.rates,
                "commodities": macro_result.breakdown.commodities,
                "china": macro_result.breakdown.china,
            },
            "details": macro_result.details,
        }
    except asyncio.TimeoutError:
        logger.warning("매크로 점수 타임아웃 (%s)", code)
        all_details["macro"] = {"error": "timeout"}
    except Exception as e:
        logger.warning("매크로 점수 계산 실패 (%s): %s %s", code, type(e).__name__, e)
        all_details["macro"] = {"error": "calculation_failed"}

    # 6) 리스크 점수 (10%)
    risk_score = 50.0
    risk_grade = "C"
    try:
        if len(closes) >= 20:
            risk_result = calc_risk_score(closes, volumes, credit_data=credit_data)
            risk_score = risk_result.score
            risk_grade = risk_result.grade
            all_details["risk"] = {
                "score": risk_result.score,
                "grade": risk_result.grade,
                "position_size_pct": risk_result.position_size_pct,
                "atr": risk_result.atr,
                "breakdown": {
                    "volatility": risk_result.breakdown.volatility,
                    "mdd": risk_result.breakdown.mdd,
                    "var_cvar": risk_result.breakdown.var_cvar,
                    "liquidity": risk_result.breakdown.liquidity,
                },
            }
    except Exception as e:
        logger.warning("리스크 점수 계산 실패 (%s): %s", code, e)
        all_details["risk"] = {"error": "calculation_failed"}

    # ── 종합 점수 계산 (6팩터) ──
    total = (
        tech_score * W_TECHNICAL
        + fund_score * W_FUNDAMENTAL
        + signal_score * W_SIGNAL
        + macro_score * W_MACRO
        + risk_score * W_RISK
        + related_score * W_RELATED
        + news_score * W_NEWS
    )

    # --- 다중공선성 보정: Technical ↔ Signal 상관 할인 ---
    # MA/거래량 등 동일 지표 이중 반영 비율 약 30% 추정 → 작은 쪽 편차의 15% 할인
    tech_dev = tech_score - 50  # 중립점 대비 편차
    sig_dev = signal_score - 50
    if tech_dev * sig_dev > 0:  # 같은 방향으로 편향
        overlap = min(abs(tech_dev), abs(sig_dev)) * 0.15
        if tech_dev > 0:
            total -= overlap  # 과대평가 보정
        else:
            total += overlap  # 과소평가 보정

    # Risk veto: 리스크 등급 D/E(점수 25 미만)인 종목은 종합점수 상한 제한
    if risk_score < 25:
        total = min(total, 45)  # 최대 "관망(매도우위)"

    total = float(np.clip(total, 0, 100))

    # 라벨 통일: 종합점수 기반 7단계 라벨 (signal, action_label 모두 동일 기준)
    unified_label = _signal_label(total)

    result = ScoringResult(
        code=code,
        name=name,
        total_score=round(total, 1),
        signal=unified_label,
        breakdown=ScoreBreakdown(
            technical=round(tech_score, 1),
            news_sentiment=round(news_score, 1),
            fundamental=round(fund_score, 1),
            related_momentum=round(related_score, 1),
            macro=round(macro_score, 1),
            signal=round(signal_score, 1),
            risk=round(risk_score, 1),
        ),
        details=all_details,
        updated_at=datetime.now().isoformat(),
        action_label=unified_label,
        risk_grade=risk_grade,
        macro_score=round(macro_score, 1),
    )

    cache.set(cache_key, result, ttl=300)
    return result
