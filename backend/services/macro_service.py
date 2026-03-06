"""글로벌 매크로 스코어 서비스."""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime

import numpy as np

from backend.models.schemas import MacroBreakdown, MacroScore
from backend.services.cache_service import cache
from backend.services.geopolitical_service import get_geopolitical_risk_score

logger = logging.getLogger(__name__)

# yfinance 티커 매핑
MACRO_TICKERS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "vix": "^VIX",
    "usdkrw": "KRW=X",
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
    "wti": "CL=F",
    "gold": "GC=F",
    "copper": "HG=F",
    "shanghai": "000001.SS",
}

# 섹터별 매크로 민감도 계수
SECTOR_MACRO_BETA = {
    "반도체": 1.3, "2차전지": 1.2, "자동차": 1.1,
    "조선": 1.2, "해운": 1.2, "화학": 1.2, "철강": 1.1, "정유": 1.3,
    "은행": 1.0, "금융": 1.0, "보험": 1.0,
    "IT": 1.0, "소프트웨어": 1.0, "게임": 0.9,
    "음식료": 0.5, "유틸리티": 0.4, "통신": 0.4,
    "제약": 0.6, "바이오": 0.6, "유통": 0.6,
    "default": 0.8,
}


async def _fetch_macro_data() -> dict:
    """yfinance에서 매크로 데이터 수집 (blocking IO를 thread에서 실행)."""
    def _fetch():
        try:
            import yfinance as yf
            data = {}
            for name, ticker in MACRO_TICKERS.items():
                try:
                    t = yf.Ticker(ticker)
                    hist = t.history(period="1mo")
                    if len(hist) >= 2:
                        latest = hist["Close"].iloc[-1]
                        prev = hist["Close"].iloc[-2]
                        chg_pct = ((latest - prev) / prev) * 100 if prev > 0 else 0.0

                        # 5일 추세 추가
                        chg_5d = 0.0
                        if len(hist) >= 6:
                            prev_5d = hist["Close"].iloc[-6]
                            chg_5d = ((latest - prev_5d) / prev_5d) * 100 if prev_5d > 0 else 0.0

                        data[name] = {
                            "price": round(latest, 2),
                            "change_pct": round(chg_pct, 2),
                            "change_5d": round(chg_5d, 2),
                        }
                    elif len(hist) >= 1:
                        data[name] = {
                            "price": round(hist["Close"].iloc[-1], 2),
                            "change_pct": 0.0,
                            "change_5d": 0.0,
                        }
                except Exception:
                    logger.debug("Failed to fetch %s", name)
            return data
        except ImportError:
            logger.warning("yfinance not installed, using neutral macro score")
            return {}

    return await asyncio.to_thread(_fetch)


def _us_market_signal(data: dict) -> float:
    """미국 시장 신호 (최대 ±15점)."""
    score = 0.0
    sp500 = data.get("sp500", {}).get("change_pct", 0)
    nasdaq = data.get("nasdaq", {}).get("change_pct", 0)
    vix = data.get("vix", {}).get("price", 20)

    if sp500 > 1.0: score += 5
    elif sp500 > 0.3: score += 3
    elif sp500 < -1.0: score -= 5
    elif sp500 < -0.3: score -= 3

    if nasdaq > 1.5: score += 4
    elif nasdaq > 0.5: score += 2
    elif nasdaq < -1.5: score -= 4
    elif nasdaq < -0.5: score -= 2

    if vix > 35: score -= 5
    elif vix > 25: score -= 3
    elif vix < 15: score += 3

    # 5일 추세 보너스/페널티 (최대 ±3)
    sp_5d = data.get("sp500", {}).get("change_5d", 0)
    nas_5d = data.get("nasdaq", {}).get("change_5d", 0)
    trend_bonus = float(np.clip((sp_5d + nas_5d) * 0.3, -3, 3))
    score += trend_bonus

    return float(np.clip(score, -15, 15))


def _fx_signal(data: dict) -> float:
    """환율 신호 (최대 ±10점)."""
    score = 0.0
    usdkrw_chg = data.get("usdkrw", {}).get("change_pct", 0)
    dxy_chg = data.get("dxy", {}).get("change_pct", 0)

    if usdkrw_chg < -0.5: score += 5
    elif usdkrw_chg < -0.2: score += 3
    elif usdkrw_chg > 0.5: score -= 5
    elif usdkrw_chg > 0.2: score -= 3

    if dxy_chg > 0.5: score -= 3
    elif dxy_chg < -0.5: score += 3

    # 5일간 원화 약세/강세 추세 반영 (최대 ±2)
    krw_5d = data.get("usdkrw", {}).get("change_5d", 0)
    fx_trend = float(np.clip(-krw_5d * 0.2, -2, 2))
    score += fx_trend

    return float(np.clip(score, -10, 10))


def _rate_signal(data: dict) -> float:
    """금리 신호 (최대 ±10점). basis point 기준 변동 반영."""
    score = 0.0
    us10y = data.get("us10y", {}).get("price", 4.0)
    us10y_chg = data.get("us10y", {}).get("change_pct", 0)

    if us10y > 5.0: score -= 5
    elif us10y > 4.5: score -= 2
    elif us10y < 3.0: score += 3

    # basis point 기준으로 변경 (금리 변동률이 아닌 절대값 변동)
    # yield 기준 변동 (1% change_pct at 4.5% = 4.5bp)
    if us10y_chg > 0:  # 금리 상승
        bp_change = us10y * us10y_chg / 100
        if bp_change > 0.08: score -= 3  # 8bp 이상 급등
        elif bp_change > 0.04: score -= 1
    elif us10y_chg < 0:  # 금리 하락
        bp_change = abs(us10y * us10y_chg / 100)
        if bp_change > 0.08: score += 3
        elif bp_change > 0.04: score += 1

    # 금리 5일 변동 방향성 반영 (최대 ±2)
    rate_5d = data.get("us10y", {}).get("change_5d", 0)
    rate_trend = float(np.clip(-rate_5d * 0.5, -2, 2))
    score += rate_trend

    return float(np.clip(score, -10, 10))


def _commodity_signal(data: dict) -> float:
    """원자재 신호 (최대 ±8점)."""
    score = 0.0
    copper_chg = data.get("copper", {}).get("change_pct", 0)
    gold_chg = data.get("gold", {}).get("change_pct", 0)

    if copper_chg > 2.0: score += 3
    elif copper_chg < -2.0: score -= 3

    if gold_chg > 2.0: score -= 2
    elif gold_chg < -1.0: score += 2

    # WTI 원유: 유가 급등 → 비용 압박 → 음수
    wti_chg = data.get("wti", {}).get("change_pct", 0)
    if abs(wti_chg) > 3:
        score += float(np.clip(-wti_chg * 0.3, -2, 2))

    # 구리 5일 추세 (경기 선행지표, 최대 ±2)
    cu_5d = data.get("copper", {}).get("change_5d", 0)
    commodity_trend = float(np.clip(cu_5d * 0.2, -2, 2))
    score += commodity_trend

    return float(np.clip(score, -8, 8))


def _china_signal(data: dict) -> float:
    """중국 신호 (최대 ±7점)."""
    score = 0.0
    shanghai_chg = data.get("shanghai", {}).get("change_pct", 0)

    if shanghai_chg > 1.0: score += 4
    elif shanghai_chg > 0.3: score += 2
    elif shanghai_chg < -1.0: score -= 4
    elif shanghai_chg < -0.3: score -= 2

    return float(np.clip(score, -7, 7))


def _rate_spread_signal(data: dict) -> float:
    """한미 금리차 프록시: US10Y 수준에 따른 한국 시장 영향 (최대 ±8점).

    US10Y 고금리 → 달러 강세 → 외국인 자금 유출 → 한국 증시 부정적
    US10Y 저금리 → 달러 약세 → 외국인 자금 유입 → 한국 증시 긍정적
    """
    us10y = data.get("us10y", {}).get("price", 0)
    us10y_5d = data.get("us10y", {}).get("change_5d", 0)
    usdkrw = data.get("usdkrw", {}).get("price", 0)

    score = 0.0

    # 데이터 없으면 중립
    if us10y == 0:
        return 0.0

    # 미국 금리 수준 영향 (4.5% 기준)
    if us10y > 5.0:
        score -= 5  # 고금리 → 자금 유출 압력
    elif us10y > 4.5:
        score -= 3
    elif us10y < 3.5:
        score += 3  # 저금리 → 자금 유입 기대
    elif us10y < 4.0:
        score += 1

    # 금리+환율 동반 악화 (이중 압박)
    if us10y > 4.5 and usdkrw > 1350:
        score -= 3  # 금리↑+원화약세 동반 → 외국인 매도 압력

    # 5일 금리 급변동 (20bp 이상)
    if abs(us10y_5d) > 20:
        score += float(np.clip(-us10y_5d * 0.05, -2, 2))

    return float(np.clip(score, -8, 8))


def get_sector_beta(sector: str | None) -> float:
    """섹터별 매크로 민감도 계수 반환."""
    if not sector:
        return SECTOR_MACRO_BETA["default"]
    for key, beta in SECTOR_MACRO_BETA.items():
        if key in sector:
            return beta
    return SECTOR_MACRO_BETA["default"]


async def get_macro_score(sector: str | None = None) -> MacroScore:
    """매크로 스코어 계산 (전역 캐시 적용)."""
    cache_key = "macro:global"
    cached = cache.get(cache_key)

    if cached is None:
        # 데이터 수집
        data = await _fetch_macro_data()

        if not data:
            return MacroScore(
                score=50.0,
                breakdown=MacroBreakdown(),
                details={"status": "data_unavailable"},
                updated_at=datetime.now().isoformat(),
            )

        # 각 신호 계산
        us = _us_market_signal(data)
        fx = _fx_signal(data)
        rates = _rate_signal(data)
        rate_spread = _rate_spread_signal(data)
        commodities = _commodity_signal(data)
        china = _china_signal(data)

        # 지정학 리스크 → event_risk 반영 (타임아웃 5초 - 매크로 계산 지연 방지)
        try:
            geo_score = await asyncio.wait_for(get_geopolitical_risk_score(), timeout=5.0)
            # 30 이하 = 안정(+보너스), 30~60 = 중립, 60+ = 위험(감점)
            event_risk = float(np.clip(-(geo_score - 30) * 0.2, -10, 3))
        except (asyncio.TimeoutError, Exception):
            logger.debug("Geopolitical risk unavailable, using neutral")
            geo_score = 20.0
            event_risk = 0.0

        base_score = 50.0 + us + fx + rates + rate_spread + commodities + china + event_risk
        base_score = float(np.clip(base_score, 0, 100))

        cached = MacroScore(
            score=base_score,
            breakdown=MacroBreakdown(
                us_market=us, fx=fx, rates=rates, rate_spread=rate_spread,
                commodities=commodities, china=china, event_risk=event_risk,
            ),
            details={**data, "rate_spread": round(rate_spread, 2)},
            updated_at=datetime.now().isoformat(),
        )
        cache.set(cache_key, cached, ttl=600)

    # 섹터 베타 보정 적용
    beta = get_sector_beta(sector)
    if beta != 1.0 and cached.score != 50.0:
        adjusted = 50.0 + (cached.score - 50.0) * beta
        adjusted = float(np.clip(adjusted, 0, 100))
        return MacroScore(
            score=adjusted,
            breakdown=cached.breakdown,
            details={**cached.details, "sector_beta": beta, "base_score": cached.score},
            updated_at=cached.updated_at,
        )

    return cached
