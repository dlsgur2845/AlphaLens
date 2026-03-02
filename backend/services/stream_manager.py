"""백그라운드 폴링 + 변경 감지 엔진."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from backend.services.cache_service import cache
from backend.services.connection_manager import ConnectionManager
from backend.services.http_client import get_mobile_client

logger = logging.getLogger(__name__)

# 폴링 간격 (초)
PRICE_INTERVAL_OPEN = 5
PRICE_INTERVAL_CLOSED = 30
NEWS_INTERVAL = 60


class StreamManager:
    """네이버 API 폴링 → 변경 감지 → 구독자 브로드캐스트."""

    def __init__(self, conn_mgr: ConnectionManager) -> None:
        self._conn_mgr = conn_mgr
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # 변경 감지용 마지막 상태
        self._last_prices: dict[str, dict] = {}
        self._last_news_ids: dict[str, set[str]] = {}

        # 동시 접근 보호 및 디바운스
        self._lock = asyncio.Lock()
        self._recalc_debounce: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(self._price_loop()),
            asyncio.create_task(self._news_loop()),
        ]
        logger.info("StreamManager started")

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("StreamManager stopped")

    async def _cleanup_stale(self, active_codes: set[str]) -> None:
        """구독 해제된 종목의 캐시 데이터 정리."""
        async with self._lock:
            for code in list(self._last_prices.keys()):
                if code not in active_codes:
                    del self._last_prices[code]
            for code in list(self._last_news_ids.keys()):
                if code not in active_codes:
                    del self._last_news_ids[code]

    # ── 가격 폴링 루프 ──────────────────────────────

    async def _price_loop(self) -> None:
        while self._running:
            try:
                codes = self._conn_mgr.get_subscribed_codes()
                await self._cleanup_stale(codes)
                if codes:
                    await self._poll_prices(codes)

                # 마지막 폴링 결과에서 시장 상태 확인하여 간격 조절
                interval = self._get_price_interval()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Price loop error")
                await asyncio.sleep(5)

    async def _poll_prices(self, codes: set[str]) -> None:
        client = get_mobile_client()

        async def _poll_one(code: str) -> None:
            try:
                resp = await client.get(
                    f"https://m.stock.naver.com/api/stock/{code}/basic",
                )
                basic = resp.json()
                price_data = self._parse_price(code, basic)
                if price_data is None:
                    return

                # 변경 감지 (Lock으로 보호)
                async with self._lock:
                    last = self._last_prices.get(code)
                    changed = (
                        last is None
                        or last.get("price") != price_data["price"]
                        or last.get("volume") != price_data["volume"]
                    )

                    if changed:
                        self._last_prices[code] = price_data

                if changed:
                    # 캐시 무효화 → 다음 HTTP 요청도 최신 데이터
                    cache.delete(f"detail:{code}")
                    cache.delete(f"scoring:{code}")

                    # 브로드캐스트
                    await self._conn_mgr.broadcast(code, "price_update", price_data)

                    # 스코어링 재계산 (디바운스)
                    asyncio.create_task(self._debounced_recalc(code))

            except Exception:
                logger.debug("Price poll failed for %s", code, exc_info=True)

        await asyncio.gather(*[_poll_one(code) for code in codes])

    def _parse_price(self, code: str, basic: dict) -> dict | None:
        try:
            name = basic.get("stockName", "")
            if not name:
                return None

            price = int(basic.get("closePrice", "0").replace(",", ""))
            change_raw = basic.get("compareToPreviousClosePrice", "0").replace(",", "")
            change = int(change_raw)

            direction = basic.get("compareToPreviousPrice", {}).get("name", "")
            if direction in ("FALLING", "LOWER_LIMIT"):
                change = -abs(change)

            change_pct = float(basic.get("fluctuationsRatio", "0"))
            if change < 0:
                change_pct = -abs(change_pct)

            volume_str = basic.get("accumulatedTradingVolume", "0")
            if isinstance(volume_str, str):
                volume_str = volume_str.replace(",", "")
            try:
                volume = int(volume_str)
            except (ValueError, TypeError):
                volume = 0

            market_status = basic.get("marketStatus", "CLOSE")

            # 가격 방향 (상승/하락/보합)
            if change > 0:
                price_direction = "up"
            elif change < 0:
                price_direction = "down"
            else:
                price_direction = "flat"

            return {
                "code": code,
                "name": name,
                "price": price,
                "change": change,
                "change_pct": change_pct,
                "volume": volume,
                "market_status": market_status,
                "price_direction": price_direction,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception:
            return None

    def _get_price_interval(self) -> int:
        """마지막 폴링된 시장 상태 기반으로 간격 결정."""
        for data in self._last_prices.values():
            if data.get("market_status") == "OPEN":
                return PRICE_INTERVAL_OPEN
        return PRICE_INTERVAL_CLOSED

    # ── 뉴스 폴링 루프 ──────────────────────────────

    async def _news_loop(self) -> None:
        while self._running:
            try:
                codes = self._conn_mgr.get_subscribed_codes()
                if codes:
                    await self._poll_news(codes)
                await asyncio.sleep(NEWS_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("News loop error")
                await asyncio.sleep(10)

    async def _poll_news(self, codes: set[str]) -> None:
        from backend.services.news_service import get_stock_news

        async def _poll_one_news(code: str) -> None:
            try:
                cache.delete(f"news:{code}:20")
                news_result = await get_stock_news(code, max_articles=20)

                current_ids = {a.link for a in news_result.articles}
                async with self._lock:
                    last_ids = self._last_news_ids.get(code, set())
                    new_ids = current_ids - last_ids
                    self._last_news_ids[code] = current_ids

                if not last_ids:
                    return

                if new_ids:
                    new_articles = [
                        {
                            "title": a.title,
                            "link": a.link,
                            "source": a.source,
                            "date": a.date,
                            "sentiment_score": a.sentiment_score,
                            "sentiment_label": a.sentiment_label,
                        }
                        for a in news_result.articles
                        if a.link in new_ids
                    ]

                    await self._conn_mgr.broadcast(code, "news_update", {
                        "code": code,
                        "new_articles": new_articles,
                        "overall_sentiment": news_result.overall_sentiment,
                        "overall_label": news_result.overall_label,
                        "positive_count": news_result.positive_count,
                        "negative_count": news_result.negative_count,
                        "neutral_count": news_result.neutral_count,
                    })

                    cache.delete(f"scoring:{code}")
                    asyncio.create_task(self._debounced_recalc(code))

            except Exception:
                logger.debug("News poll failed for %s", code, exc_info=True)

        await asyncio.gather(*[_poll_one_news(code) for code in codes], return_exceptions=True)

    # ── 스코어링 재계산 (디바운스) ──────────────────

    async def _debounced_recalc(self, code: str) -> None:
        """디바운스된 스코어링 재계산 트리거."""
        if code in self._recalc_debounce:
            self._recalc_debounce[code].cancel()
        self._recalc_debounce[code] = asyncio.create_task(self._delayed_recalc(code))

    async def _delayed_recalc(self, code: str) -> None:
        """1초 대기 후 실제 재계산 실행."""
        await asyncio.sleep(1.0)
        await self._recalc_scoring(code)
        self._recalc_debounce.pop(code, None)

    async def _recalc_scoring(self, code: str) -> None:
        try:
            from backend.services.scoring_service import calculate_score

            result = await calculate_score(code)
            await self._conn_mgr.broadcast(code, "scoring_update", {
                "code": result.code,
                "total_score": result.total_score,
                "signal": result.signal,
                "action_label": result.action_label,
                "risk_grade": result.risk_grade,
                "breakdown": {
                    "technical": result.breakdown.technical,
                    "news_sentiment": result.breakdown.news_sentiment,
                    "fundamental": result.breakdown.fundamental,
                    "related_momentum": result.breakdown.related_momentum,
                    "macro": result.breakdown.macro,
                    "signal": result.breakdown.signal,
                    "risk": result.breakdown.risk,
                },
                "updated_at": result.updated_at,
            })
        except Exception:
            logger.debug("Scoring recalc failed for %s", code, exc_info=True)
