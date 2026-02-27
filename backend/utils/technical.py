"""기술적 지표 계산 유틸리티."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_moving_averages(closes: pd.Series) -> dict:
    """5일, 20일, 60일 이동평균 및 골든/데드크로스 판단."""
    ma5 = closes.rolling(5).mean()
    ma20 = closes.rolling(20).mean()
    ma60 = closes.rolling(60).mean()

    latest = closes.iloc[-1]
    result = {
        "ma5": round(ma5.iloc[-1], 2) if len(ma5.dropna()) else None,
        "ma20": round(ma20.iloc[-1], 2) if len(ma20.dropna()) else None,
        "ma60": round(ma60.iloc[-1], 2) if len(ma60.dropna()) else None,
        "above_ma5": bool(latest > ma5.iloc[-1]) if ma5.iloc[-1] else None,
        "above_ma20": bool(latest > ma20.iloc[-1]) if ma20.iloc[-1] else None,
        "above_ma60": bool(latest > ma60.iloc[-1]) if ma60.iloc[-1] else None,
    }

    # 골든크로스: 단기 MA가 장기 MA를 상향 돌파
    if len(ma5.dropna()) >= 2 and len(ma20.dropna()) >= 2:
        prev_diff = ma5.iloc[-2] - ma20.iloc[-2]
        curr_diff = ma5.iloc[-1] - ma20.iloc[-1]
        result["golden_cross"] = bool(prev_diff < 0 and curr_diff > 0)
        result["dead_cross"] = bool(prev_diff > 0 and curr_diff < 0)
    else:
        result["golden_cross"] = False
        result["dead_cross"] = False

    return result


def calc_rsi(closes: pd.Series, period: int = 14) -> float | None:
    """RSI (Relative Strength Index) 계산."""
    if len(closes) < period + 1:
        return None

    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta.where(delta < 0, 0.0))

    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calc_macd(closes: pd.Series) -> dict | None:
    """MACD (12, 26, 9) 계산."""
    if len(closes) < 26:
        return None

    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    return {
        "macd": round(macd_line.iloc[-1], 2),
        "signal": round(signal_line.iloc[-1], 2),
        "histogram": round(histogram.iloc[-1], 2),
        "bullish": bool(histogram.iloc[-1] > 0),
    }


def calc_volume_trend(volumes: pd.Series, period: int = 20) -> dict | None:
    """거래량 추세 분석."""
    if len(volumes) < period:
        return None

    avg_volume = volumes.rolling(period).mean().iloc[-1]
    latest_volume = volumes.iloc[-1]
    ratio = latest_volume / avg_volume if avg_volume > 0 else 1.0

    return {
        "avg_volume": int(avg_volume),
        "latest_volume": int(latest_volume),
        "volume_ratio": round(ratio, 2),
        "high_volume": bool(ratio > 1.5),
    }


def calc_technical_score(closes: pd.Series, volumes: pd.Series) -> tuple[float, dict]:
    """기술적 분석 종합 점수 (0~100)를 반환.

    Returns:
        (score, details) 튜플
    """
    score = 50.0  # 기본 중립
    details: dict = {}

    # 이동평균 (최대 ±20점)
    ma = calc_moving_averages(closes)
    details["moving_averages"] = ma
    ma_score = 0.0
    if ma.get("above_ma5"):
        ma_score += 5
    elif ma.get("above_ma5") is False:
        ma_score -= 5
    if ma.get("above_ma20"):
        ma_score += 7
    elif ma.get("above_ma20") is False:
        ma_score -= 7
    if ma.get("above_ma60"):
        ma_score += 8
    elif ma.get("above_ma60") is False:
        ma_score -= 8
    if ma.get("golden_cross"):
        ma_score += 10
    if ma.get("dead_cross"):
        ma_score -= 10
    score += np.clip(ma_score, -20, 20)

    # RSI (최대 ±15점)
    rsi = calc_rsi(closes)
    details["rsi"] = rsi
    if rsi is not None:
        if rsi < 30:
            score += 15  # 과매도 → 반등 가능성
        elif rsi < 40:
            score += 8
        elif rsi > 70:
            score -= 15  # 과매수 → 조정 가능성
        elif rsi > 60:
            score -= 5

    # MACD (최대 ±10점)
    macd = calc_macd(closes)
    details["macd"] = macd
    if macd:
        if macd["bullish"]:
            score += 10
        else:
            score -= 10

    # 거래량 (최대 ±5점)
    vol = calc_volume_trend(volumes)
    details["volume_trend"] = vol
    if vol:
        price_up = closes.iloc[-1] > closes.iloc[-2] if len(closes) >= 2 else False
        if vol["high_volume"] and price_up:
            score += 5  # 거래량 동반 상승
        elif vol["high_volume"] and not price_up:
            score -= 5  # 거래량 동반 하락

    return float(np.clip(score, 0, 100)), details
