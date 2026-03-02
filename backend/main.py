import asyncio
import json
import logging
import sys
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from backend.api.v1 import stocks, news, scoring, related, recommendations, geopolitical, backtest, ws
from backend.config import settings
from backend.services import http_client
from backend.utils.auth import create_access_token
from backend.services.connection_manager import ConnectionManager
from backend.services.stream_manager import StreamManager

# 싱글턴
connection_manager = ConnectionManager()
stream_manager = StreamManager(connection_manager)

# Prometheus-compatible metrics
_metrics = {
    "requests_total": defaultdict(int),
    "errors_total": defaultdict(int),
}

logger = logging.getLogger(__name__)


class JsonFormatter(logging.Formatter):
    """JSON 구조화 로그 포매터."""

    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    await http_client.startup()
    ws.init(connection_manager, stream_manager)
    await stream_manager.start()
    _cache_task = asyncio.create_task(_periodic_cache_cleanup())

    from backend.services.database import init_db, close_db
    from backend.services.scheduler import start_scheduler, stop_scheduler

    await init_db()
    start_scheduler()

    yield
    # shutdown
    stop_scheduler()
    _cache_task.cancel()
    await stream_manager.stop()
    await http_client.shutdown()
    await close_db()


async def _periodic_cache_cleanup() -> None:
    """주기적으로 만료된 캐시 엔트리 정리 (5분마다)."""
    from backend.services.cache_service import cache

    while True:
        await asyncio.sleep(300)
        try:
            cache.cleanup()
        except Exception as e:
            logger.warning("Cache cleanup failed: %s", e)


app = FastAPI(
    title="AlphaLens",
    description="국내 주식 분석 및 스코어링 플랫폼",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self' wss:; "
            "font-src 'self' https://cdn.jsdelivr.net"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 60, window: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        _metrics["requests_total"][path] += 1

        if path.startswith("/api/"):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()

            # 5분마다 오래된 IP 엔트리 전체 정리
            if now - self._last_cleanup > 300:
                expired = [ip for ip, ts in self._requests.items()
                          if not ts or now - ts[-1] > self.window]
                for ip in expired:
                    del self._requests[ip]
                self._last_cleanup = now

            self._requests[client_ip] = [
                t for t in self._requests[client_ip] if now - t < self.window
            ]
            if len(self._requests[client_ip]) >= self.max_requests:
                _metrics["errors_total"][path] += 1
                return Response("Too Many Requests", status_code=429)
            self._requests[client_ip].append(now)

        response = await call_next(request)
        if response.status_code >= 400:
            _metrics["errors_total"][path] += 1
        return response


origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=settings.rate_limit_per_minute)

@app.get("/api/v1/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


@app.post("/api/v1/auth/token", tags=["auth"])
async def get_token(x_api_key: str = Header(default="")):
    """API Key로 JWT 토큰 발급."""
    if not settings.jwt_secret:
        raise HTTPException(status_code=404, detail="JWT not enabled")
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    token = create_access_token()
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/v1/metrics", tags=["monitoring"])
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    lines = []
    lines.append("# HELP alphalens_requests_total Total HTTP requests")
    lines.append("# TYPE alphalens_requests_total counter")
    for path, count in _metrics["requests_total"].items():
        lines.append(f'alphalens_requests_total{{path="{path}"}} {count}')

    lines.append("# HELP alphalens_errors_total Total HTTP errors")
    lines.append("# TYPE alphalens_errors_total counter")
    for path, count in _metrics["errors_total"].items():
        lines.append(f'alphalens_errors_total{{path="{path}"}} {count}')

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")


app.include_router(stocks.router, prefix="/api/v1/stocks", tags=["stocks"])
app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(scoring.router, prefix="/api/v1/scoring", tags=["scoring"])
app.include_router(related.router, prefix="/api/v1/related", tags=["related"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["recommendations"])
app.include_router(geopolitical.router, prefix="/api/v1/geopolitical", tags=["geopolitical"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["backtest"])
app.include_router(ws.router, prefix="/api/v1", tags=["websocket"])

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
