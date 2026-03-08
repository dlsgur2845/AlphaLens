"""매매 시그널 서비스."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.models.schemas import SignalBreakdown, SignalScore
from backend.utils.technical import calc_atr, calc_bollinger_bands, calc_macd, calc_rsi


# 7단계 액션 라벨
ACTION_LABELS = {
    (80, 101): "강력매수",  # 100점 포함
    (65, 80): "매수",
    (55, 65): "관망(매수우위)",
    (45, 55): "중립",
    (35, 45): "관망(매도우위)",
    (20, 35): "매도",
    (0, 20): "강력매도",
}


def _get_action_label(score: float) -> str:
    for (lo, hi), label in ACTION_LABELS.items():
        if lo <= score < hi:
            return label
    return "중립"


def _detect_regime(closes: pd.Series) -> tuple[str, float]:
    """시장 레짐 감지: BULL/BEAR/SIDEWAYS/TRANSITION."""
    if len(closes) < 60:
        return "UNKNOWN", 0.0

    ma20 = closes.rolling(20).mean()
    ma60 = closes.rolling(60).mean()

    if len(ma20.dropna()) < 2 or len(ma60.dropna()) < 2:
        return "UNKNOWN", 0.0

    # 추세 판단
    ma20_slope = (ma20.iloc[-1] - ma20.iloc[-5]) / ma20.iloc[-5] * 100 if len(ma20.dropna()) >= 5 else 0
    ma60_slope = (ma60.iloc[-1] - ma60.iloc[-10]) / ma60.iloc[-10] * 100 if len(ma60.dropna()) >= 10 else 0

    # 변동성
    returns = closes.pct_change().dropna()
    volatility = returns.tail(20).std() * np.sqrt(252) * 100 if len(returns) >= 20 else 20

    # 레짐 판정
    if ma20.iloc[-1] > ma60.iloc[-1] and ma20_slope > 0.5:
        regime = "BULL"
        regime_score = min(80, 50 + ma20_slope * 5)
    elif ma20.iloc[-1] < ma60.iloc[-1] and ma20_slope < -0.5:
        regime = "BEAR"
        regime_score = max(20, 50 + ma20_slope * 5)
    elif abs(ma20_slope) < 0.3 and volatility < 25:
        regime = "SIDEWAYS"
        regime_score = 50.0
    else:
        regime = "TRANSITION"
        regime_score = 50.0 + ma20_slope * 3

    return regime, float(np.clip(regime_score, 0, 100))


def _momentum_signal(closes: pd.Series, volumes: pd.Series) -> tuple[float, list[str]]:
    """모멘텀 매수 신호 (다중 시간축: 5일/20일/60일)."""
    score = 0.0
    signals = []

    if len(closes) < 20:
        return score, signals

    # 단기 모멘텀 (5일)
    if len(closes) >= 6:
        ret_5d = (closes.iloc[-1] / closes.iloc[-6] - 1) * 100
        if ret_5d > 3:
            score += 5
            signals.append(f"5일 단기 상승 모멘텀 +{ret_5d:.1f}%")
        elif ret_5d < -3:
            score -= 5
            signals.append(f"5일 단기 하락 모멘텀 {ret_5d:.1f}%")

    # 20일 수익률
    ret_20d = (closes.iloc[-1] / closes.iloc[-20] - 1) * 100
    if ret_20d > 5:
        score += 15
        signals.append(f"20일 수익률 +{ret_20d:.1f}%")
    elif ret_20d > 2:
        score += 8
    elif ret_20d < -5:
        score -= 15
        signals.append(f"20일 하락 모멘텀 {ret_20d:.1f}%")
    elif ret_20d < -2:
        score -= 8
        signals.append(f"20일 약세 모멘텀 {ret_20d:.1f}%")

    # 장기 모멘텀 (60일)
    if len(closes) >= 61:
        ret_60d = (closes.iloc[-1] / closes.iloc[-61] - 1) * 100
        if ret_60d > 15:
            score += 5
            signals.append(f"60일 장기 상승 추세 +{ret_60d:.1f}%")
        elif ret_60d < -15:
            score -= 5
            signals.append(f"60일 장기 하락 추세 {ret_60d:.1f}%")

    # 거래량 동반 상승
    if len(volumes) >= 5:
        vol_avg = volumes.tail(5).mean()
        vol_prev_avg = volumes.iloc[-25:-5].mean() if len(volumes) >= 25 else volumes.mean()
        if vol_avg > vol_prev_avg * 1.3 and ret_20d > 0:
            score += 10
            signals.append("거래량 동반 상승")

    return float(np.clip(score, -40, 40)), signals


def _mean_reversion_signal(closes: pd.Series) -> tuple[float, list[str]]:
    """평균회귀 매수 신호 (Bollinger Band %B 기반).

    Technical의 MA20 위치 점수와 다중공선성을 해소하기 위해
    MA20 편차 대신 BB %B를 사용하여 과매수/과매도를 판단.
    """
    score = 0.0
    signals = []

    if len(closes) < 20:
        return score, signals

    bb = calc_bollinger_bands(closes)
    if bb is None:
        return score, signals

    pctb = bb["pct_b"]

    if pctb < 0.1:
        score += 15
        signals.append(f"BB %B {pctb:.2f} (극도 과매도, 반등 기대)")
    elif pctb < 0.2:
        score += 10
        signals.append(f"BB %B {pctb:.2f} (과매도)")
    elif pctb < 0.3:
        score += 5
        signals.append(f"BB %B {pctb:.2f} (하단 접근)")
    elif pctb > 0.9:
        score -= 15
        signals.append(f"BB %B {pctb:.2f} (극도 과매수, 조정 기대)")
    elif pctb > 0.8:
        score -= 10
        signals.append(f"BB %B {pctb:.2f} (과매수)")
    elif pctb > 0.7:
        score -= 5
        signals.append(f"BB %B {pctb:.2f} (상단 접근)")

    return float(np.clip(score, -20, 20)), signals


def _breakout_signal(closes: pd.Series, volumes: pd.Series) -> tuple[float, list[str]]:
    """돌파 매수 신호."""
    score = 0.0
    signals = []

    if len(closes) < 60:
        return score, signals

    # 현재가를 제외한 이전 고점과 비교
    high_20d = closes.iloc[:-1].tail(19).max() if len(closes) > 20 else closes.iloc[:-1].max()
    high_60d = closes.iloc[:-1].tail(59).max() if len(closes) > 60 else closes.iloc[:-1].max()
    latest = closes.iloc[-1]

    # 20일 신고가 돌파
    if latest >= high_20d * 0.99:
        score += 10
        signals.append("20일 고가 근접/돌파")

        # 거래량 동반
        if len(volumes) >= 20:
            vol_ratio = volumes.iloc[-1] / volumes.tail(20).mean()
            if vol_ratio > 1.5:
                score += 8
                signals.append(f"거래량 {vol_ratio:.1f}배 동반")

    # 60일 신고가 돌파
    if latest >= high_60d * 0.99:
        score += 5
        signals.append("60일 고가 근접/돌파")

    return float(np.clip(score, -20, 25)), signals


def _sell_signals(closes: pd.Series) -> tuple[float, list[str]]:
    """매도 신호."""
    score = 0.0
    signals = []

    if len(closes) < 20:
        return score, signals

    close = closes.iloc[-1]

    # Phase 1: 이익실현 (고점 대비 하락)
    high_20d = closes.tail(20).max()
    drawdown = (close / high_20d - 1) * 100

    if drawdown < -10:
        score -= 18
        signals.append(f"20일 고점 대비 {drawdown:.1f}% 하락")
    elif drawdown < -5:
        score -= 10
        signals.append(f"20일 고점 대비 {drawdown:.1f}% 조정")

    # Phase 2: 추세 이탈
    if len(closes) >= 60:
        ma60 = closes.rolling(60).mean().iloc[-1]
        if close < ma60 * 0.95:
            score -= 12
            signals.append("60일선 5% 이탈 (추세 이탈)")

    # Phase 3: MACD 데드크로스
    try:
        macd_data = calc_macd(closes)
        if macd_data is not None:
            histogram = macd_data["histogram"]
            if histogram is not None and histogram < 0 and abs(histogram) > 0.5:
                score -= 8
                signals.append("MACD 데드크로스")
    except Exception:
        pass  # MACD 계산 실패 시 스킵

    # Phase 4: RSI 과매수 반전
    try:
        rsi = calc_rsi(closes)
        if rsi is not None and rsi > 70:
            score -= 6
            signals.append(f"RSI 과매수 ({rsi:.1f})")
        elif rsi is not None and rsi > 60:
            # 최근 5일 RSI가 70 이상이었다가 내려온 경우
            if len(closes) >= 6:
                recent_rsis = [calc_rsi(closes[:i]) for i in range(len(closes) - 5, len(closes) + 1)]
                recent_rsis = [r for r in recent_rsis if r is not None]
                if recent_rsis and any(r > 70 for r in recent_rsis[:-1]) and recent_rsis[-1] < 65:
                    score -= 5
                    signals.append("RSI 과매수 반전")
    except Exception:
        pass  # RSI 계산 실패 시 스킵

    # Phase 5: ATR 트레일링 스탑 이탈
    try:
        atr = calc_atr(closes)
        if atr is not None and atr > 0:
            trailing_stop = high_20d - (atr * 2.5)
            if close < trailing_stop:
                score -= 10
                signals.append("ATR 트레일링 스탑 이탈")
    except Exception:
        pass  # ATR 계산 실패 시 스킵

    return float(np.clip(score, -55, 0)), signals


def _credit_signal(credit_data: dict | None) -> tuple[float, list[str]]:
    """신용잔고 기반 시그널 (-10 ~ +10점).

    신용비율이 높으면 → 과열 경고 (매도 신호)
    신용비율이 낮으면 → 안전 (약한 매수 보조)
    공매도비율이 높으면 → 숏 스퀴즈 가능성 (매수 보조)
    """
    score = 0.0
    signals = []

    if not credit_data:
        return score, signals

    credit_ratio = credit_data.get("credit_ratio", 0)
    short_ratio = credit_data.get("short_ratio", 0)

    # 신용비율 분석 (높을수록 과열)
    if credit_ratio > 10:
        score -= 10
        signals.append(f"신용비율 {credit_ratio:.1f}% (과열 경고, 반대매매 위험)")
    elif credit_ratio > 5:
        score -= 5
        signals.append(f"신용비율 {credit_ratio:.1f}% (주의)")
    elif credit_ratio > 3:
        score -= 2
    elif credit_ratio > 0 and credit_ratio < 1:
        score += 3
        signals.append(f"신용비율 {credit_ratio:.1f}% (안전)")

    # 공매도비율 분석 (높으면 숏 스퀴즈 가능성)
    if short_ratio > 5:
        score += 5
        signals.append(f"공매도비율 {short_ratio:.1f}% (숏 스퀴즈 가능성)")
    elif short_ratio > 3:
        score += 2

    return float(np.clip(score, -10, 10)), signals


def calc_signal_score(
    closes: pd.Series,
    volumes: pd.Series,
    credit_data: dict | None = None,
) -> SignalScore:
    """종합 시그널 스코어 계산."""
    if len(closes) < 20:
        return SignalScore()

    # 레짐 감지
    regime, regime_score = _detect_regime(closes)

    # 매수 신호
    mom_score, mom_signals = _momentum_signal(closes, volumes)
    mr_score, mr_signals = _mean_reversion_signal(closes)
    bo_score, bo_signals = _breakout_signal(closes, volumes)

    # 매도 신호
    sell_score, sell_signals_list = _sell_signals(closes)

    # 신용잔고 신호
    credit_score, credit_signals = _credit_signal(credit_data)

    # 레짐별 전략 가중치 적용
    if regime == "BULL":
        mom_weight, mr_weight = 1.3, 0.5
    elif regime == "BEAR":
        mom_weight, mr_weight = 0.5, 0.7
    elif regime == "SIDEWAYS":
        mom_weight, mr_weight = 0.5, 1.3
    else:  # TRANSITION, UNKNOWN
        mom_weight, mr_weight = 1.0, 1.0

    # 종합 (기본 50 + 가중 적용된 매수/매도 신호 + 신용잔고 신호)
    total = 50.0 + (mom_score * mom_weight) + (mr_score * mr_weight) + bo_score + sell_score + credit_score

    # 시그널 합의도 보너스: 5개 시그널 중 3개 이상 동일 방향이면 ±3
    signals = [mom_score, mr_score, bo_score, sell_score, credit_score]
    positive_count = sum(1 for s in signals if s > 0)
    negative_count = sum(1 for s in signals if s < 0)
    if positive_count >= 3:
        total += 3
    elif negative_count >= 3:
        total -= 3

    total = float(np.clip(total, 0, 100))

    # 신용잔고 신호를 매수/매도 시그널에 분류
    credit_buy = [s for s in credit_signals if "안전" in s or "스퀴즈" in s]
    credit_sell = [s for s in credit_signals if "과열" in s or "주의" in s]

    return SignalScore(
        score=total,
        action_label=_get_action_label(total),
        breakdown=SignalBreakdown(
            momentum=mom_score * mom_weight,
            mean_reversion=mr_score * mr_weight,
            breakout=bo_score,
            regime=regime,
            regime_score=regime_score,
        ),
        buy_signals=mom_signals + mr_signals + bo_signals + credit_buy,
        sell_signals=sell_signals_list + credit_sell,
    )
