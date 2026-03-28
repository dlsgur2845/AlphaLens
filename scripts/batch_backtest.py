"""알파 검증 배치 백테스트 — 3-factor 모델 vs 벤치마크 성과 비교.

Usage:
    python -m scripts.batch_backtest [--top N] [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--no-cache]

Output:
    docs/backtest_results.csv   — 종목별 성과 요약
    docs/backtest_summary.png   — 벤치마크 비교 차트
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import pickle
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 디스플레이 없는 환경 대응
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.backtest_service import (
    BacktestEngine,
    THREE_FACTOR_WEIGHTS,
    BUY_THRESHOLD,
    SELL_THRESHOLD,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

CACHE_DIR = PROJECT_ROOT / ".backtest_cache"
DOCS_DIR = PROJECT_ROOT / "docs"

# ─── 벤치마크 전략 ───────────────────────────────────────────

def benchmark_buy_and_hold(closes: list[float], start_idx: int = 60) -> dict:
    """매수 후 보유 전략."""
    base = closes[start_idx] if closes[start_idx] > 0 else 1.0
    total_return = (closes[-1] - base) / base * 100
    daily_rets = []
    for i in range(start_idx + 1, len(closes)):
        if closes[i - 1] > 0:
            daily_rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
        else:
            daily_rets.append(0.0)
    sharpe = _calc_sharpe(daily_rets)
    mdd = _calc_mdd(closes[start_idx:])
    return {
        "strategy": "Buy & Hold",
        "total_return": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(mdd, 2),
        "total_trades": 1,
    }


def benchmark_ma_crossover(
    closes: list[float],
    short_period: int = 20,
    long_period: int = 60,
    start_idx: int = 60,
    include_costs: bool = True,
) -> dict:
    """이동평균 골든/데드 크로스 전략."""
    from backend.services.backtest_service import COMMISSION_RATE, SLIPPAGE_RATE

    trades: list[float] = []
    position = None
    daily_rets: list[float] = []

    for i in range(start_idx, len(closes)):
        if i < long_period:
            daily_rets.append(0.0)
            continue

        ma_short = np.mean(closes[i - short_period + 1 : i + 1])
        ma_long = np.mean(closes[i - long_period + 1 : i + 1])

        prev_short = np.mean(closes[i - short_period : i])
        prev_long = np.mean(closes[i - long_period : i])

        # 포지션 보유 중 일별 수익률
        if position is not None and closes[i - 1] > 0:
            daily_rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
        else:
            daily_rets.append(0.0)

        # 골든 크로스: 매수
        if position is None and prev_short <= prev_long and ma_short > ma_long:
            position = closes[i]

        # 데드 크로스: 매도
        elif position is not None and prev_short >= prev_long and ma_short < ma_long:
            raw_ret = (closes[i] - position) / position * 100 if position > 0 else 0.0
            cost = (COMMISSION_RATE * 2 + SLIPPAGE_RATE * 2) * 100 if include_costs else 0.0
            trades.append(raw_ret - cost)
            position = None

    # 미청산 처리
    if position is not None and position > 0:
        raw_ret = (closes[-1] - position) / position * 100
        cost = (COMMISSION_RATE + SLIPPAGE_RATE) * 100 if include_costs else 0.0
        trades.append(raw_ret - cost)

    cumulative = 1.0
    for r in trades:
        cumulative *= (1 + r / 100)
    total_return = (cumulative - 1) * 100

    sharpe = _calc_sharpe(daily_rets)
    mdd = _calc_mdd(closes[start_idx:])

    return {
        "strategy": "MA Crossover (20/60)",
        "total_return": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown": round(mdd, 2),
        "total_trades": len(trades),
    }


def benchmark_random_entry(
    closes: list[float],
    seed: int = 42,
    n_trials: int = 1000,
    avg_holding: int = 30,
    start_idx: int = 60,
    include_costs: bool = True,
) -> dict:
    """랜덤 진입 전략 (Monte Carlo 시뮬레이션)."""
    from backend.services.backtest_service import COMMISSION_RATE, SLIPPAGE_RATE

    rng = np.random.RandomState(seed)
    trial_returns: list[float] = []
    trial_sharpes: list[float] = []
    tradeable_range = len(closes) - start_idx - avg_holding

    if tradeable_range <= 0:
        return {
            "strategy": f"Random Entry (seed={seed}, {n_trials} trials)",
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "total_trades": 0,
        }

    for _ in range(n_trials):
        n_trades = rng.randint(3, 10)
        trade_rets: list[float] = []
        daily_rets: list[float] = []

        for _ in range(n_trades):
            entry_idx = rng.randint(start_idx, start_idx + tradeable_range)
            hold = max(5, int(rng.exponential(avg_holding)))
            exit_idx = min(entry_idx + hold, len(closes) - 1)

            if closes[entry_idx] > 0:
                raw_ret = (closes[exit_idx] - closes[entry_idx]) / closes[entry_idx] * 100
                cost = (COMMISSION_RATE * 2 + SLIPPAGE_RATE * 2) * 100 if include_costs else 0.0
                trade_rets.append(raw_ret - cost)

                for j in range(entry_idx + 1, exit_idx + 1):
                    if closes[j - 1] > 0:
                        daily_rets.append((closes[j] - closes[j - 1]) / closes[j - 1])

        cumulative = 1.0
        for r in trade_rets:
            cumulative *= (1 + r / 100)
        trial_returns.append((cumulative - 1) * 100)
        trial_sharpes.append(_calc_sharpe(daily_rets))

    mdd = _calc_mdd(closes[start_idx:])
    return {
        "strategy": f"Random Entry (seed={seed}, {n_trials} trials)",
        "total_return": round(float(np.mean(trial_returns)), 2),
        "sharpe_ratio": round(float(np.mean(trial_sharpes)), 3),
        "max_drawdown": round(mdd, 2),
        "total_trades": n_trials,
    }


# ─── 유틸리티 ────────────────────────────────────────────────

def _calc_sharpe(daily_returns: list[float], risk_free_annual: float = 0.03) -> float:
    if not daily_returns:
        return 0.0
    dr = np.array(daily_returns)
    daily_rf = risk_free_annual / 252
    excess = dr - daily_rf
    std = np.std(excess)
    if std == 0:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(252))


def _calc_mdd(prices: list[float]) -> float:
    peak = prices[0] if prices and prices[0] > 0 else 1.0
    max_dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = (peak - p) / peak * 100 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


# ─── 데이터 캐시 ─────────────────────────────────────────────

def _cache_key(codes: list[str], start: str, end: str) -> str:
    raw = f"{sorted(codes)}-{start}-{end}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def download_prices(
    codes: list[str],
    start_date: str,
    end_date: str,
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """yfinance에서 가격 데이터를 다운로드 (pickle 캐시 지원)."""
    if yf is None:
        raise RuntimeError("yfinance가 필요합니다: pip install yfinance")

    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"prices_{_cache_key(codes, start_date, end_date)}.pkl"

    if use_cache and cache_file.exists():
        try:
            with open(cache_file, "rb") as f:
                data = pickle.load(f)
            logger.info(f"캐시 로드: {cache_file.name} ({len(data)}종목)")
            return data
        except Exception:
            logger.warning("캐시 파일 손상, 재다운로드")
            cache_file.unlink(missing_ok=True)

    data: dict[str, pd.DataFrame] = {}
    for i, code in enumerate(codes):
        logger.info(f"[{i+1}/{len(codes)}] {code} 다운로드 중...")
        try:
            ticker = yf.Ticker(f"{code}.KS")
            hist = ticker.history(start=start_date, end=end_date)
            if hist.empty:
                ticker = yf.Ticker(f"{code}.KQ")
                hist = ticker.history(start=start_date, end=end_date)
            if not hist.empty and len(hist) >= 60:
                data[code] = hist
            else:
                logger.warning(f"  {code}: 데이터 부족 ({len(hist)}일)")
        except Exception as e:
            logger.error(f"  {code}: 다운로드 실패 — {e}")

        # rate limit 대응
        if (i + 1) % 10 == 0:
            time.sleep(1.0)
        else:
            time.sleep(0.3)

    # 캐시 저장
    if data:
        with open(cache_file, "wb") as f:
            pickle.dump(data, f)
        logger.info(f"캐시 저장: {cache_file.name} ({len(data)}종목)")

    return data


# ─── 메인 실행 ────────────────────────────────────────────────

def get_top_stocks(n: int = 100) -> list[str]:
    """stock_service에서 상위 N개 종목 코드를 가져옴."""
    try:
        from backend.services.stock_service import _stock_list_cache
        if _stock_list_cache:
            codes = [s["code"] for s in _stock_list_cache[:n]]
            if codes:
                return codes
    except Exception:
        pass

    # fallback: 네이버 금융에서 시가총액 상위 종목
    logger.info("stock_service 캐시 없음, 대표 종목 사용")
    return [
        "005930", "000660", "373220", "207940", "005380",
        "006400", "035420", "000270", "068270", "051910",
        "005490", "035720", "105560", "028260", "012330",
        "003670", "055550", "066570", "032830", "086790",
        "096770", "034730", "003550", "015760", "017670",
        "316140", "033780", "009150", "018260", "011200",
    ][:n]


def run_batch(
    top_n: int = 100,
    start_date: str = "2021-01-01",
    end_date: str = "2025-12-31",
    use_cache: bool = True,
) -> pd.DataFrame:
    """배치 백테스트 실행 → DataFrame 반환."""
    engine = BacktestEngine()
    codes = get_top_stocks(top_n)
    logger.info(f"대상 종목: {len(codes)}개, 기간: {start_date} ~ {end_date}")

    # 가격 데이터 다운로드
    price_data = download_prices(codes, start_date, end_date, use_cache)
    if not price_data:
        logger.error("다운로드된 종목 없음. 종료.")
        return pd.DataFrame()

    logger.info(f"데이터 확보: {len(price_data)}/{len(codes)}종목")

    results = []
    for i, (code, hist) in enumerate(price_data.items()):
        logger.info(f"[{i+1}/{len(price_data)}] {code} 백테스트 중...")
        try:
            closes = hist["Close"].values.tolist()
            volumes = hist["Volume"].values.tolist()
            dates = [d.strftime("%Y-%m-%d") for d in hist.index]

            # 데이터 완성도 체크 (결측 10% 초과 시 스킵)
            total_expected = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days * 5 / 7
            if len(closes) < total_expected * 0.9 * 0.5:  # 최소 45%
                logger.warning(f"  {code}: 데이터 완성도 부족, 스킵")
                continue

            # AlphaLens 3-factor 백테스트
            al_result = engine._simulate(
                closes, volumes, dates,
                weights=THREE_FACTOR_WEIGHTS,
                stock_code=code,
                include_costs=True,
            )

            # 벤치마크
            bnh = benchmark_buy_and_hold(closes)
            ma = benchmark_ma_crossover(closes, include_costs=True)
            rand = benchmark_random_entry(closes, include_costs=True)

            results.append({
                "code": code,
                "days": al_result["trading_days"],
                "al_return": al_result["total_return"],
                "al_sharpe": al_result["sharpe_ratio"],
                "al_mdd": al_result["max_drawdown"],
                "al_trades": al_result["total_trades"],
                "al_win_rate": al_result["win_rate"],
                "bnh_return": bnh["total_return"],
                "bnh_sharpe": bnh["sharpe_ratio"],
                "ma_return": ma["total_return"],
                "ma_sharpe": ma["sharpe_ratio"],
                "ma_trades": ma["total_trades"],
                "rand_return": rand["total_return"],
                "rand_sharpe": rand["sharpe_ratio"],
                "excess_vs_bnh": round(al_result["total_return"] - bnh["total_return"], 2),
                "excess_vs_ma": round(al_result["total_return"] - ma["total_return"], 2),
            })

        except Exception as e:
            logger.error(f"  {code}: 백테스트 실패 — {e}")
            continue

    if not results:
        logger.error("성공한 종목 없음.")
        return pd.DataFrame()

    df = pd.DataFrame(results)
    return df


def save_results(df: pd.DataFrame, output_dir: Path | None = None) -> None:
    """결과를 CSV와 차트로 저장."""
    out = output_dir or DOCS_DIR
    out.mkdir(exist_ok=True)

    # CSV 저장
    csv_path = out / "backtest_results.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info(f"CSV 저장: {csv_path}")

    # 요약 통계
    print("\n" + "=" * 60)
    print("  AlphaLens 3-Factor 알파 검증 결과")
    print("=" * 60)
    print(f"  검증 종목 수: {len(df)}")
    print(f"  ---")
    print(f"  AlphaLens 평균 수익률: {df['al_return'].mean():.2f}%")
    print(f"  AlphaLens 평균 Sharpe: {df['al_sharpe'].mean():.3f}")
    print(f"  B&H 평균 수익률:       {df['bnh_return'].mean():.2f}%")
    print(f"  B&H 평균 Sharpe:       {df['bnh_sharpe'].mean():.3f}")
    print(f"  MA 평균 수익률:        {df['ma_return'].mean():.2f}%")
    print(f"  MA 평균 Sharpe:        {df['ma_sharpe'].mean():.3f}")
    print(f"  Random 평균 수익률:    {df['rand_return'].mean():.2f}%")
    print(f"  Random 평균 Sharpe:    {df['rand_sharpe'].mean():.3f}")
    print(f"  ---")
    sharpe_delta = df['al_sharpe'].mean() - df['bnh_sharpe'].mean()
    print(f"  Sharpe 차이 (AL - B&H): {sharpe_delta:.3f}")
    beat_bnh = (df['al_return'] > df['bnh_return']).sum()
    beat_ma = (df['al_return'] > df['ma_return']).sum()
    print(f"  B&H 대비 우위 종목:    {beat_bnh}/{len(df)} ({beat_bnh/len(df)*100:.0f}%)")
    print(f"  MA 대비 우위 종목:     {beat_ma}/{len(df)} ({beat_ma/len(df)*100:.0f}%)")
    print(f"  평균 거래 횟수:        {df['al_trades'].mean():.1f}")
    print(f"  평균 승률:             {df['al_win_rate'].mean():.1f}%")

    # 성공 기준 체크
    print(f"\n  {'=' * 40}")
    print(f"  성공 기준 체크:")
    ok1 = sharpe_delta >= 0.3
    print(f"  {'PASS' if ok1 else 'FAIL'} Sharpe(AL) - Sharpe(B&H) >= 0.3: {sharpe_delta:.3f}")
    ok2 = df['al_return'].mean() > df['ma_return'].mean()
    print(f"  {'PASS' if ok2 else 'FAIL'} 연평균 수익률 > MA: {df['al_return'].mean():.2f}% vs {df['ma_return'].mean():.2f}%")
    ok3 = df['al_return'].mean() > 0
    print(f"  {'PASS' if ok3 else 'FAIL'} 거래비용 포함 양의 알파: {df['al_return'].mean():.2f}%")
    print("=" * 60)

    # 차트 생성
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("AlphaLens 3-Factor Alpha Verification", fontsize=14, fontweight="bold")

    # 1. 수익률 비교 (박스플롯)
    ax = axes[0, 0]
    bp_data = [df["al_return"], df["bnh_return"], df["ma_return"], df["rand_return"]]
    bp = ax.boxplot(bp_data, labels=["AlphaLens", "B&H", "MA(20/60)", "Random"], patch_artist=True)
    colors = ["#4CAF50", "#2196F3", "#FF9800", "#9E9E9E"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.set_title("Total Return Distribution (%)")
    ax.axhline(y=0, color="red", linestyle="--", alpha=0.5)
    ax.grid(True, alpha=0.3)

    # 2. Sharpe ratio 비교
    ax = axes[0, 1]
    strategies = ["AlphaLens", "B&H", "MA(20/60)", "Random"]
    sharpes = [df["al_sharpe"].mean(), df["bnh_sharpe"].mean(), df["ma_sharpe"].mean(), df["rand_sharpe"].mean()]
    bars = ax.bar(strategies, sharpes, color=colors, alpha=0.7)
    ax.set_title("Average Sharpe Ratio")
    ax.axhline(y=0, color="red", linestyle="--", alpha=0.5)
    ax.grid(True, alpha=0.3)
    for bar, val in zip(bars, sharpes):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, f"{val:.3f}", ha="center", fontsize=9)

    # 3. 초과수익률 분포 (AL vs B&H)
    ax = axes[1, 0]
    ax.hist(df["excess_vs_bnh"], bins=20, color="#4CAF50", alpha=0.7, edgecolor="black")
    ax.axvline(x=0, color="red", linestyle="--", linewidth=2)
    ax.set_title("Excess Return vs B&H (%)")
    ax.set_xlabel("Excess Return (%)")
    ax.set_ylabel("Count")
    ax.grid(True, alpha=0.3)

    # 4. 승률 vs 거래횟수
    ax = axes[1, 1]
    scatter = ax.scatter(df["al_trades"], df["al_win_rate"], c=df["al_return"],
                         cmap="RdYlGn", alpha=0.7, edgecolors="black", linewidth=0.5)
    ax.set_title("Win Rate vs Trade Count")
    ax.set_xlabel("Total Trades")
    ax.set_ylabel("Win Rate (%)")
    ax.axhline(y=50, color="gray", linestyle="--", alpha=0.5)
    plt.colorbar(scatter, ax=ax, label="Total Return (%)")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    chart_path = out / "backtest_summary.png"
    fig.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"차트 저장: {chart_path}")


def main():
    parser = argparse.ArgumentParser(description="AlphaLens 3-Factor 알파 검증 배치 백테스트")
    parser.add_argument("--top", type=int, default=30, help="상위 N개 종목 (기본: 30)")
    parser.add_argument("--start", default="2021-01-01", help="시작일 (기본: 2021-01-01)")
    parser.add_argument("--end", default="2025-12-31", help="종료일 (기본: 2025-12-31)")
    parser.add_argument("--no-cache", action="store_true", help="캐시 사용 안 함")
    args = parser.parse_args()

    df = run_batch(
        top_n=args.top,
        start_date=args.start,
        end_date=args.end,
        use_cache=not args.no_cache,
    )

    if df.empty:
        print("결과 없음. 데이터를 확인하세요.")
        sys.exit(1)

    save_results(df)


if __name__ == "__main__":
    main()
