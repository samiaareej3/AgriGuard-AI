"""Retention: delete uploaded images older than UPLOAD_RETENTION_DAYS.

Scan records are kept (their ``image_path`` then returns 404 "no longer
available"). System logs and telemetry expire via MongoDB TTL indexes; the
in-memory store does not enforce TTL, so they are also purged here.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from pathlib import Path

from app.core.timeutil import utcnow
from app.db.client import Database

logger = logging.getLogger("agriguard.retention")


def cleanup(db: Database, upload_dir: Path, upload_days: int, log_days: int) -> dict[str, int]:
    removed = 0
    cutoff = time.time() - upload_days * 86400
    if upload_dir.exists():
        for path in upload_dir.rglob("*.jpg"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    logs = db.system_logs.delete_many({"ts": {"$lt": utcnow() - timedelta(days=log_days)}}).deleted_count
    tel = db.telemetry.delete_many({"ts": {"$lt": utcnow() - timedelta(days=7)}}).deleted_count
    if removed or logs or tel:
        logger.info("retention cleanup", extra={"images": removed, "logs": logs, "telemetry": tel})
    return {"images": removed, "logs": logs, "telemetry": tel}
