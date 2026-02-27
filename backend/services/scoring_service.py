"""멀티팩터 스코어링 서비스."""

from __future__ import annotations

import asyncio
from datetime import datetime

import numpy as np
import pandas as pd

from backend.models.schemas import ScoreBreakdown, ScoringResult
from backend.services.cache_service import cache
from backend.services.news_service import get_stock_news
from backend.services.related_company_service import find_related_companies
from backend.services.stock_service import (
    _fetch_krx_stock_list,
    get_price_history,
    get_stock_detail,
)
from backend.utils.sentiment import sentiment_to_score
from backend.utils.technical import calc_technical_score

# 가중치 (뉴스 감성은 참고 표시만, 점수 미반영)
W_TECHNICAL = 0.50
W_NEWS = 0.00
W_FUNDAMENTAL = 0.30
W_RELATED = 0.20


def _signal_label(score: float) -> str:
    """점수를 시그널 라벨로 변환."""
    if score >= 70:
        return "강한상승"
    elif score >= 55:
        return "상승"
    elif score >= 45:
        return "중립"
    elif score >= 30:
        return "하락"
    else:
        return "강한하락"


def _calc_fundamental_score(detail) -> tuple[float, dict]:
    """펀더멘탈 점수 계산 (PER, PBR 기반). 이미 조회된 detail을 받음."""
    details: dict = {}
    score = 50.0

    if not detail:
        return score, details

    per = detail.per
    pbr = detail.pbr

    if per is not None:
        details["per"] = per
        if per < 0:
            score -= 15
        elif per == 0:
            pass
        elif per < 10:
            score += 15
        elif per < 15:
            score += 8
        elif per < 25:
            pass
        elif per < 40:
            score -= 5
        else:
            score -= 10

    if pbr is not None:
        details["pbr"] = pbr
        if pbr < 0:
            score -= 10
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

    return float(np.clip(score, 0, 100)), details


async def _calc_related_score(code: str) -> tuple[float, dict]:
    """관련기업 모멘텀 점수."""
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

    score = 50.0 + (avg_change * 5)
    return float(np.clip(score, 0, 100)), details


async def calculate_score(code: str) -> ScoringResult:
    """종합 스코어링 계산."""
    cache_key = f"scoring:{code}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # 이름 조회
    stocks = await _fetch_krx_stock_list()
    name = code
    for s in stocks:
        if s["code"] == code:
            name = s["name"]
            break

    # 병렬 로드 (detail은 1번만 호출, fundamental은 detail 결과로 계산)
    (
        price_history,
        detail,
        news_result,
        (related_score, related_details),
    ) = await asyncio.gather(
        get_price_history(code, days=120),
        get_stock_detail(code),
        get_stock_news(code, stock_name=name, max_articles=15),
        _calc_related_score(code),
    )

    # 펀더멘탈: 이미 조회된 detail로 즉시 계산 (추가 API 호출 없음)
    fund_score, fund_details = _calc_fundamental_score(detail)

    all_details: dict = {}

    # 1) 기술적 분석 점수 (50%)
    if price_history and len(price_history.prices) >= 5:
        closes = pd.Series([p.close for p in price_history.prices], dtype=float)
        volumes = pd.Series([p.volume for p in price_history.prices], dtype=float)
        tech_score, tech_details = calc_technical_score(closes, volumes)
        all_details["technical"] = tech_details
    else:
        tech_score = 50.0
        all_details["technical"] = {"error": "insufficient_data"}

    # 시간외/NXT 가격 보조 신호
    if detail and detail.over_market and detail.price > 0:
        nxt_diff_pct = ((detail.over_market.price - detail.price) / detail.price) * 100
        all_details["over_market"] = {
            "krx_price": detail.price,
            "nxt_price": detail.over_market.price,
            "diff_pct": round(nxt_diff_pct, 2),
            "session": detail.over_market.session_type,
        }
        # NXT가 KRX보다 높으면 상승 신호, 낮으면 하락 신호 (기술적 점수 보정)
        tech_score = float(np.clip(tech_score + nxt_diff_pct * 2, 0, 100))

    # 뉴스 감성 점수 변환
    news_score = sentiment_to_score(news_result.overall_sentiment)
    all_details["news"] = {
        "overall_sentiment": news_result.overall_sentiment,
        "positive": news_result.positive_count,
        "negative": news_result.negative_count,
        "neutral": news_result.neutral_count,
        "total_articles": len(news_result.articles),
    }
    all_details["fundamental"] = fund_details
    all_details["related"] = related_details

    # 종합 점수
    total = (
        tech_score * W_TECHNICAL
        + news_score * W_NEWS
        + fund_score * W_FUNDAMENTAL
        + related_score * W_RELATED
    )
    total = float(np.clip(total, 0, 100))

    result = ScoringResult(
        code=code,
        name=name,
        total_score=round(total, 1),
        signal=_signal_label(total),
        breakdown=ScoreBreakdown(
            technical=round(tech_score, 1),
            news_sentiment=round(news_score, 1),
            fundamental=round(fund_score, 1),
            related_momentum=round(related_score, 1),
        ),
        details=all_details,
        updated_at=datetime.now().isoformat(),
    )

    cache.set(cache_key, result, ttl=300)
    return result
