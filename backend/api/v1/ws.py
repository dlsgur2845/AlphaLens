"""WebSocket 엔드포인트 - 실시간 스트리밍."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.connection_manager import ConnectionManager
from backend.services.stream_manager import StreamManager

logger = logging.getLogger(__name__)

router = APIRouter()

# main.py에서 lifespan 시 주입
connection_manager: ConnectionManager | None = None
stream_manager: StreamManager | None = None


def init(conn_mgr: ConnectionManager, strm_mgr: StreamManager) -> None:
    """싱글턴 주입."""
    global connection_manager, stream_manager
    connection_manager = conn_mgr
    stream_manager = strm_mgr


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    if connection_manager is None:
        await ws.close(code=1011, reason="Server not ready")
        return

    await connection_manager.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await connection_manager.send_personal(ws, "error", {"message": "Invalid JSON"})
                continue

            action = msg.get("action", "")
            code = msg.get("code", "")

            if action == "subscribe" and code:
                await connection_manager.subscribe(ws, code)
                await connection_manager.send_personal(ws, "subscribed", {"code": code})

            elif action == "unsubscribe" and code:
                await connection_manager.unsubscribe(ws, code)
                await connection_manager.send_personal(ws, "unsubscribed", {"code": code})

            elif action == "ping":
                await connection_manager.send_personal(ws, "pong")

            else:
                await connection_manager.send_personal(
                    ws, "error", {"message": f"Unknown action: {action}"}
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("WS error", exc_info=True)
    finally:
        await connection_manager.disconnect(ws)
