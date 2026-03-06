"""LLM 클라이언트 — Docker Model Runner (OpenAI-compatible API).

Graceful fallback: LLM_BASE_URL 미설정 또는 장애 시 모든 호출이 None 반환.
CircuitBreaker + LRU 캐시 적용.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

# ── CircuitBreaker ──

_CB_THRESHOLD = 3  # 연속 실패 횟수
_CB_RESET_TIMEOUT = 120  # open → half-open 전환 (초)


class _CircuitBreaker:
    __slots__ = ("failures", "last_failure", "state")

    def __init__(self):
        self.failures = 0
        self.last_failure = 0.0
        self.state = "closed"  # closed | open | half-open

    def record_success(self):
        self.failures = 0
        self.state = "closed"

    def record_failure(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= _CB_THRESHOLD:
            self.state = "open"
            logger.warning("LLM CircuitBreaker → OPEN (failures=%d)", self.failures)

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure >= _CB_RESET_TIMEOUT:
                self.state = "half-open"
                return True
            return False
        # half-open: 1회 시도 허용
        return True


# ── LRU 캐시 ──

_CACHE_MAX = 500


class _LLMCache:
    __slots__ = ("_store", "_max")

    def __init__(self, maxsize: int = _CACHE_MAX):
        self._store: dict[str, tuple[float, any]] = {}
        self._max = maxsize

    def _make_key(self, messages: list[dict], **kwargs) -> str:
        raw = json.dumps(messages, ensure_ascii=False, sort_keys=True)
        raw += json.dumps(kwargs, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str, ttl: int) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: str):
        if len(self._store) >= self._max:
            # 가장 오래된 항목 제거
            oldest = min(self._store, key=lambda k: self._store[k][0])
            del self._store[oldest]
        self._store[key] = (time.time(), value)


# ── LLM Service ──

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


class LLMService:
    """OpenAI-compatible LLM 클라이언트 (Docker Model Runner 용)."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._cb = _CircuitBreaker()
        self._cache = _LLMCache()

    @property
    def available(self) -> bool:
        return bool(settings.llm_base_url)

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=settings.llm_base_url,
                timeout=httpx.Timeout(settings.llm_timeout, connect=10.0),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str | None:
        """일반 텍스트 응답. 실패 시 None 반환."""
        if not self.available:
            return None

        if not self._cb.allow_request():
            logger.debug("LLM CircuitBreaker OPEN — skipping request")
            return None

        temp = temperature if temperature is not None else settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

        # 캐시 확인
        cache_key = self._cache._make_key(messages, t=temp, m=tokens)
        cached = self._cache.get(cache_key, settings.llm_cache_ttl)
        if cached is not None:
            return cached

        try:
            client = self._ensure_client()
            resp = await client.post(
                "/chat/completions",
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "temperature": temp,
                    "max_tokens": tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            self._cb.record_success()
            self._cache.set(cache_key, content)
            return content

        except Exception as e:
            self._cb.record_failure()
            logger.warning("LLM chat failed: %s", e)
            return None

    async def chat_json(
        self,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict | None:
        """JSON 응답 파싱. markdown 코드블록 자동 처리. 실패 시 None."""
        content = await self.chat(
            messages, temperature=temperature, max_tokens=max_tokens,
        )
        if content is None:
            return None

        text = content.strip()

        # markdown 코드블록 제거
        match = _CODE_BLOCK_RE.search(text)
        if match:
            text = match.group(1).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM JSON parse failed, raw=%s", text[:200])
            return None


# 싱글톤
llm = LLMService()
