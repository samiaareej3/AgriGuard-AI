"""In-process real-time event bus feeding the dashboard WebSocket.

``publish`` is safe to call from worker threads (sync endpoints, simulator
ticks): events are handed to the event loop with ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.core.timeutil import new_id, utcnow


class EventBus:
    def __init__(self, history: int = 200, queue_size: int = 500) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._recent: deque[dict[str, Any]] = deque(maxlen=history)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()
        self._queue_size = queue_size

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event_type: str, data: dict[str, Any] | None = None, *, simulated: bool = False) -> dict:
        event = jsonable_encoder({
            "id": new_id("evt"),
            "type": event_type,
            "ts": utcnow(),
            "simulated": simulated,
            "data": data or {},
        })
        with self._lock:
            self._recent.append(event)
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                self._fanout(event)
            else:
                loop.call_soon_threadsafe(self._fanout, event)
        return event

    def _fanout(self, event: dict) -> None:
        for queue in list(self._subscribers):
            if queue.full():  # slow consumer: drop oldest rather than block
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._recent)[-limit:]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
