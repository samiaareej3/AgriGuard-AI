"""Minimal in-process sliding-window rate limiter.

Suitable for a single-instance deployment. For multi-instance deployments use a
shared store (e.g. Redis) or the reverse proxy's limiter (see docs/SECURITY.md).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.errors import AppError


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_s: float = 60.0) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_s:
                hits.popleft()
            if len(hits) >= limit:
                retry = int(window_s - (now - hits[0])) + 1
                raise RateLimitedError(
                    "Too many requests, please slow down", details={"retry_after_s": retry}
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
