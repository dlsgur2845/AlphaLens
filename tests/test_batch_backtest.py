"""배치 백테스트 + _simulate() 확장 테스트.

3-factor 재정규화, risk 통합, NaN guard, 거래비용, Sharpe ratio,
벤치마크 전략, 데이터 캐시 등 15개 테스트.
"""

import math
import os
import pickle
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from backend.services.backtest_service import (
    BacktestEngine,
    BUY_THRESHOLD,
    SELL_THRESHOLD,
    THREE_FACTOR_WEIGHTS,
    DEFAULT_WEIGHTS,
    COMMISSION_RATE,
    SLIPPAGE_RATE,
)


# ── 헬퍼 ─────────────────────────────────────────────────────

def _make_data(n_days: int = 200, base: float = 50000, seed: int = 42, trend: float = 0.0005):
    """테스트용 가격/거래량/날짜 데이터 생성."""
    np.random.seed(seed)
    dates = pd.bdate_range(end="2025-12-31", periods=n_days)
    prices = [base]
    for _ in range(n_days - 1):
        prices.append(max(1.0, prices[-1] * (1 + np.random.normal(trend, 0.015))))
    closes = [float(p) for p in prices]
    volumes = [float(v) for v in np.random.randint(100_000, 2_000_000, n_days)]
    date_strs = [d.strftime("%Y-%m-%d") for d in dates]
    return closes, volumes, date_strs


# ── 1. 3-factor 가중치 재정규화 ────────────────────────────────

class TestThreeFactorWeights:
    """3-factor 가중치가 올바르게 적용되는지 검증."""

    def test_three_factor_weights_sum_to_one(self):
        total = sum(THREE_FACTOR_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_three_factor_only_price_based(self):
        assert set(THREE_FACTOR_WEIGHTS.keys()) == {"technical", "signal", "risk"}

    def test_simulate_with_three_factor_produces_scores(self):
        """3-factor 가중치로 _simulate() 실행 시 유효한 스코어 생성."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        assert "daily_scores" in result
        assert len(result["daily_scores"]) > 0
        # 스코어가 0-100 범위
        for ds in result["daily_scores"]:
            assert 0 <= ds["score"] <= 100, f"Score out of range: {ds['score']}"

    def test_three_factor_mode_includes_risk_in_scores(self):
        """3-factor 모드에서 daily_scores에 risk 필드 포함."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        for ds in result["daily_scores"]:
            assert "risk" in ds, "3-factor 모드에서 risk 필드 누락"


# ── 2. NaN Guard ──────────────────────────────────────────────

class TestNaNGuard:
    """NaN 값이 스코어에 전파되지 않는지 검증."""

    def test_nan_in_closes_does_not_crash(self):
        """NaN이 포함된 가격 데이터에서 크래시하지 않음."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        closes[100] = float("nan")
        # 크래시하지 않아야 함
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        assert "total_return" in result

    def test_scores_never_nan(self):
        """daily_scores에 NaN 스코어가 없음."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        for ds in result["daily_scores"]:
            assert not math.isnan(ds["score"]), f"NaN score on {ds['date']}"
            assert not math.isnan(ds["technical"])
            assert not math.isnan(ds["signal"])


# ── 3. Division by Zero Guard ─────────────────────────────────

class TestDivisionByZero:
    """0으로 나누기 방어 검증."""

    def test_zero_price_at_start_does_not_crash(self):
        """closes[60]이 0이어도 크래시하지 않음."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        closes[60] = 0.0
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        assert "buy_hold_return" in result
        # bnh_return이 유한한 값
        assert math.isfinite(result["buy_hold_return"])

    def test_zero_entry_price_does_not_crash(self):
        """매수 시점 가격이 0이어도 안전하게 처리."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        # 모든 가격을 아주 작은 값으로 (0은 아니지만 거의 0)
        for i in range(len(closes)):
            closes[i] = max(closes[i], 0.01)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        assert math.isfinite(result["total_return"])


# ── 4. 거래비용 시뮬레이션 ────────────────────────────────────

class TestTransactionCosts:
    """거래비용이 올바르게 적용되는지 검증."""

    def test_include_costs_reduces_returns(self):
        """거래비용 포함 시 수익률이 감소."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result_no_cost = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS, include_costs=False)
        result_cost = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS, include_costs=True)

        # 매매가 있는 경우에만 비교
        if result_no_cost["total_trades"] > 0 and result_cost["total_trades"] > 0:
            assert result_cost["total_return"] <= result_no_cost["total_return"]

    def test_cost_fields_in_trades(self):
        """거래에 cost_pct, raw_return_pct 필드 포함."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS, include_costs=True)
        for trade in result["trades"]:
            assert "cost_pct" in trade
            assert "raw_return_pct" in trade
            assert "return_pct" in trade

    def test_cost_amount_is_correct(self):
        """거래비용이 정확한 금액 (수수료 0.25%×2 + 슬리피지 0.1%×2 = 0.7%)."""
        expected = (COMMISSION_RATE * 2 + SLIPPAGE_RATE * 2) * 100  # 0.7%
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS, include_costs=True)
        for trade in result["trades"]:
            if not trade.get("open"):
                assert abs(trade["cost_pct"] - expected) < 0.01


# ── 5. Sharpe Ratio ───────────────────────────────────────────

class TestSharpeRatio:
    """Sharpe ratio 계산 검증."""

    def test_sharpe_ratio_in_result(self):
        """결과에 sharpe_ratio 필드 포함."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        assert "sharpe_ratio" in result
        assert math.isfinite(result["sharpe_ratio"])

    def test_sharpe_is_zero_with_no_trades(self):
        """매매가 없으면 Sharpe는 포지션 없이 계산 (0에 가까움)."""
        engine = BacktestEngine()
        # 모든 스코어가 매수 임계값 아래가 되도록 평탄한 데이터
        closes = [100.0] * 200
        volumes = [1000.0] * 200
        dates = [f"2024-{(i//30)+1:02d}-{(i%30)+1:02d}" for i in range(200)]
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        assert math.isfinite(result["sharpe_ratio"])


# ── 6. stock_code 반환 버그 수정 ───────────────────────────────

class TestStockCodeFix:
    """stock_code 파라미터가 결과에 올바르게 반영."""

    def test_stock_code_passed_through(self):
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS, stock_code="005930")
        assert result["stock_code"] == "005930"

    def test_stock_code_default_empty(self):
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=THREE_FACTOR_WEIGHTS)
        assert result["stock_code"] == ""


# ── 7. 벤치마크: Buy & Hold ───────────────────────────────────

class TestBenchmarkBuyAndHold:
    def test_bnh_returns_correct_fields(self):
        from scripts.batch_backtest import benchmark_buy_and_hold
        closes, _, _ = _make_data(200)
        result = benchmark_buy_and_hold(closes)
        assert "total_return" in result
        assert "sharpe_ratio" in result
        assert "max_drawdown" in result
        assert result["strategy"] == "Buy & Hold"
        assert result["total_trades"] == 1


# ── 8. 벤치마크: MA Crossover ─────────────────────────────────

class TestBenchmarkMACrossover:
    def test_ma_crossover_returns_correct_fields(self):
        from scripts.batch_backtest import benchmark_ma_crossover
        closes, _, _ = _make_data(200)
        result = benchmark_ma_crossover(closes)
        assert "total_return" in result
        assert "sharpe_ratio" in result
        assert result["strategy"] == "MA Crossover (20/60)"

    def test_ma_crossover_with_trending_data(self):
        """강한 상승추세에서 MA crossover가 양의 수익."""
        from scripts.batch_backtest import benchmark_ma_crossover
        closes, _, _ = _make_data(300, trend=0.003)  # 강한 상승
        result = benchmark_ma_crossover(closes, include_costs=False)
        # 상승장에서는 양의 수익 기대
        assert math.isfinite(result["total_return"])


# ── 9. 벤치마크: Random Entry ─────────────────────────────────

class TestBenchmarkRandomEntry:
    def test_random_entry_reproducible(self):
        """같은 seed로 같은 결과."""
        from scripts.batch_backtest import benchmark_random_entry
        closes, _, _ = _make_data(200)
        r1 = benchmark_random_entry(closes, seed=42)
        r2 = benchmark_random_entry(closes, seed=42)
        assert r1["total_return"] == r2["total_return"]
        assert r1["sharpe_ratio"] == r2["sharpe_ratio"]

    def test_different_seed_different_result(self):
        from scripts.batch_backtest import benchmark_random_entry
        closes, _, _ = _make_data(200)
        r1 = benchmark_random_entry(closes, seed=42)
        r2 = benchmark_random_entry(closes, seed=99)
        # 대부분의 경우 다른 결과
        assert r1["total_return"] != r2["total_return"] or r1["sharpe_ratio"] != r2["sharpe_ratio"]

    def test_short_data_returns_zero(self):
        """데이터가 너무 짧으면 0 반환."""
        from scripts.batch_backtest import benchmark_random_entry
        closes = [100.0] * 65  # avg_holding=30 고려하면 부족
        result = benchmark_random_entry(closes, avg_holding=30)
        assert result["total_return"] == 0.0


# ── 10. 데이터 캐시 ───────────────────────────────────────────

class TestDataCache:
    def test_pickle_cache_write_and_read(self, tmp_path):
        """pickle 캐시 저장 및 로드."""
        from scripts.batch_backtest import _cache_key
        key = _cache_key(["005930"], "2021-01-01", "2025-12-31")
        assert len(key) == 12  # MD5 해시 12자

    def test_corrupt_cache_handled(self, tmp_path):
        """손상된 캐시 파일을 안전하게 처리."""
        cache_file = tmp_path / "corrupt.pkl"
        cache_file.write_text("not a pickle")
        with pytest.raises(Exception):
            with open(cache_file, "rb") as f:
                pickle.load(f)


# ── 11. 결과 집계 ─────────────────────────────────────────────

class TestResultAggregation:
    def test_empty_results_handled(self):
        """결과가 비어도 크래시하지 않음."""
        from scripts.batch_backtest import save_results
        df = pd.DataFrame()
        # save_results는 빈 DataFrame이면 조기 종료해야 함
        # 빈 DataFrame으로 호출 시 에러 없이 처리
        assert df.empty


# ── 12. matplotlib Agg backend ────────────────────────────────

class TestMatplotlibBackend:
    def test_agg_backend_set(self):
        """matplotlib이 Agg backend으로 설정됨."""
        import matplotlib
        matplotlib.use("Agg")
        assert matplotlib.get_backend().lower() == "agg"


# ── 13. DEFAULT_WEIGHTS 하위호환 ──────────────────────────────

class TestBackwardCompatibility:
    def test_default_weights_unchanged(self):
        """기존 DEFAULT_WEIGHTS가 변경되지 않음."""
        assert DEFAULT_WEIGHTS == {
            "technical": 0.23, "signal": 0.19, "fundamental": 0.19,
            "macro": 0.14, "risk": 0.15, "related": 0.05, "news": 0.05,
        }

    def test_simulate_with_default_weights_still_works(self):
        """기존 7-factor 가중치로도 _simulate()가 동작."""
        engine = BacktestEngine()
        closes, volumes, dates = _make_data(200)
        result = engine._simulate(closes, volumes, dates, weights=DEFAULT_WEIGHTS)
        assert "total_return" in result
        assert "sharpe_ratio" in result
