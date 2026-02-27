"""WebSocket 연결 및 구독 관리."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 클라이언트 연결 + 종목 구독 관리."""

    def __init__(self) -> None:
        # WebSocket → 구독 중인 종목 코드 set
        self._connections: dict[WebSocket, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[ws] = set()
        logger.info("WS connected: %s (total: %d)", id(ws), len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(ws, None)
        logger.info("WS disconnected: %s (total: %d)", id(ws), len(self._connections))

    async def subscribe(self, ws: WebSocket, code: str) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections[ws].add(code)
        logger.info("WS %s subscribed to %s", id(ws), code)

    async def unsubscribe(self, ws: WebSocket, code: str) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections[ws].discard(code)
        logger.info("WS %s unsubscribed from %s", id(ws), code)

    def get_subscribed_codes(self) -> set[str]:
        """현재 구독 중인 모든 종목 코드 반환 (폴링 대상)."""
        codes: set[str] = set()
        for subs in self._connections.values():
            codes.update(subs)
        return codes

    async def broadcast(self, code: str, event_type: str, data: Any) -> None:
        """해당 종목 구독자 전체에게 메시지 푸시. 끊긴 연결 자동 정리."""
        message = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        dead: list[WebSocket] = []

        # lock 밖에서 snapshot 생성
        async with self._lock:
            targets = [
                ws for ws, subs in self._connections.items() if code in subs
            ]

        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.pop(ws, None)
            logger.info("Cleaned %d dead connections", len(dead))

    async def send_personal(self, ws: WebSocket, event_type: str, data: Any = None) -> None:
        """개별 클라이언트에게 메시지 전송."""
        message = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        await ws.send_text(message)

    @property
    def active_count(self) -> int:
        return len(self._connections)
