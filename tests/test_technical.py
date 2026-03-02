"""기술적 지표 단위 테스트."""
import numpy as np
import pandas as pd
import pytest

from backend.utils.technical import (
    calc_bollinger_bands,
    calc_macd,
    calc_rsi,
    calc_technical_score,
)


class TestCalcRsi:
    """RSI 계산 테스트."""

    def test_rsi_range(self, sample_closes):
        rsi = calc_rsi(sample_closes)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_rsi_bull_above_50(self, bull_closes):
        rsi = calc_rsi(bull_closes)
        assert rsi is not None
        assert rsi > 50, f"상승 추세에서 RSI가 50 이하: {rsi}"

    def test_rsi_bear_below_50(self, bear_closes):
        rsi = calc_rsi(bear_closes)
        assert rsi is not None
        assert rsi < 50, f"하락 추세에서 RSI가 50 이상: {rsi}"

    def test_rsi_insufficient_data(self):
        short = pd.Series([100, 101, 102], dtype=float)
        assert calc_rsi(short) is None

    def test_rsi_constant_price(self):
        flat = pd.Series([50000.0] * 30, dtype=float)
        rsi = calc_rsi(flat)
        # 변화 없으면 gain=0, loss=0 -> RS=NaN 또는 50 근처
        # 실제로 0/0이면 None 반환 가능
        if rsi is not None:
            assert 0 <= rsi <= 100


class TestCalcMacd:
    """MACD 계산 테스트."""

    def test_macd_returns_dict(self, sample_closes):
        result = calc_macd(sample_closes)
        assert result is not None
        assert isinstance(result, dict)

    def test_macd_has_keys(self, sample_closes):
        result = calc_macd(sample_closes)
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result
        assert "bullish" in result
        assert "crossover" in result
        assert "crossunder" in result

    def test_macd_types(self, sample_closes):
        result = calc_macd(sample_closes)
        assert isinstance(result["macd"], float)
        assert isinstance(result["signal"], float)
        assert isinstance(result["histogram"], float)
        assert isinstance(result["bullish"], bool)

    def test_macd_histogram_consistency(self, sample_closes):
        result = calc_macd(sample_closes)
        expected_hist = round(result["macd"] - result["signal"], 2)
        assert abs(result["histogram"] - expected_hist) < 0.02

    def test_macd_insufficient_data(self):
        short = pd.Series([100, 101, 102], dtype=float)
        assert calc_macd(short) is None


class TestCalcBollingerBands:
    """볼린저 밴드 테스트."""

    def test_bb_order(self, sample_closes):
        bb = calc_bollinger_bands(sample_closes)
        assert bb is not None
        assert bb["upper"] > bb["middle"] > bb["lower"]

    def test_bb_has_keys(self, sample_closes):
        bb = calc_bollinger_bands(sample_closes)
        assert "upper" in bb
        assert "middle" in bb
        assert "lower" in bb
        assert "bandwidth" in bb
        assert "pct_b" in bb

    def test_bb_bandwidth_positive(self, sample_closes):
        bb = calc_bollinger_bands(sample_closes)
        assert bb["bandwidth"] > 0

    def test_bb_insufficient_data(self):
        short = pd.Series([100, 101, 102], dtype=float)
        assert calc_bollinger_bands(short) is None


class TestCalcTechnicalScore:
    """기술적 분석 종합 점수 테스트."""

    def test_returns_tuple(self, sample_closes, sample_volumes):
        result = calc_technical_score(sample_closes, sample_volumes)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_score_range(self, sample_closes, sample_volumes):
        score, details = calc_technical_score(sample_closes, sample_volumes)
        assert 0 <= score <= 100

    def test_details_is_dict(self, sample_closes, sample_volumes):
        score, details = calc_technical_score(sample_closes, sample_volumes)
        assert isinstance(details, dict)

    def test_details_has_components(self, sample_closes, sample_volumes):
        score, details = calc_technical_score(sample_closes, sample_volumes)
        assert "moving_averages" in details
        assert "rsi" in details
        assert "macd" in details
        assert "bollinger_bands" in details

    def test_bull_score_above_neutral(self, bull_closes, sample_volumes):
        """상승 추세 데이터의 기술 점수가 중립(50) 부근 이상."""
        np.random.seed(99)
        bull_score, details = calc_technical_score(bull_closes, sample_volumes)
        # 상승 추세에서 MA 정배열 등 긍정 신호가 반영됨
        assert bull_score >= 40, (
            f"상승 추세 점수가 40 이상이어야 함: {bull_score}"
        )
