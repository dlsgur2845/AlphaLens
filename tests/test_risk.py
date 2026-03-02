"""리스크 서비스 단위 테스트."""
import numpy as np
import pandas as pd
import pytest

from backend.services.risk_service import (
    _liquidity_score,
    _mdd_score,
    _var_cvar_score,
    _volatility_score,
    calc_risk_score,
)


VALID_GRADES = ["A", "B", "C", "D", "E"]


class TestCalcRiskScore:
    """종합 리스크 스코어 테스트."""

    def test_score_range(self, sample_closes, sample_volumes):
        result = calc_risk_score(sample_closes, sample_volumes)
        assert 0 <= result.score <= 100

    def test_valid_grade(self, sample_closes, sample_volumes):
        result = calc_risk_score(sample_closes, sample_volumes)
        assert result.grade in VALID_GRADES, (
            f"유효하지 않은 등급: {result.grade}"
        )

    def test_has_breakdown(self, sample_closes, sample_volumes):
        result = calc_risk_score(sample_closes, sample_volumes)
        assert hasattr(result.breakdown, "volatility")
        assert hasattr(result.breakdown, "mdd")
        assert hasattr(result.breakdown, "var_cvar")
        assert hasattr(result.breakdown, "liquidity")

    def test_position_size_range(self, sample_closes, sample_volumes):
        result = calc_risk_score(sample_closes, sample_volumes)
        assert 1.0 <= result.position_size_pct <= 15.0

    def test_atr_present(self, sample_closes, sample_volumes):
        result = calc_risk_score(sample_closes, sample_volumes)
        assert result.atr is not None
        assert result.atr > 0


class TestVolatilityScore:
    """변동성 점수 테스트."""

    def test_low_volatility_high_score(self):
        """저변동성 -> 높은 점수 (안전)."""
        np.random.seed(42)
        # 매우 작은 일일 변동 -> 낮은 연환산 변동성
        base = 50000
        prices = [base + np.random.normal(0, 10) for _ in range(200)]
        closes = pd.Series(prices, dtype=float)
        score = _volatility_score(closes)
        assert score >= 70, f"저변동성에서 높은 점수 기대: {score}"

    def test_high_volatility_low_score(self):
        """고변동성 -> 낮은 점수 (위험)."""
        np.random.seed(42)
        # 큰 일일 변동
        base = 50000
        prices = [base]
        for _ in range(199):
            prices.append(prices[-1] * (1 + np.random.normal(0, 0.05)))
        closes = pd.Series(prices, dtype=float)
        score = _volatility_score(closes)
        assert score <= 50, f"고변동성에서 낮은 점수 기대: {score}"

    def test_score_continuous_range(self, sample_closes):
        """변동성 점수가 0-100 사이 연속값."""
        score = _volatility_score(sample_closes)
        assert 0 <= score <= 100

    def test_insufficient_data_returns_50(self):
        short = pd.Series([100, 101, 102], dtype=float)
        assert _volatility_score(short) == 50.0


class TestMddScore:
    """MDD 점수 테스트."""

    def test_steady_uptrend_high_score(self):
        """꾸준한 상승 -> MDD 작음 -> 높은 점수."""
        prices = [50000 + 100 * i for i in range(200)]
        closes = pd.Series(prices, dtype=float)
        score = _mdd_score(closes)
        assert score >= 70, f"꾸준한 상승에서 높은 MDD 점수 기대: {score}"

    def test_crash_low_score(self):
        """급락 -> MDD 큼 -> 낮은 점수."""
        prices = [50000 + 100 * i for i in range(100)]
        # 50% 하락
        for i in range(100):
            prices.append(prices[99] * (1 - 0.007 * i))
        closes = pd.Series(prices, dtype=float)
        score = _mdd_score(closes)
        assert score <= 30, f"급락 시 낮은 MDD 점수 기대: {score}"

    def test_score_continuous_range(self, sample_closes):
        """MDD 점수가 0-100 사이 연속값."""
        score = _mdd_score(sample_closes)
        assert 0 <= score <= 100


class TestLiquidityScore:
    """유동성 점수 테스트."""

    def test_high_volume_high_score(self):
        """높은 거래량 -> 높은 유동성 점수."""
        volumes = pd.Series([2_000_000] * 200, dtype=float)
        score = _liquidity_score(volumes)
        assert score >= 75

    def test_low_volume_low_score(self):
        """낮은 거래량 -> 낮은 유동성 점수."""
        volumes = pd.Series([5_000] * 200, dtype=float)
        score = _liquidity_score(volumes)
        assert score <= 20

    def test_score_continuous_range(self, sample_volumes):
        """유동성 점수가 0-100 사이 연속값."""
        score = _liquidity_score(sample_volumes)
        assert 10.0 <= score <= 90.0


class TestVarCvarScore:
    """VaR/CVaR 점수 테스트."""

    def test_stable_stock_high_score(self):
        """안정적 종목 -> 높은 VaR 점수."""
        np.random.seed(42)
        base = 50000
        prices = [base + np.random.normal(0, 10) for _ in range(200)]
        closes = pd.Series(prices, dtype=float)
        score = _var_cvar_score(closes)
        assert score >= 70, f"안정적 종목에서 높은 VaR 점수 기대: {score}"

    def test_volatile_stock_low_score(self):
        """고변동 종목 -> 낮은 VaR 점수."""
        np.random.seed(42)
        base = 50000
        prices = [base]
        for _ in range(199):
            prices.append(prices[-1] * (1 + np.random.normal(0, 0.05)))
        closes = pd.Series(prices, dtype=float)
        score = _var_cvar_score(closes)
        assert score <= 50, f"고변동 종목에서 낮은 VaR 점수 기대: {score}"

    def test_insufficient_data_returns_50(self):
        short = pd.Series([100, 101, 102], dtype=float)
        assert _var_cvar_score(short) == 50.0

    def test_score_range(self, sample_closes):
        score = _var_cvar_score(sample_closes)
        assert 0 <= score <= 100
