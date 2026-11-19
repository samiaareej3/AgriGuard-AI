"""UTC time helpers. All timestamps in AgriGuard are timezone-aware UTC."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def utcnow() -> datetime:
    # Millisecond precision: MongoDB stores datetimes with ms resolution, so
    # truncating here keeps in-memory and persisted values identical.
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def ensure_utc(value: datetime | None) -> datetime | None:
    """MongoDB may return naive datetimes (implicitly UTC); make them aware."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def new_id(prefix: str) -> str:
    """Readable, collision-resistant string IDs, e.g. ``scan_3f2a...``."""
    return f"{prefix}_{uuid.uuid4().hex[:20]}"
