"""리스크 관리 서비스."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.models.schemas import RiskBreakdown, RiskScore


RISK_GRADES = {
    (80, 101): "A",  # 매우 안전 (100점 포함)
    (60, 80): "B",   # 안전
    (40, 60): "C",   # 보통
    (20, 40): "D",   # 위험
    (0, 20): "E",    # 매우 위험
}


def _get_risk_grade(score: float) -> str:
    for (lo, hi), grade in RISK_GRADES.items():
        if lo <= score < hi:
            return grade
    return "C"


def _interpolate_score(value: float, breakpoints: list[tuple[float, float]]) -> float:
    """브레이크포인트 기반 선형 보간 점수 계산."""
    if value <= breakpoints[0][0]:
        return float(breakpoints[0][1])
    if value >= breakpoints[-1][0]:
        return float(breakpoints[-1][1])

    for i in range(len(breakpoints) - 1):
        v0, s0 = breakpoints[i]
        v1, s1 = breakpoints[i + 1]
        if v0 <= value <= v1:
            ratio = (value - v0) / (v1 - v0)
            return float(s0 + (s1 - s0) * ratio)

    return 50.0


def _volatility_score(closes: pd.Series) -> float:
    """다중 윈도우 변동성 점수. 높은 점수 = 낮은 리스크."""
    if len(closes) < 20:
        return 50.0

    returns = closes.pct_change().dropna()

    # 다중 윈도우
    vol_10 = returns.tail(10).std() * np.sqrt(252) * 100 if len(returns) >= 10 else None
    vol_20 = returns.tail(20).std() * np.sqrt(252) * 100
    vol_60 = returns.tail(60).std() * np.sqrt(252) * 100 if len(returns) >= 60 else None

    # 가중 평균 (단기 비중 높게)
    weights, vols = [], []
    if vol_10 is not None:
        weights.append(0.4)
        vols.append(vol_10)
    weights.append(0.35 if vol_10 else 0.6)
    vols.append(vol_20)
    if vol_60 is not None:
        weights.append(0.25)
        vols.append(vol_60)

    # 정규화
    total_w = sum(weights)
    weighted_vol = sum(w * v for w, v in zip(weights, vols)) / total_w

    breakpoints = [(10, 95), (15, 80), (25, 55), (35, 30), (50, 10)]
    return _interpolate_score(weighted_vol, breakpoints)


def _mdd_score(closes: pd.Series) -> float:
    """Rolling MDD + 회복률 점수."""
    if len(closes) < 20:
        return 50.0

    # 60일 Rolling MDD (전체 expanding 대신)
    window = min(60, len(closes))
    rolling_peak = closes.rolling(window=window, min_periods=1).max()
    drawdown = (closes - rolling_peak) / rolling_peak
    current_mdd = abs(float(drawdown.iloc[-1])) * 100  # 현재 MDD (%)
    max_mdd = abs(float(drawdown.min())) * 100  # 기간 내 최대 MDD (%)

    # MDD 점수 (현재 MDD와 최대 MDD를 7:3으로 혼합)
    mdd_val = current_mdd * 0.7 + max_mdd * 0.3

    breakpoints = [(5, 95), (10, 80), (20, 55), (30, 30), (50, 10)]
    base = _interpolate_score(mdd_val, breakpoints)

    # 회복률 보정: 현재가 고점 대비 회복 중이면 보너스
    if current_mdd < max_mdd * 0.5 and max_mdd > 10:
        base += 5  # 반 이상 회복

    return min(base, 100.0)


def _var_cvar_score(closes: pd.Series) -> float:
    """VaR(95%)와 CVaR로 테일 리스크 평가."""
    if len(closes) < 30:
        return 50.0
    returns = closes.pct_change().dropna()
    var_95 = float(np.percentile(returns, 5))  # 5th percentile = 95% VaR
    tail = returns[returns <= var_95]
    cvar_95 = float(tail.mean()) if len(tail) > 0 else var_95

    # VaR를 일간 % 기준으로 변환 (절대값)
    var_pct = abs(var_95) * 100
    cvar_pct = abs(cvar_95) * 100

    # VaR 점수 (일간 최대 손실 기준)
    var_score = _interpolate_score(var_pct, [
        (1.0, 95), (2.0, 80), (3.5, 60), (5.0, 40), (8.0, 20), (12.0, 5),
    ])

    # CVaR 보정: CVaR가 VaR의 1.5배 이상이면 추가 감점 (fat tail)
    if cvar_pct > var_pct * 1.5:
        var_score *= 0.85  # 15% 추가 감점

    return round(var_score, 1)


def _liquidity_score(volumes: pd.Series) -> float:
    """유동성 기반 리스크 점수 (연속 선형 보간)."""
    if len(volumes) < 20:
        return 50.0

    avg_volume = volumes.tail(20).mean()

    # 거래량 구간별 연속 보간
    breakpoints = [
        (10_000, 10), (50_000, 25), (100_000, 40),
        (500_000, 60), (1_000_000, 75), (5_000_000, 90),
    ]
    return _interpolate_score(avg_volume, breakpoints)


def _calc_position_size(
    closes: pd.Series,
    risk_score: float = 50.0,
    portfolio_value: float = 100_000_000,
) -> float:
    """ATR 기반 포지션 사이징 (% of portfolio). 리스크 등급 연동."""
    if len(closes) < 15:
        return 5.0  # 기본 5%

    atr = closes.diff().abs().ewm(alpha=1/14, adjust=False).mean().iloc[-1]
    if atr <= 0 or closes.iloc[-1] <= 0:
        return 5.0

    # 적응형 리스크 비율: 등급에 따라 차등 배분
    grade = _get_risk_grade(risk_score)
    risk_pct_map = {"A": 0.03, "B": 0.02, "C": 0.015, "D": 0.01, "E": 0.005}
    risk_per_trade = risk_pct_map.get(grade, 0.02)

    risk_amount = portfolio_value * risk_per_trade
    shares = risk_amount / atr
    position_value = shares * closes.iloc[-1]
    position_pct = (position_value / portfolio_value) * 100

    return float(np.clip(position_pct, 1.0, 15.0))


def _calc_atr(closes: pd.Series, period: int = 14) -> float | None:
    """ATR 계산."""
    if len(closes) < period + 1:
        return None
    atr = closes.diff().abs().ewm(alpha=1/period, adjust=False).mean().iloc[-1]
    return round(atr, 2)


def _leverage_risk_score(credit_data: dict | None) -> float:
    """신용잔고 기반 레버리지 리스크 점수 (0~100, 높을수록 안전)."""
    if not credit_data:
        return 50.0  # 데이터 없으면 중립

    credit_ratio = credit_data.get("credit_ratio", 0)

    # 신용비율 기반 리스크 평가
    breakpoints = [
        (0.5, 95),   # 0.5% 이하: 매우 안전
        (2.0, 75),   # 2% 이하: 안전
        (5.0, 50),   # 5% 이하: 보통
        (10.0, 25),  # 10% 이하: 위험
        (20.0, 5),   # 20% 이상: 매우 위험
    ]
    base = _interpolate_score(credit_ratio, breakpoints)

    # 공매도비율 보정 (높으면 숏 스퀴즈 리스크 = 변동성 상승)
    short_ratio = credit_data.get("short_ratio", 0)
    if short_ratio > 5:
        base *= 0.9  # 10% 감점

    return round(base, 1)


def calc_risk_score(
    closes: pd.Series,
    volumes: pd.Series,
    credit_data: dict | None = None,
) -> RiskScore:
    """종합 리스크 스코어 계산."""
    vol_score = _volatility_score(closes)
    mdd_s = _mdd_score(closes)
    var_s = _var_cvar_score(closes)
    liq_score = _liquidity_score(volumes)
    lev_score = _leverage_risk_score(credit_data)

    # 가중 평균 (신용잔고 데이터 유무에 따라 가중치 조정)
    if credit_data:
        # 레버리지 리스크 포함: 변동성 28% + MDD 23% + VaR 18% + 유동성 23% + 레버리지 8%
        total = (
            vol_score * 0.28
            + mdd_s * 0.23
            + var_s * 0.18
            + liq_score * 0.23
            + lev_score * 0.08
        )
    else:
        # 기존 가중치 유지
        total = vol_score * 0.30 + mdd_s * 0.25 + var_s * 0.20 + liq_score * 0.25

    total = float(np.clip(total, 0, 100))

    return RiskScore(
        score=total,
        grade=_get_risk_grade(total),
        breakdown=RiskBreakdown(
            volatility=round(vol_score, 1),
            mdd=round(mdd_s, 1),
            var_cvar=round(var_s, 1),
            liquidity=round(liq_score, 1),
            leverage=round(lev_score, 1),
        ),
        position_size_pct=round(_calc_position_size(closes, total), 1),
        atr=_calc_atr(closes),
    )
