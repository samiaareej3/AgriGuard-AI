"""Audit trail: persists significant events to ``system_logs`` and the event bus.

High-frequency events (heartbeats) are NOT written here — only state changes,
decisions, commands, operator actions and errors.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pymongo.errors import PyMongoError

from app.core.logging import request_id_ctx
from app.core.timeutil import new_id, utcnow
from app.db.client import Database
from app.services.events import EventBus

logger = logging.getLogger("agriguard.audit")

Level = Literal["debug", "info", "warning", "error", "critical"]


class AuditLog:
    def __init__(self, db: Database, bus: EventBus) -> None:
        self.db = db
        self.bus = bus

    def record(
        self,
        category: str,
        action: str,
        message: str,
        *,
        level: Level = "info",
        actor: str | None = None,
        device_id: str | None = None,
        simulated: bool = False,
        context: dict[str, Any] | None = None,
    ) -> dict:
        doc = {
            "_id": new_id("log"),
            "ts": utcnow(),
            "level": level,
            "category": category,
            "action": action,
            "message": message,
            "actor": actor,
            "device_id": device_id,
            "simulated": simulated,
            "request_id": request_id_ctx.get(),
            "context": context or {},
        }
        logger.log(
            getattr(logging, level.upper()), message,
            extra={"category": category, "action": action, "actor": actor, "device_id": device_id},
        )
        try:
            self.db.system_logs.insert_one(dict(doc))
        except PyMongoError as exc:  # auditing must never break the main action
            logger.error("failed to persist audit log", extra={"error": type(exc).__name__})
        out = {k: v for k, v in doc.items() if k != "_id"} | {"id": doc["_id"]}
        self.bus.publish("log.created", out, simulated=simulated)
        return out

    def list(
        self,
        *,
        category: str | None = None,
        level: str | None = None,
        device_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        query: dict[str, Any] = {}
        if category:
            query["category"] = category
        if level:
            query["level"] = level
        if device_id:
            query["device_id"] = device_id
        total = self.db.system_logs.count_documents(query)
        cursor = (
            self.db.system_logs.find(query).sort("ts", -1).skip((page - 1) * page_size).limit(page_size)
        )
        return list(cursor), total
