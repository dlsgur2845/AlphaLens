"""백테스팅 서비스 - 6-팩터 모델 성과 검증 프레임워크."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# 거래 규칙
BUY_THRESHOLD = 65   # 매수 진입 점수
SELL_THRESHOLD = 35   # 매도 청산 점수
INITIAL_CAPITAL = 100_000_000  # 1억원

# 기본 가중치
DEFAULT_WEIGHTS = {
    "technical": 0.23, "signal": 0.19, "fundamental": 0.19,
    "macro": 0.14, "risk": 0.15, "related": 0.05, "news": 0.05,
}


class BacktestEngine:
    """백테스팅 엔진: 6-팩터 모델의 과거 성과를 검증."""

    async def run_backtest(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        weights: Optional[dict] = None,
    ) -> dict:
        """종목 백테스트 실행.

        1. yfinance로 해당 기간 일봉 데이터 조회 (KRX 종목코드 -> {code}.KS)
        2. 매 거래일 technical score + signal score 계산
           (fundamental, macro, risk는 느리게 변하므로 50 고정)
        3. 스코어 기반 매수/매도 시뮬레이션
        4. 성과 지표 산출
        """
        # yfinance 데이터 조회 (KRX -> .KS, 코스닥 -> .KQ)
        ticker = yf.Ticker(f"{stock_code}.KS")
        hist = ticker.history(start=start_date, end=end_date)

        if hist.empty:
            ticker = yf.Ticker(f"{stock_code}.KQ")
            hist = ticker.history(start=start_date, end=end_date)

        if len(hist) < 60:
            return {"error": "insufficient_data", "message": "최소 60 거래일 필요"}

        closes = hist["Close"].values.tolist()
        volumes = hist["Volume"].values.tolist()
        dates = [d.strftime("%Y-%m-%d") for d in hist.index]

        return self._simulate(closes, volumes, dates, weights)

    def _simulate(
        self,
        closes: list[float],
        volumes: list[float],
        dates: list[str],
        weights: Optional[dict] = None,
    ) -> dict:
        """매매 시뮬레이션 + 성과 지표 산출 (테스트 가능한 순수 로직)."""
        from backend.utils.technical import calc_technical_score
        from backend.services.signal_service import calc_signal_score

        w = weights or DEFAULT_WEIGHTS.copy()

        trades: list[dict] = []
        position: Optional[dict] = None
        daily_scores: list[dict] = []

        for i in range(60, len(closes)):
            window_closes = pd.Series(closes[: i + 1], dtype=float)
            window_volumes = pd.Series(volumes[: i + 1], dtype=float)

            tech_score, _ = calc_technical_score(window_closes, window_volumes)

            sig_result = calc_signal_score(window_closes, window_volumes)
            sig_score = sig_result.score if hasattr(sig_result, "score") else 50.0

            # 간이 종합 점수 (tech + signal 가중 평균, 다른 팩터는 50 고정)
            total = (
                tech_score * w.get("technical", 0.23)
                + sig_score * w.get("signal", 0.19)
                + 50 * w.get("fundamental", 0.19)
                + 50 * w.get("macro", 0.14)
                + 50 * w.get("risk", 0.15)
                + 50 * w.get("related", 0.05)
                + 50 * w.get("news", 0.05)
            )

            daily_scores.append({
                "date": dates[i],
                "close": closes[i],
                "score": round(total, 1),
                "technical": round(tech_score, 1),
                "signal": round(sig_score, 1),
            })

            # 매매 시뮬레이션
            if position is None and total >= BUY_THRESHOLD:
                position = {
                    "entry_date": dates[i],
                    "entry_price": closes[i],
                    "entry_score": total,
                }
            elif position is not None and total <= SELL_THRESHOLD:
                ret = (closes[i] - position["entry_price"]) / position["entry_price"] * 100
                holding = sum(
                    1 for d in dates if position["entry_date"] <= d <= dates[i]
                )
                trades.append({
                    "entry_date": position["entry_date"],
                    "exit_date": dates[i],
                    "entry_price": round(position["entry_price"]),
                    "exit_price": round(closes[i]),
                    "return_pct": round(ret, 2),
                    "score_at_entry": round(position["entry_score"], 1),
                    "holding_days": holding,
                })
                position = None

        # 미청산 포지션 처리
        if position is not None:
            ret = (closes[-1] - position["entry_price"]) / position["entry_price"] * 100
            holding = sum(
                1 for d in dates if position["entry_date"] <= d <= dates[-1]
            )
            trades.append({
                "entry_date": position["entry_date"],
                "exit_date": dates[-1],
                "entry_price": round(position["entry_price"]),
                "exit_price": round(closes[-1]),
                "return_pct": round(ret, 2),
                "score_at_entry": round(position["entry_score"], 1),
                "holding_days": holding,
                "open": True,
            })

        # 성과 지표 산출
        returns = [t["return_pct"] for t in trades]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]

        # Buy & Hold 비교
        bnh_return = (closes[-1] - closes[60]) / closes[60] * 100

        # 누적 수익률 (복리)
        cumulative = 1.0
        for r in returns:
            cumulative *= (1 + r / 100)
        total_return = (cumulative - 1) * 100

        # MDD 계산
        peak = closes[60]
        max_dd = 0.0
        for c in closes[60:]:
            if c > peak:
                peak = c
            dd = (peak - c) / peak * 100
            if dd > max_dd:
                max_dd = dd

        trading_days = len(closes) - 60
        years = trading_days / 252
        annual_return = (
            ((1 + total_return / 100) ** (1 / max(years, 0.1)) - 1) * 100
            if years > 0
            else 0
        )

        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 0.0
        pl_ratio = round(abs(avg_win / avg_loss), 2) if wins and losses and avg_loss != 0 else 0.0

        return {
            "stock_code": dates[0].split("-")[0] if dates else "",  # placeholder
            "period": f"{dates[0]} ~ {dates[-1]}" if dates else "",
            "trading_days": trading_days,
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "buy_hold_return": round(bnh_return, 2),
            "excess_return": round(total_return - bnh_return, 2),
            "max_drawdown": round(max_dd, 2),
            "total_trades": len(trades),
            "win_rate": round(len(wins) / max(len(trades), 1) * 100, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_loss_ratio": pl_ratio,
            "trades": trades,
            "daily_scores": daily_scores,
        }

    async def sensitivity_analysis(
        self,
        stock_code: str,
        start_date: str = "2024-01-01",
        end_date: str = "2025-12-31",
    ) -> dict:
        """가중치 민감도 분석.

        각 팩터 가중치를 +/-10%p 범위에서 5%p 단위로 변경,
        다른 팩터는 비례 조정하여 합 = 1.0 유지.
        """
        base_weights = DEFAULT_WEIGHTS.copy()

        results: dict = {
            "base": await self.run_backtest(stock_code, start_date, end_date, base_weights),
        }
        parameter_impacts: dict = {}

        for factor in ["technical", "signal", "fundamental", "macro", "risk"]:
            base_w = base_weights[factor]
            variations = []

            for delta in [-0.10, -0.05, 0.0, 0.05, 0.10]:
                new_w = max(0.05, min(0.40, base_w + delta))
                remaining = 1.0 - new_w
                other_total = sum(v for k, v in base_weights.items() if k != factor)
                adjusted = {}
                for k, v in base_weights.items():
                    if k == factor:
                        adjusted[k] = new_w
                    else:
                        adjusted[k] = v / other_total * remaining

                bt = await self.run_backtest(stock_code, start_date, end_date, adjusted)
                variations.append({
                    "weight": round(new_w, 2),
                    "total_return": bt.get("total_return", 0),
                    "win_rate": bt.get("win_rate", 0),
                    "max_drawdown": bt.get("max_drawdown", 0),
                })

            best = max(variations, key=lambda x: x["total_return"])
            parameter_impacts[factor] = {
                "base_weight": base_w,
                "variations": variations,
                "optimal_weight": best["weight"],
                "optimal_return": best["total_return"],
            }

        results["parameter_impacts"] = parameter_impacts
        results["warning"] = (
            "최적 가중치는 과적합(overfitting) 위험이 있습니다. "
            "다양한 종목/기간에서 교차 검증 필요."
        )
        return results

    async def attribution_analysis(
        self,
        stock_code: str,
        start_date: str = "2024-01-01",
        end_date: str = "2025-12-31",
    ) -> dict:
        """팩터 기여도 분해 분석.

        각 팩터를 제외(가중치 0)하고 백테스트 -> 성과 차이 = 해당 팩터 기여도.
        """
        base = await self.run_backtest(stock_code, start_date, end_date)
        base_return = base.get("total_return", 0)

        contributions: dict = {}
        for factor in ["technical", "signal", "fundamental", "macro", "risk", "related", "news"]:
            modified_weights = DEFAULT_WEIGHTS.copy()
            modified_weights[factor] = 0.0
            remaining = sum(modified_weights.values())
            if remaining > 0:
                for k in modified_weights:
                    modified_weights[k] /= remaining

            bt = await self.run_backtest(stock_code, start_date, end_date, modified_weights)
            diff = base_return - bt.get("total_return", 0)
            contributions[factor] = round(diff, 2)

        total_contribution = sum(abs(v) for v in contributions.values())
        normalized: dict = {}
        if total_contribution > 0:
            for k, v in contributions.items():
                normalized[k] = round(v / total_contribution * 100, 1)

        return {
            "stock_code": stock_code,
            "period": f"{start_date} ~ {end_date}",
            "base_return": base_return,
            "factor_contributions": contributions,
            "normalized_contributions": normalized,
            "warning": (
                "귀인 분석은 근사적 방법으로, "
                "팩터 간 상호작용 효과는 별도 분석 필요."
            ),
        }


# 싱글턴
backtest_engine = BacktestEngine()
