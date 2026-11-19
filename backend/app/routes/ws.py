"""Real-time event stream for the dashboard.

Connect: ``ws://<host>/api/v1/ws/events?token=<bearer token>``
Frames are JSON: ``{"id", "type", "ts", "simulated", "data"}``. The server
sends a ``hello`` frame first and a ``ping`` frame every 20 s when idle.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.timeutil import utcnow
from app.routes.deps import user_from_token

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/events")
async def events(websocket: WebSocket) -> None:
    services = websocket.app.state.services
    user = user_from_token(services, websocket.query_params.get("token"))
    if user is None:
        await websocket.close(code=4401, reason="unauthorized")
        return
    await websocket.accept()
    queue = services.bus.subscribe()
    try:
        await websocket.send_json({"type": "hello", "ts": utcnow().isoformat(), "data": {"user": user.username}})
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "ts": utcnow().isoformat(), "data": {}})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        services.bus.unsubscribe(queue)
