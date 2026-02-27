import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.v1 import stocks, news, scoring, related, ws
from backend.services import http_client
from backend.services.connection_manager import ConnectionManager
from backend.services.stream_manager import StreamManager

# 싱글턴
connection_manager = ConnectionManager()
stream_manager = StreamManager(connection_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await http_client.startup()
    ws.init(connection_manager, stream_manager)
    await stream_manager.start()
    _cache_task = asyncio.create_task(_periodic_cache_cleanup())
    yield
    # shutdown
    _cache_task.cancel()
    await stream_manager.stop()
    await http_client.shutdown()


async def _periodic_cache_cleanup() -> None:
    """주기적으로 만료된 캐시 엔트리 정리 (5분마다)."""
    from backend.services.cache_service import cache

    while True:
        await asyncio.sleep(300)
        cache.cleanup()


app = FastAPI(
    title="AlphaLens",
    description="국내 주식 분석 및 스코어링 플랫폼",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router, prefix="/api/v1/stocks", tags=["stocks"])
app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(scoring.router, prefix="/api/v1/scoring", tags=["scoring"])
app.include_router(related.router, prefix="/api/v1/related", tags=["related"])
app.include_router(ws.router, prefix="/api/v1", tags=["websocket"])

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
