"""Database connection management.

Two modes share the exact same PyMongo API, so services never branch on mode:

* ``mongodb`` — a real MongoDB / MongoDB Atlas cluster (``MONGODB_URI`` set).
* ``memory``  — an in-process mongomock store used when no URI is configured.
  Data is lost on restart; the readiness endpoint and dashboard say so.

If a URI *is* configured but the cluster is unreachable we do NOT silently fall
back to memory (that would hide data loss). The app still starts, readiness
reports ``not_ready``, and data endpoints return 503 until the cluster is back;
PyMongo reconnects automatically.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.schemas.health import ComponentStatus

logger = logging.getLogger("agriguard.db")

COLLECTIONS = (
    "devices",
    "device_commands",
    "telemetry",
    "scans",
    "spray_events",
    "system_logs",
    "users",
    "settings",
    "weather_records",
)


class Database:
    def __init__(self, settings: Settings) -> None:
        self.cfg = settings
        self.mode: Literal["mongodb", "memory"] = (
            "mongodb" if settings.database_configured else "memory"
        )
        self.client: Any = None
        self.db: Any = None
        self.last_error: str | None = None

    # -- lifecycle -------------------------------------------------------------
    def connect(self) -> None:
        if self.mode == "mongodb":
            self.client = MongoClient(
                self.cfg.mongodb_uri,
                serverSelectionTimeoutMS=self.cfg.mongodb_timeout_ms,
                connectTimeoutMS=self.cfg.mongodb_timeout_ms,
                tz_aware=True,
                appname="agriguard-api",
                retryWrites=True,
            )
        else:
            import mongomock  # imported lazily: not needed when Atlas is used

            self.client = mongomock.MongoClient(tz_aware=True)
            logger.warning("MONGODB_URI not set: using NON-PERSISTENT in-memory database")
        self.db = self.client[self.cfg.database_name]
        try:
            self.client.admin.command("ping") if self.mode == "mongodb" else None
            self.ensure_indexes()
            self.last_error = None
        except PyMongoError as exc:
            # Never log the URI (contains credentials); the error type is enough.
            self.last_error = type(exc).__name__
            logger.error("database unreachable at startup", extra={"error": self.last_error})

    def close(self) -> None:
        if self.client is not None:
            self.client.close()

    # -- health ------------------------------------------------------------------
    def check(self) -> ComponentStatus:
        if self.mode == "memory":
            return ComponentStatus(
                status="degraded",
                detail="In-memory database (MONGODB_URI not set): data is lost on restart",
                critical=False,
            )
        try:
            self.client.admin.command("ping")
            if self.last_error:  # recovered after a startup failure
                self.ensure_indexes()
                self.last_error = None
            return ComponentStatus(status="ok", detail="MongoDB reachable")
        except PyMongoError as exc:
            self.last_error = type(exc).__name__
            return ComponentStatus(status="unavailable", detail=f"MongoDB unreachable ({self.last_error})")

    # -- schema --------------------------------------------------------------------
    def ensure_indexes(self) -> None:
        d = self.db
        d.devices.create_index([("token_hash", ASCENDING)], unique=True, sparse=True)
        d.devices.create_index([("last_seen", DESCENDING)])
        d.device_commands.create_index(
            [("device_id", ASCENDING), ("status", ASCENDING), ("created_at", ASCENDING)]
        )
        d.telemetry.create_index([("device_id", ASCENDING), ("ts", DESCENDING)])
        d.telemetry.create_index([("ts", ASCENDING)], expireAfterSeconds=7 * 24 * 3600)
        d.scans.create_index([("created_at", DESCENDING)])
        d.scans.create_index([("device_id", ASCENDING), ("created_at", DESCENDING)])
        d.scans.create_index([("prediction.label", ASCENDING)])
        d.scans.create_index([("decision.outcome", ASCENDING)])
        d.scans.create_index([("idempotency_key", ASCENDING)], unique=True, sparse=True)
        d.spray_events.create_index([("status", ASCENDING), ("created_at", DESCENDING)])
        d.spray_events.create_index([("device_id", ASCENDING), ("created_at", DESCENDING)])
        d.spray_events.create_index([("scan_id", ASCENDING)])
        d.system_logs.create_index(
            [("ts", ASCENDING)], expireAfterSeconds=self.cfg.log_retention_days * 86400
        )
        d.system_logs.create_index([("category", ASCENDING), ("ts", DESCENDING)])
        d.users.create_index([("username", ASCENDING)], unique=True)
        d.weather_records.create_index([("key", ASCENDING), ("fetched_at", DESCENDING)])

    # -- accessors -----------------------------------------------------------------
    def __getattr__(self, name: str) -> Collection:
        if name in COLLECTIONS:
            return self.db[name]
        raise AttributeError(name)
