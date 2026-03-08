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

from backend.api.v1 import stocks, news, scoring, related, recommendations, geopolitical, backtest, ws, portfolio
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

    # 종목 리스트 미리 로드 (첫 요청 지연 방지)
    try:
        from backend.services.stock_service import _get_stock_list
        stocks = await _get_stock_list()
        logger.info("Preloaded %d stocks", len(stocks))
    except Exception as e:
        logger.warning("Stock list preload failed: %s", e)

    # FinBERT 모델 미리 로드 (첫 뉴스 요청 지연 방지)
    try:
        from backend.services.finbert_service import finbert
        if finbert.available:
            finbert.analyze("테스트")  # warm-up
            logger.info("FinBERT model preloaded")
    except ImportError:
        pass
    except Exception as e:
        logger.warning("FinBERT preload failed: %s", e)

    yield
    # shutdown
    stop_scheduler()
    _cache_task.cancel()
    await stream_manager.stop()
    await http_client.shutdown()
    await close_db()

    # LLM 클라이언트 종료
    try:
        from backend.services.llm_service import llm
        await llm.close()
    except ImportError:
        pass


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

class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """API 요청 전체 타임아웃 미들웨어 (무한 로딩 방지)."""

    DEFAULT_TIMEOUT = 45  # 일반 API 기본 타임아웃
    LONG_TIMEOUT_PREFIXES = [
        ("/api/v1/recommendations", 90),
        ("/api/v1/geopolitical", 60),
        ("/api/v1/scoring", 60),
        ("/api/v1/related", 60),
        ("/api/v1/backtest", 90),
        ("/api/v1/portfolio", 120),
    ]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        timeout = self.DEFAULT_TIMEOUT
        for prefix, t in self.LONG_TIMEOUT_PREFIXES:
            if path.startswith(prefix):
                timeout = t
                break
        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Request timeout (%ds): %s", timeout, path)
            return Response(
                content='{"detail":"요청 처리 시간이 초과되었습니다"}',
                status_code=504,
                media_type="application/json",
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
app.add_middleware(RequestTimeoutMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=settings.rate_limit_per_minute)

@app.get("/api/v1/health", tags=["health"])
async def health_check():
    llm_available = False
    try:
        from backend.services.llm_service import llm
        llm_available = llm.available
    except ImportError:
        pass
    return {"status": "ok", "llm_available": llm_available}


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


import os as _os
import psutil as _psutil

# 시스템 모니터링: 백그라운드 스레드에서 1초 간격 측정 (컨테이너 cgroup 기준)
_system_stats_cache: dict = {}


def _read_cgroup_cpu():
    """cgroup v2 기반 컨테이너 CPU 사용률 측정."""
    try:
        # cgroup v2: cpu.stat
        with open("/sys/fs/cgroup/cpu.stat") as f:
            stats = {}
            for line in f:
                k, v = line.strip().split()
                stats[k] = int(v)
        return stats.get("usage_usec")
    except FileNotFoundError:
        pass
    try:
        # cgroup v1 fallback
        with open("/sys/fs/cgroup/cpuacct/cpuacct.usage") as f:
            return int(f.read().strip()) // 1000  # ns -> usec
    except FileNotFoundError:
        return None


def _read_cgroup_memory():
    """cgroup 기반 컨테이너 메모리 사용량."""
    try:
        # cgroup v2
        with open("/sys/fs/cgroup/memory.current") as f:
            used = int(f.read().strip())
        try:
            with open("/sys/fs/cgroup/memory.max") as f:
                val = f.read().strip()
                limit = int(val) if val != "max" else _psutil.virtual_memory().total
        except FileNotFoundError:
            limit = _psutil.virtual_memory().total
        return used, limit
    except FileNotFoundError:
        pass
    try:
        # cgroup v1 fallback
        with open("/sys/fs/cgroup/memory/memory.usage_in_bytes") as f:
            used = int(f.read().strip())
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as f:
            limit = int(f.read().strip())
            if limit > _psutil.virtual_memory().total:
                limit = _psutil.virtual_memory().total
        return used, limit
    except FileNotFoundError:
        mem = _psutil.virtual_memory()
        return mem.used, mem.total


def _update_system_stats():
    """백그라운드 스레드에서 주기적으로 컨테이너 지표 수집."""
    import threading
    import time as _t

    _prev_cpu = _read_cgroup_cpu()
    _prev_time = _t.monotonic()
    cpu_count = _os.cpu_count() or 1

    def _loop():
        nonlocal _prev_cpu, _prev_time
        while True:
            try:
                # CPU: cgroup usage delta 기반 계산
                cur_cpu = _read_cgroup_cpu()
                cur_time = _t.monotonic()
                if cur_cpu is not None and _prev_cpu is not None:
                    delta_usec = cur_cpu - _prev_cpu
                    delta_sec = cur_time - _prev_time
                    # 사용률 = (사용 시간 / 경과 시간 / CPU 수) * 100
                    cpu_pct = (delta_usec / 1_000_000) / delta_sec / cpu_count * 100
                    cpu_pct = min(round(cpu_pct, 1), 100.0)
                else:
                    cpu_pct = round(_psutil.cpu_percent(interval=None, percpu=False), 1)
                _prev_cpu = cur_cpu
                _prev_time = cur_time

                # Memory: cgroup 기반
                mem_used, mem_total = _read_cgroup_memory()
                mem_pct = round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0

                _system_stats_cache.update({
                    "cpu_percent": cpu_pct,
                    "cpu_count": cpu_count,
                    "memory_total": mem_total,
                    "memory_used": mem_used,
                    "memory_percent": mem_pct,
                })
            except Exception:
                pass
            _t.sleep(1)
    t = threading.Thread(target=_loop, daemon=True)
    t.start()


_update_system_stats()


@app.get("/api/v1/system/stats", tags=["monitoring"])
async def system_stats():
    """컨테이너 CPU/메모리 사용량 반환 (1초 간격 백그라운드 측정)."""
    if not _system_stats_cache:
        mem_used, mem_total = _read_cgroup_memory()
        return {
            "cpu_percent": round(_psutil.cpu_percent(interval=0.5), 1),
            "cpu_count": _os.cpu_count() or 1,
            "memory_total": mem_total,
            "memory_used": mem_used,
            "memory_percent": round(mem_used / mem_total * 100, 1) if mem_total > 0 else 0,
        }
    return _system_stats_cache


app.include_router(stocks.router, prefix="/api/v1/stocks", tags=["stocks"])
app.include_router(news.router, prefix="/api/v1/news", tags=["news"])
app.include_router(scoring.router, prefix="/api/v1/scoring", tags=["scoring"])
app.include_router(related.router, prefix="/api/v1/related", tags=["related"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["recommendations"])
app.include_router(geopolitical.router, prefix="/api/v1/geopolitical", tags=["geopolitical"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["backtest"])
app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["portfolio"])
app.include_router(ws.router, prefix="/api/v1", tags=["websocket"])

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
