"""APScheduler 기반 주기적 배치 작업."""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def refresh_stock_list():
    """종목 목록 갱신 (6시간마다)."""
    try:
        from backend.services.stock_service import _get_stock_list
        stocks = await _get_stock_list()
        logger.info("Stock list refreshed: %d stocks", len(stocks) if stocks else 0)
    except Exception as e:
        logger.warning("Stock list refresh failed: %s", e)


async def cleanup_cache():
    """캐시 정리 (5분마다)."""
    try:
        from backend.services.cache_service import cache
        cache.cleanup()
    except Exception as e:
        logger.warning("Cache cleanup failed: %s", e)


def start_scheduler():
    """스케줄러 시작."""
    scheduler.add_job(refresh_stock_list, "interval", hours=6, id="refresh_stocks", replace_existing=True)
    scheduler.add_job(cleanup_cache, "interval", minutes=5, id="cleanup_cache", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))


def stop_scheduler():
    """스케줄러 중지."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
