"""공유 httpx.AsyncClient - 커넥션 풀링으로 성능 최적화."""

from __future__ import annotations

import httpx

DESKTOP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/16.6 Mobile/15E148 Safari/604.1"
    ),
}

# 앱 수명 동안 재사용되는 싱글톤 클라이언트
_desktop_client: httpx.AsyncClient | None = None
_mobile_client: httpx.AsyncClient | None = None


async def startup() -> None:
    """앱 시작 시 호출 - 클라이언트 생성."""
    global _desktop_client, _mobile_client
    _desktop_client = httpx.AsyncClient(
        headers=DESKTOP_HEADERS,
        timeout=15.0,
        limits=httpx.Limits(max_connections=30, max_keepalive_connections=15),
    )
    _mobile_client = httpx.AsyncClient(
        headers=MOBILE_HEADERS,
        timeout=10.0,
        limits=httpx.Limits(max_connections=30, max_keepalive_connections=15),
    )


async def shutdown() -> None:
    """앱 종료 시 호출 - 클라이언트 정리."""
    global _desktop_client, _mobile_client
    if _desktop_client:
        await _desktop_client.aclose()
        _desktop_client = None
    if _mobile_client:
        await _mobile_client.aclose()
        _mobile_client = None


def get_desktop_client() -> httpx.AsyncClient:
    """데스크톱 UA 클라이언트 (네이버 금융 웹, KRX 등)."""
    if _desktop_client is None:
        raise RuntimeError("HTTP client not initialized. Call startup() first.")
    return _desktop_client


def get_mobile_client() -> httpx.AsyncClient:
    """모바일 UA 클라이언트 (네이버 금융 모바일 API)."""
    if _mobile_client is None:
        raise RuntimeError("HTTP client not initialized. Call startup() first.")
    return _mobile_client
