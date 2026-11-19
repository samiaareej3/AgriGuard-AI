"""Scan submission: validate -> store -> classify -> safety decision -> persist."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pymongo.errors import DuplicateKeyError

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.timeutil import new_id, utcnow
from app.db.client import Database
from app.schemas.scan import ScanOut
from app.services import images
from app.services.audit import AuditLog
from app.services.events import EventBus
from app.services.inference import InferenceService
from app.services.policy import PolicyService
from app.services.spray import SprayService


class ScanService:
    def __init__(self, db: Database, settings: Settings, bus: EventBus, audit: AuditLog,
                 policy: PolicyService, inference: InferenceService, spray: SprayService) -> None:
        self.db, self.settings, self.bus, self.audit = db, settings, bus, audit
        self.policy, self.inference, self.spray = policy, inference, spray

    @staticmethod
    def to_out(doc: dict) -> ScanOut:
        return ScanOut.from_doc(doc)

    def create(
        self, *, data: bytes, filename: str | None, content_type: str | None, source: str,
        device_id: str | None, actor: str, simulated: bool = False,
        idempotency_key: str | None = None, notes: str | None = None,
    ) -> tuple[dict, bool]:
        """Returns (scan_doc, created). Retries with the same idempotency key
        return the original scan instead of creating a duplicate."""
        if idempotency_key:
            existing = self.db.scans.find_one({"idempotency_key": idempotency_key})
            if existing:
                return existing, False

        validated = images.validate_image(
            data, filename, content_type, self.settings.max_upload_bytes, self.settings.max_image_pixels
        )
        quality = images.quality_metrics(validated.image)
        warns, force_uncertain = images.quality_warnings(quality)
        policy = self.policy.get()
        prediction = self.inference.classify(
            validated.image, threshold=policy.confidence_threshold, min_margin=policy.min_confidence_margin,
            extra_warnings=warns, force_uncertain=force_uncertain,
        )

        scan_id = new_id("scan")
        rel_path = images.save_jpeg(validated.image, self.settings.upload_dir, scan_id)
        decision, op_id = self.spray.decide_for_scan(scan_id, prediction, device_id, simulated, actor)

        doc: dict[str, Any] = {
            "_id": scan_id,
            "created_at": utcnow(),
            "source": source,
            "simulated": simulated,
            "device_id": device_id,
            "submitted_by": actor,
            "original_filename": _safe_display_name(filename),
            "content_type": "image/jpeg",
            "size_bytes": validated.size_bytes,
            "image_path": rel_path,
            "quality": quality.model_dump(),
            "prediction": prediction.model_dump(),
            "decision": decision.model_dump(),
            "spray_operation_id": op_id,
            "notes": notes,
        }
        if idempotency_key:
            doc["idempotency_key"] = idempotency_key
        try:
            self.db.scans.insert_one(doc)
        except DuplicateKeyError:  # concurrent retry with the same key won the race
            existing = self.db.scans.find_one({"idempotency_key": idempotency_key})
            if existing:
                return existing, False
            raise

        self.audit.record(
            "scan", "created",
            f"Scan {scan_id}: {prediction.display_label}"
            + (f" ({prediction.confidence:.0%})" if prediction.confidence is not None else "")
            + f" → {decision.outcome}",
            actor=actor, device_id=device_id, simulated=simulated,
            context={"label": prediction.label, "outcome": decision.outcome, "operation_id": op_id},
        )
        self.bus.publish("scan.created", self.to_out(doc).model_dump(), simulated=simulated)
        return doc, True

    def get_doc(self, scan_id: str) -> dict:
        doc = self.db.scans.find_one({"_id": scan_id})
        if doc is None:
            raise NotFoundError("Scan not found")
        return doc

    def image_file(self, scan_id: str) -> Path:
        doc = self.get_doc(scan_id)
        path = (self.settings.upload_dir / doc.get("image_path", "")).resolve()
        root = self.settings.upload_dir.resolve()
        if root not in path.parents or not path.is_file():
            raise NotFoundError("Image no longer available (may have been removed by retention policy)")
        return path

    def list(
        self, *, q: str | None = None, label: str | None = None, outcome: str | None = None,
        device_id: str | None = None, source: str | None = None, date_from: datetime | None = None,
        date_to: datetime | None = None, page: int = 1, page_size: int = 20,
    ) -> tuple[list[dict], int]:
        query: dict[str, Any] = {}
        if label == "uncertain":
            query["prediction.status"] = {"$in": ["UNCERTAIN", "MODEL_UNAVAILABLE"]}
        elif label:
            query["prediction.label"] = label
        if outcome:
            query["decision.outcome"] = outcome
        if device_id:
            query["device_id"] = device_id
        if source:
            query["source"] = source
        if date_from or date_to:
            query["created_at"] = {}
            if date_from:
                query["created_at"]["$gte"] = date_from
            if date_to:
                query["created_at"]["$lte"] = date_to
        if q:
            pattern = re.escape(q.strip()[:64])
            query["$or"] = [
                {"_id": {"$regex": pattern, "$options": "i"}},
                {"original_filename": {"$regex": pattern, "$options": "i"}},
                {"prediction.display_label": {"$regex": pattern, "$options": "i"}},
                {"notes": {"$regex": pattern, "$options": "i"}},
            ]
        total = self.db.scans.count_documents(query)
        docs = list(self.db.scans.find(query).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size))
        return docs, total


def _safe_display_name(name: str | None) -> str | None:
    """Keep only a sanitised basename for display; it is never used as a path."""
    if not name:
        return None
    base = re.split(r"[\\/]", name)[-1]
    return re.sub(r"[^A-Za-z0-9._ -]", "_", base)[:120]
