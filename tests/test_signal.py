"""시그널 서비스 단위 테스트."""
import numpy as np
import pandas as pd
import pytest

from backend.services.signal_service import (
    _detect_regime,
    _mean_reversion_signal,
    _momentum_signal,
    _sell_signals,
    calc_signal_score,
)


VALID_ACTION_LABELS = [
    "강력매수", "매수", "관망(매수우위)", "중립",
    "관망(매도우위)", "매도", "강력매도",
]


class TestDetectRegime:
    """시장 레짐 감지 테스트."""

    def test_bull_regime(self, bull_closes):
        regime, score = _detect_regime(bull_closes)
        assert regime == "BULL", f"상승 추세에서 레짐이 BULL이 아님: {regime}"

    def test_bear_regime(self, bear_closes):
        regime, score = _detect_regime(bear_closes)
        assert regime == "BEAR", f"하락 추세에서 레짐이 BEAR가 아님: {regime}"

    def test_regime_score_range(self, sample_closes):
        regime, score = _detect_regime(sample_closes)
        assert 0 <= score <= 100

    def test_insufficient_data(self):
        short = pd.Series([100, 101, 102], dtype=float)
        regime, score = _detect_regime(short)
        assert regime == "UNKNOWN"
        assert score == 0.0

    def test_valid_regime_values(self, sample_closes):
        regime, _ = _detect_regime(sample_closes)
        assert regime in ("BULL", "BEAR", "SIDEWAYS", "TRANSITION", "UNKNOWN")


class TestMomentumSignal:
    """모멘텀 신호 테스트."""

    def test_bull_positive_score(self, bull_closes, sample_volumes):
        score, signals = _momentum_signal(bull_closes, sample_volumes)
        assert score > 0, f"상승 추세에서 모멘텀 점수가 양수여야 함: {score}"

    def test_score_range(self, sample_closes, sample_volumes):
        score, signals = _momentum_signal(sample_closes, sample_volumes)
        assert -40 <= score <= 40

    def test_returns_list_of_strings(self, sample_closes, sample_volumes):
        score, signals = _momentum_signal(sample_closes, sample_volumes)
        assert isinstance(signals, list)
        for s in signals:
            assert isinstance(s, str)

    def test_insufficient_data(self):
        short = pd.Series([100, 101, 102], dtype=float)
        vols = pd.Series([1000, 1100, 1200], dtype=float)
        score, signals = _momentum_signal(short, vols)
        assert score == 0.0
        assert signals == []


class TestMeanReversionSignal:
    """평균회귀 신호 테스트."""

    def test_oversold_positive_score(self):
        """MA20 대비 크게 하락한 경우 양수 점수."""
        np.random.seed(42)
        # 안정적 가격 후 급락
        prices = [50000.0] * 19 + [42000.0]  # 마지막 가격이 MA20 대비 -16%
        closes = pd.Series(prices, dtype=float)
        score, signals = _mean_reversion_signal(closes)
        assert score > 0, f"과매도 시 양수 점수 기대: {score}"

    def test_overheated_negative_score(self):
        """MA20 대비 크게 상승한 경우 음수 점수."""
        prices = [50000.0] * 19 + [58000.0]  # 마지막 가격이 MA20 대비 +16%
        closes = pd.Series(prices, dtype=float)
        score, signals = _mean_reversion_signal(closes)
        assert score < 0, f"과열 시 음수 점수 기대: {score}"

    def test_score_range(self, sample_closes):
        score, signals = _mean_reversion_signal(sample_closes)
        assert -20 <= score <= 20


class TestCalcSignalScore:
    """종합 시그널 스코어 테스트."""

    def test_score_range(self, sample_closes, sample_volumes):
        result = calc_signal_score(sample_closes, sample_volumes)
        assert 0 <= result.score <= 100

    def test_valid_action_label(self, sample_closes, sample_volumes):
        result = calc_signal_score(sample_closes, sample_volumes)
        assert result.action_label in VALID_ACTION_LABELS, (
            f"유효하지 않은 라벨: {result.action_label}"
        )

    def test_has_breakdown(self, sample_closes, sample_volumes):
        result = calc_signal_score(sample_closes, sample_volumes)
        assert hasattr(result.breakdown, "momentum")
        assert hasattr(result.breakdown, "mean_reversion")
        assert hasattr(result.breakdown, "breakout")
        assert hasattr(result.breakdown, "regime")

    def test_insufficient_data_defaults(self):
        short = pd.Series([100, 101, 102], dtype=float)
        vols = pd.Series([1000, 1100, 1200], dtype=float)
        result = calc_signal_score(short, vols)
        assert result.score == 50.0
        assert result.action_label == "중립"

    def test_regime_in_breakdown(self, sample_closes, sample_volumes):
        result = calc_signal_score(sample_closes, sample_volumes)
        assert result.breakdown.regime in (
            "BULL", "BEAR", "SIDEWAYS", "TRANSITION", "UNKNOWN"
        )


class TestSellSignals:
    """매도 신호 테스트."""

    def test_score_range(self, sample_closes):
        score, signals = _sell_signals(sample_closes)
        assert -55 <= score <= 0

    def test_drawdown_sell(self):
        """20일 고점 대비 하락 시 매도 신호."""
        prices = list(range(50000, 52000, 100)) + [46000.0]  # 마지막에 급락
        closes = pd.Series(prices, dtype=float)
        score, signals = _sell_signals(closes)
        assert score < 0
        assert any("고점 대비" in s for s in signals)

    def test_insufficient_data(self):
        short = pd.Series([100, 101, 102], dtype=float)
        score, signals = _sell_signals(short)
        assert score == 0.0
        assert signals == []

    def test_returns_list_of_strings(self, sample_closes):
        score, signals = _sell_signals(sample_closes)
        assert isinstance(signals, list)
        for s in signals:
            assert isinstance(s, str)

    def test_bear_market_sell_signals(self, bear_closes):
        """하락장에서 매도 신호가 발생해야 함."""
        score, signals = _sell_signals(bear_closes)
        assert score < 0, f"하락장에서 매도 점수가 음수여야 함: {score}"


class TestMultiTimeframeMomentum:
    """다중 시간축 모멘텀 테스트."""

    def test_short_term_momentum(self):
        """5일 단기 모멘텀 감지."""
        prices = [50000.0] * 20 + [52000.0]  # 마지막에 급등
        closes = pd.Series(prices, dtype=float)
        vols = pd.Series([500000.0] * len(prices), dtype=float)
        score, signals = _momentum_signal(closes, vols)
        assert any("5일" in s for s in signals)

    def test_long_term_momentum(self):
        """60일 장기 모멘텀 감지."""
        np.random.seed(42)
        # 60일 이상의 꾸준한 상승
        prices = [50000 * (1 + 0.005 * i) for i in range(70)]
        closes = pd.Series(prices, dtype=float)
        vols = pd.Series([500000.0] * len(prices), dtype=float)
        score, signals = _momentum_signal(closes, vols)
        assert any("60일" in s for s in signals)
