"""기술적 지표 계산 유틸리티."""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_moving_averages(closes: pd.Series) -> dict:
    """5일, 20일, 60일, 120일, 200일 이동평균 및 골든/데드크로스 판단."""
    ma5 = closes.rolling(5).mean()
    ma20 = closes.rolling(20).mean()
    ma60 = closes.rolling(60).mean()
    ma120 = closes.rolling(120).mean()
    ma200 = closes.rolling(200).mean()

    latest = closes.iloc[-1]
    result = {
        "ma5": round(ma5.iloc[-1], 2) if len(ma5.dropna()) else None,
        "ma20": round(ma20.iloc[-1], 2) if len(ma20.dropna()) else None,
        "ma60": round(ma60.iloc[-1], 2) if len(ma60.dropna()) else None,
        "ma120": round(ma120.iloc[-1], 2) if len(ma120.dropna()) else None,
        "ma200": round(ma200.iloc[-1], 2) if len(ma200.dropna()) else None,
        "above_ma5": bool(latest > ma5.iloc[-1]) if ma5.iloc[-1] else None,
        "above_ma20": bool(latest > ma20.iloc[-1]) if ma20.iloc[-1] else None,
        "above_ma60": bool(latest > ma60.iloc[-1]) if ma60.iloc[-1] else None,
        "above_ma120": bool(latest > ma120.iloc[-1]) if len(ma120.dropna()) else None,
        "above_ma200": bool(latest > ma200.iloc[-1]) if len(ma200.dropna()) else None,
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

    # MA 정배열/역배열 판단
    ma_values = []
    for ma_series, period in [(ma5, 5), (ma20, 20), (ma60, 60)]:
        if len(ma_series.dropna()):
            ma_values.append((period, ma_series.iloc[-1]))
    if len(ma_values) >= 3:
        # 정배열: MA5 > MA20 > MA60
        result["ma_aligned_bull"] = all(
            ma_values[i][1] > ma_values[i + 1][1]
            for i in range(len(ma_values) - 1)
        )
        # 역배열: MA5 < MA20 < MA60
        result["ma_aligned_bear"] = all(
            ma_values[i][1] < ma_values[i + 1][1]
            for i in range(len(ma_values) - 1)
        )
    else:
        result["ma_aligned_bull"] = False
        result["ma_aligned_bear"] = False

    return result


def calc_rsi(closes: pd.Series, period: int = 14) -> float | None:
    """RSI (Relative Strength Index) 계산 - Wilder's smoothing (SMA seed 방식)."""
    if len(closes) < period + 1:
        return None

    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    # 첫 period 구간은 SMA로 계산 (Wilder 표준)
    avg_gain = gain.copy()
    avg_loss = loss.copy()

    avg_gain.iloc[:period] = float('nan')
    avg_loss.iloc[:period] = float('nan')

    # SMA seed
    avg_gain.iloc[period] = gain.iloc[1:period + 1].mean()
    avg_loss.iloc[period] = loss.iloc[1:period + 1].mean()

    # Wilder smoothing: avg = (prev_avg * (period-1) + current) / period
    for i in range(period + 1, len(closes)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    last_rsi = rsi.iloc[-1]
    if pd.isna(last_rsi):
        return None
    return round(float(last_rsi), 2)


def calc_macd(closes: pd.Series) -> dict | None:
    """MACD (12, 26, 9) 계산 + 크로스오버 감지."""
    if len(closes) < 26:
        return None

    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    # 크로스오버 감지 (최근 3일 내)
    crossover = False
    crossunder = False
    if len(histogram) >= 2:
        prev_hist = histogram.iloc[-2]
        curr_hist = histogram.iloc[-1]
        crossover = bool(prev_hist <= 0 and curr_hist > 0)  # 매수 신호
        crossunder = bool(prev_hist >= 0 and curr_hist < 0)  # 매도 신호

    return {
        "macd": round(macd_line.iloc[-1], 2),
        "signal": round(signal_line.iloc[-1], 2),
        "histogram": round(histogram.iloc[-1], 2),
        "bullish": bool(histogram.iloc[-1] > 0),
        "crossover": crossover,
        "crossunder": crossunder,
    }


def calc_obv(closes: pd.Series, volumes: pd.Series) -> dict | None:
    """OBV (On-Balance Volume) 계산."""
    if len(closes) < 10 or len(volumes) < 10:
        return None

    obv = pd.Series(0.0, index=closes.index)
    for i in range(1, len(closes)):
        if closes.iloc[i] > closes.iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] + volumes.iloc[i]
        elif closes.iloc[i] < closes.iloc[i - 1]:
            obv.iloc[i] = obv.iloc[i - 1] - volumes.iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i - 1]

    # OBV 추세: 최근 5일 OBV MA vs 20일 OBV MA
    obv_ma5 = obv.rolling(5).mean()
    obv_ma20 = obv.rolling(20).mean()

    obv_trend = "neutral"
    if len(obv_ma5.dropna()) and len(obv_ma20.dropna()):
        if obv_ma5.iloc[-1] > obv_ma20.iloc[-1]:
            obv_trend = "bullish"
        elif obv_ma5.iloc[-1] < obv_ma20.iloc[-1]:
            obv_trend = "bearish"

    # 가격-OBV 다이버전스 감지 (5일 기준)
    price_up = closes.iloc[-1] > closes.iloc[-5] if len(closes) >= 5 else None
    obv_up = obv.iloc[-1] > obv.iloc[-5] if len(obv) >= 5 else None
    divergence = None
    if price_up is not None and obv_up is not None:
        if price_up and not obv_up:
            divergence = "bearish"  # 가격 상승 but OBV 하락 → 약세 다이버전스
        elif not price_up and obv_up:
            divergence = "bullish"  # 가격 하락 but OBV 상승 → 강세 다이버전스

    return {
        "obv": int(obv.iloc[-1]),
        "obv_trend": obv_trend,
        "divergence": divergence,
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


def calc_bollinger_bands(closes: pd.Series, period: int = 20, num_std: float = 2.0) -> dict | None:
    """볼린저 밴드 계산."""
    if len(closes) < period:
        return None

    sma = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    upper = sma + num_std * std
    lower = sma - num_std * std

    latest = closes.iloc[-1]
    mid = sma.iloc[-1]
    up = upper.iloc[-1]
    lo = lower.iloc[-1]
    band_width = up - lo

    bandwidth = band_width / mid * 100 if mid > 0 else 0
    pct_b = (latest - lo) / band_width if band_width > 0 else 0.5

    return {
        "upper": round(up, 2),
        "middle": round(mid, 2),
        "lower": round(lo, 2),
        "bandwidth": round(bandwidth, 2),
        "pct_b": round(pct_b, 4),
    }


def calc_adx(closes: pd.Series, period: int = 14) -> dict:
    """ADX (Average Directional Index) 계산 - Close-only 근사.

    high/low 데이터 없이 종가만으로 +DM/-DM/TR을 근사 계산.
    Returns:
        {"adx": float, "plus_di": float, "minus_di": float}
    """
    if len(closes) < period * 2:
        return {"adx": 25.0, "plus_di": 50.0, "minus_di": 50.0}

    diff = closes.diff()
    plus_dm = diff.where(diff > 0, 0.0)
    minus_dm = (-diff).where(diff < 0, 0.0)
    tr = diff.abs()

    # EWM 평활화
    smoothed_plus = plus_dm.ewm(span=period, adjust=False).mean()
    smoothed_minus = minus_dm.ewm(span=period, adjust=False).mean()
    smoothed_tr = tr.ewm(span=period, adjust=False).mean()

    # +DI / -DI
    plus_di = (smoothed_plus / smoothed_tr * 100).replace([np.inf, -np.inf], 0).fillna(0)
    minus_di = (smoothed_minus / smoothed_tr * 100).replace([np.inf, -np.inf], 0).fillna(0)

    # DX → ADX
    di_sum = plus_di + minus_di
    dx = ((plus_di - minus_di).abs() / di_sum.where(di_sum > 0, 1.0) * 100)
    adx = dx.ewm(span=period, adjust=False).mean()

    last_adx = adx.iloc[-1]
    last_plus = plus_di.iloc[-1]
    last_minus = minus_di.iloc[-1]

    if pd.isna(last_adx):
        return {"adx": 25.0, "plus_di": 50.0, "minus_di": 50.0}

    return {
        "adx": round(float(last_adx), 2),
        "plus_di": round(float(last_plus), 2),
        "minus_di": round(float(last_minus), 2),
    }


def calc_atr(closes: pd.Series, highs: pd.Series | None = None,
             lows: pd.Series | None = None, period: int = 14) -> float | None:
    """ATR (Average True Range) 계산. highs/lows 없으면 closes 기반 근사."""
    if len(closes) < period + 1:
        return None

    if highs is not None and lows is not None:
        tr1 = highs - lows
        tr2 = (highs - closes.shift(1)).abs()
        tr3 = (lows - closes.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    else:
        # closes만으로 근사: |close - prev_close|
        tr = closes.diff().abs()

    atr = tr.ewm(alpha=1/period, adjust=False).mean().iloc[-1]
    return round(atr, 2)


def calc_technical_score(closes: pd.Series, volumes: pd.Series) -> tuple[float, dict]:
    """기술적 분석 종합 점수 (0~100)를 반환.

    다중공선성 해소:
    - MA와 MACD는 독립 신호만 카운트 (정배열/크로스오버 중심)
    - RSI와 BB는 과매수/과매도에서만 독립 적용

    Returns:
        (score, details) 튜플
    """
    score = 50.0  # 기본 중립
    details: dict = {}

    # ── 이동평균 (최대 ±15점) ──
    # MA/MACD 다중공선성 해소: 개별 MA 위/아래 점수 축소, 정배열 보너스 강조
    ma = calc_moving_averages(closes)
    details["moving_averages"] = ma
    ma_score = 0.0

    # 개별 MA 포지션 (축소: 각 2-3점)
    if ma.get("above_ma20"):
        ma_score += 3
    elif ma.get("above_ma20") is False:
        ma_score -= 3
    if ma.get("above_ma60"):
        ma_score += 3
    elif ma.get("above_ma60") is False:
        ma_score -= 3

    # 장기 MA (120/200일) 보너스
    if ma.get("above_ma120"):
        ma_score += 2
    elif ma.get("above_ma120") is False:
        ma_score -= 2
    if ma.get("above_ma200"):
        ma_score += 2
    elif ma.get("above_ma200") is False:
        ma_score -= 2

    # 정배열/역배열 보너스 (핵심 신호)
    if ma.get("ma_aligned_bull"):
        ma_score += 5
    if ma.get("ma_aligned_bear"):
        ma_score -= 5

    # 골든/데드크로스 (이벤트 신호)
    if ma.get("golden_cross"):
        ma_score += 5
    if ma.get("dead_cross"):
        ma_score -= 5

    score += np.clip(ma_score, -15, 15)

    # ── RSI (최대 ±12점) ──
    rsi = calc_rsi(closes)
    details["rsi"] = rsi
    if rsi is not None:
        if rsi < 25:
            score += 12  # 극단적 과매도
        elif rsi < 30:
            score += 8
        elif rsi < 40:
            score += 4
        elif rsi > 75:
            score -= 12  # 극단적 과매수
        elif rsi > 70:
            score -= 8
        elif rsi > 60:
            score -= 3

    # ── MACD (최대 ±12점) ──
    # 크로스오버에 높은 가중치, 히스토그램 크기에 비례
    macd = calc_macd(closes)
    details["macd"] = macd
    if macd:
        hist_pct = abs(macd["histogram"]) / closes.iloc[-1] * 100 if closes.iloc[-1] > 0 else 0
        macd_strength = min(5, 2 + hist_pct * 10)

        if macd["bullish"]:
            score += macd_strength
        else:
            score -= macd_strength

        # 크로스오버 보너스 (핵심 타이밍 신호)
        if macd.get("crossover"):
            score += 3
        if macd.get("crossunder"):
            score -= 3

    # ── 거래량 (최대 ±8점) ── (강화)
    vol = calc_volume_trend(volumes)
    details["volume_trend"] = vol
    if vol:
        price_up = closes.iloc[-1] > closes.iloc[-2] if len(closes) >= 2 else False
        ratio = vol["volume_ratio"]

        if ratio > 2.0:  # 폭발적 거래량
            score += 6 if price_up else -6
        elif ratio > 1.5:  # 높은 거래량
            score += 4 if price_up else -4
        elif ratio < 0.5:  # 극단적 저거래량
            score -= 2  # 관심 부족

    # ── OBV (최대 ±5점) ── (신규)
    obv = calc_obv(closes, volumes)
    details["obv"] = obv
    if obv:
        if obv["obv_trend"] == "bullish":
            score += 3
        elif obv["obv_trend"] == "bearish":
            score -= 3
        if obv.get("divergence") == "bullish":
            score += 2  # 강세 다이버전스
        elif obv.get("divergence") == "bearish":
            score -= 2  # 약세 다이버전스

    # ── 볼린저 밴드 (최대 ±8점) ──
    bb = calc_bollinger_bands(closes)
    details["bollinger_bands"] = bb
    if bb:
        pct_b = bb["pct_b"]
        if pct_b < 0:
            score += 8  # 하단 밴드 이탈 → 과매도
        elif pct_b < 0.2:
            score += 5
        elif pct_b > 1.0:
            score -= 8  # 상단 밴드 이탈 → 과매수
        elif pct_b > 0.8:
            score -= 5

        # BB 스퀴즈 감지
        bb_bandwidth = bb.get("bandwidth", 0)
        if bb_bandwidth > 0:
            if bb_bandwidth < 4.0:  # 극도로 좁은 밴드 → 돌파 임박
                score += 3
            elif bb_bandwidth < 6.0:
                score += 1  # 약한 스퀴즈

    # ── ADX 추세강도 (최대 ±5점) ──
    adx_data = calc_adx(closes)
    adx_val = adx_data["adx"]
    details["adx"] = adx_data

    # trend_direction: MA5 > MA20이면 +1, 아니면 -1
    if ma.get("ma5") is not None and ma.get("ma20") is not None:
        trend_direction = 1 if ma["ma5"] > ma["ma20"] else -1
    else:
        trend_direction = 0  # MA 데이터 부족 시 중립
    details["trend_direction"] = trend_direction

    if adx_val > 40:  # 강한 추세
        if trend_direction > 0:  # 상승 추세
            score += 5  # 추세 추종 보너스
        else:
            score -= 5  # 강한 하락 추세 페널티
    elif adx_val < 20:  # 약한 추세 (횡보)
        score -= 3  # 횡보장 거짓 신호 억제

    # ── ATR (변동성 정보 - 점수 직접 영향 없음, 리스크 서비스에서 활용) ──
    atr = calc_atr(closes)
    details["atr"] = atr

    return float(np.clip(score, 0, 100)), details
