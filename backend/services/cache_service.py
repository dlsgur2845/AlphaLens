from __future__ import annotations

import time
from typing import Any


MAX_CACHE_SIZE = 500


class CacheService:
    """Simple in-memory TTL cache with LRU eviction."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float, float]] = {}  # key -> (value, expires_at, created_at)

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at, _created_at = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def get_with_age(self, key: str) -> tuple[Any | None, float | None]:
        """캐시 값과 경과 시간(초)을 반환. 미스 시 (None, None)."""
        entry = self._store.get(key)
        if entry is None:
            return None, None
        value, expires_at, created_at = entry
        now = time.time()
        if now > expires_at:
            del self._store[key]
            return None, None
        return value, round(now - created_at, 1)

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        now = time.time()
        self._store[key] = (value, now + ttl, now)
        if len(self._store) > MAX_CACHE_SIZE:
            self.cleanup()
            if len(self._store) > MAX_CACHE_SIZE:
                sorted_keys = sorted(
                    self._store.keys(),
                    key=lambda k: self._store[k][2],  # created_at
                )
                for k in sorted_keys[: len(self._store) // 10]:
                    del self._store[k]

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def cleanup(self) -> int:
        """Remove expired entries. Returns count of removed items."""
        now = time.time()
        expired = [k for k, (_, exp, _c) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]
        return len(expired)


cache = CacheService()
