"""Spray-operation lifecycle.

    scan ──► safety.evaluate ──► BLOCKED / PENDING_APPROVAL / (AUTHORIZED ─► dispatch)
    PENDING_APPROVAL ──approve──► re-evaluate ALL rules ──► DISPATCHED or BLOCKED
    DISPATCHED ──device ack──► RUNNING ──device result──► COMPLETED / FAILED
    any open state ──emergency stop──► ABORTED   (+ STOP command to the device)
    timeouts (sweep) ──► EXPIRED / FAILED

Overlap protection: dispatch atomically claims the device
(``devices.active_operation_id``) so two operations can never run at once on
one device, even with concurrent approvals or multiple API instances.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any

from pymongo import ReturnDocument

from app.core.errors import ConflictError, NotFoundError
from app.core.timeutil import ensure_utc, new_id, utcnow
from app.db.client import Database
from app.schemas.device import DeviceCapabilities, Telemetry
from app.schemas.scan import Prediction
from app.schemas.spray import ACTIVE_STATUSES, OPEN_STATUSES, Decision, SprayOperationOut
from app.services import safety
from app.services.audit import AuditLog
from app.services.devices import CommandService, DeviceService
from app.services.events import EventBus
from app.services.policy import EmergencyStopService, PolicyService


class SprayService:
    def __init__(
        self, db: Database, bus: EventBus, audit: AuditLog, policy: PolicyService,
        estop: EmergencyStopService, devices: DeviceService, commands: CommandService,
        model_labels: callable, weather_snapshot: callable,
    ) -> None:
        self.db, self.bus, self.audit = db, bus, audit
        self.policy, self.estop, self.devices, self.commands = policy, estop, devices, commands
        self._model_labels = model_labels
        self._weather_snapshot = weather_snapshot
        self._lock = threading.RLock()  # serialises evaluate+dispatch within this process

    # -- helpers ----------------------------------------------------------------
    @staticmethod
    def to_out(doc: dict) -> SprayOperationOut:
        return SprayOperationOut.from_doc(doc)

    def get_doc(self, op_id: str) -> dict:
        doc = self.db.spray_events.find_one({"_id": op_id})
        if doc is None:
            raise NotFoundError("Spray operation not found")
        return doc

    def _history(self, status: str, actor: str, message: str) -> dict:
        return {"ts": utcnow(), "status": status, "actor": actor, "message": message}

    def _publish(self, doc: dict) -> None:
        self.bus.publish("spray.updated", self.to_out(doc).model_dump(), simulated=doc.get("simulated", False))

    def _set_status(self, op_id: str, from_statuses: tuple[str, ...], status: str, actor: str, message: str,
                    extra: dict[str, Any] | None = None) -> dict | None:
        now = utcnow()
        doc = self.db.spray_events.find_one_and_update(
            {"_id": op_id, "status": {"$in": list(from_statuses)}},
            {"$set": {"status": status, "updated_at": now, **(extra or {})},
             "$push": {"history": self._history(status, actor, message)}},
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            self._publish(doc)
        return doc

    def build_context(self, prediction: Prediction | None, device_id: str | None, *, approved: bool,
                      stage: str, exclude_op: str | None = None) -> safety.SafetyContext:
        policy = self.policy.get()
        device_snapshot = None
        active: tuple[str, ...] = ()
        if device_id:
            doc = self.db.devices.find_one({"_id": device_id})
            if doc:
                caps = DeviceCapabilities(**(doc.get("capabilities") or {}))
                device_snapshot = safety.DeviceSnapshot(
                    id=doc["_id"],
                    connectivity=self.devices.connectivity(doc, timeout_s=policy.device_offline_timeout_s),
                    reported_status=doc.get("reported_status"),
                    telemetry=Telemetry(**doc["last_telemetry"]) if doc.get("last_telemetry") else None,
                    last_spray_completed_at=ensure_utc(doc.get("last_spray_completed_at")),
                    max_spray_duration_s=caps.max_spray_duration_s,
                )
                ids = {d["_id"] for d in self.db.spray_events.find(
                    {"device_id": device_id, "status": {"$in": list(ACTIVE_STATUSES)}}, {"_id": 1})}
                if doc.get("active_operation_id"):
                    ids.add(doc["active_operation_id"])
                ids.discard(exclude_op)
                active = tuple(sorted(ids))
        return safety.SafetyContext(
            prediction=prediction,
            model_labels=tuple(self._model_labels()),
            device=device_snapshot,
            active_operation_ids=active,
            emergency_stop_active=self.estop.is_active_or_unknown(),
            policy=policy,
            requested_duration_s=policy.spray_duration_s,
            operator_approved=approved,
            now=utcnow(),
            weather=self._weather_snapshot(),
            stage=stage,
        )

    # -- creation from a scan ----------------------------------------------------------
    def decide_for_scan(self, scan_id: str, prediction: Prediction, device_id: str | None,
                        simulated: bool, actor: str) -> tuple[Decision, str | None]:
        """Evaluate a new scan; create an operation record when spraying is in question."""
        with self._lock:
            ctx = self.build_context(prediction, device_id, approved=False, stage="scan")
            decision = safety.evaluate(ctx)
            if decision.outcome in ("SKIP", "REVIEW_REQUIRED"):
                return decision, None
            now = utcnow()
            status = {"BLOCKED": "BLOCKED", "PENDING_APPROVAL": "PENDING_APPROVAL",
                      "AUTHORIZED": "PENDING_APPROVAL"}[decision.outcome]
            doc = {
                "_id": new_id("op"), "scan_id": scan_id, "device_id": device_id, "simulated": simulated,
                "status": status, "label": prediction.label, "confidence": prediction.confidence,
                "duration_s": ctx.requested_duration_s, "decision": decision.model_dump(),
                "command_id": None, "approved_by": None, "created_at": now, "updated_at": now,
                "expires_at": now + timedelta(seconds=ctx.policy.pending_approval_ttl_s)
                if status == "PENDING_APPROVAL" else None,
                "started_at": None, "finished_at": None,
                "history": [self._history(status, actor, "; ".join(decision.reasons[:3]))],
            }
            self.db.spray_events.insert_one(doc)
            self.audit.record("spray", f"operation_{status.lower()}",
                              f"Spray operation {doc['_id']} {status} for {prediction.label}",
                              level="warning" if status == "BLOCKED" else "info", actor=actor,
                              device_id=device_id, simulated=simulated,
                              context={"scan_id": scan_id, "reasons": decision.reasons})
            self._publish(doc)
            if decision.outcome == "AUTHORIZED":  # approval not required by policy
                self._dispatch(doc, actor="policy:auto")
            return decision, doc["_id"]

    # -- operator actions ----------------------------------------------------------------
    def approve(self, op_id: str, actor: str, note: str | None = None) -> dict:
        with self._lock:
            doc = self.get_doc(op_id)
            if doc["status"] != "PENDING_APPROVAL":
                raise ConflictError(f"Operation is {doc['status']}, not awaiting approval")
            if doc.get("expires_at") and ensure_utc(doc["expires_at"]) <= utcnow():
                self._set_status(op_id, ("PENDING_APPROVAL",), "EXPIRED", "system", "Approval window elapsed")
                raise ConflictError("Approval window has expired; re-scan the plant")
            scan = self.db.scans.find_one({"_id": doc["scan_id"]}) if doc.get("scan_id") else None
            prediction = Prediction(**scan["prediction"]) if scan else None
            ctx = self.build_context(prediction, doc.get("device_id"), approved=True, stage="approval",
                                     exclude_op=op_id)
            decision = safety.evaluate(ctx)
            if decision.outcome != "AUTHORIZED":
                updated = self._set_status(
                    op_id, ("PENDING_APPROVAL",), "BLOCKED", actor,
                    "Re-evaluation at approval failed: " + "; ".join(decision.reasons[:3]),
                    {"decision": decision.model_dump()},
                )
                self.audit.record("spray", "approval_blocked", f"Approval of {op_id} blocked by safety rules",
                                  level="warning", actor=actor, device_id=doc.get("device_id"),
                                  simulated=doc["simulated"], context={"reasons": decision.reasons})
                return updated or self.get_doc(op_id)
            doc = self.db.spray_events.find_one_and_update(
                {"_id": op_id, "status": "PENDING_APPROVAL"},
                {"$set": {"decision": decision.model_dump(), "approved_by": actor, "updated_at": utcnow()},
                 "$push": {"history": self._history("PENDING_APPROVAL", actor,
                                                    "Approved" + (f": {note}" if note else ""))}},
                return_document=ReturnDocument.AFTER,
            )
            if doc is None:
                raise ConflictError("Operation changed concurrently")
            self.audit.record("spray", "approved", f"Operation {op_id} approved", actor=actor,
                              device_id=doc.get("device_id"), simulated=doc["simulated"])
            return self._dispatch(doc, actor)

    def reject(self, op_id: str, actor: str, note: str | None = None) -> dict:
        doc = self._set_status(op_id, ("PENDING_APPROVAL",), "REJECTED", actor,
                               "Rejected by operator" + (f": {note}" if note else ""))
        if doc is None:
            raise ConflictError("Only operations awaiting approval can be rejected")
        self.audit.record("spray", "rejected", f"Operation {op_id} rejected", actor=actor,
                          device_id=doc.get("device_id"), simulated=doc["simulated"])
        return doc

    def _dispatch(self, doc: dict, actor: str) -> dict:
        op_id, device_id = doc["_id"], doc.get("device_id")
        if not device_id or not self.devices.claim(device_id, op_id):
            blocked = self._set_status(op_id, ("PENDING_APPROVAL",), "BLOCKED", "system",
                                       "Device busy with another operation")
            return blocked or self.get_doc(op_id)
        policy = self.policy.get()
        cmd = self.commands.enqueue(
            device_id, "SPRAY", {"duration_s": doc["duration_s"], "operation_id": op_id},
            ttl_s=policy.command_ack_timeout_s, operation_id=op_id, simulated=doc["simulated"],
        )
        updated = self._set_status(op_id, ("PENDING_APPROVAL",), "DISPATCHED", actor,
                                   f"SPRAY command {cmd['_id']} queued ({doc['duration_s']:g}s)",
                                   {"command_id": cmd["_id"]})
        if updated is None:  # lost a race: undo
            self.commands.cancel_pending(device_id, "SPRAY", "operation changed concurrently")
            self.devices.release(device_id, op_id, sprayed=False)
            return self.get_doc(op_id)
        self.audit.record("command", "spray_dispatched", f"SPRAY dispatched for {op_id}", actor=actor,
                          device_id=device_id, simulated=doc["simulated"], context={"command_id": cmd["_id"]})
        return updated

    # -- device feedback -------------------------------------------------------------------
    def on_command_acknowledged(self, cmd: dict) -> None:
        if cmd["type"] == "SPRAY" and cmd.get("operation_id"):
            self._set_status(cmd["operation_id"], ("DISPATCHED",), "RUNNING", f"device:{cmd['device_id']}",
                             "Device acknowledged; spraying", {"started_at": utcnow()})

    def on_command_finished(self, cmd: dict, success: bool, message: str | None) -> None:
        if cmd["type"] != "SPRAY" or not cmd.get("operation_id"):
            return
        op_id = cmd["operation_id"]
        status = "COMPLETED" if success else "FAILED"
        doc = self._set_status(op_id, ("DISPATCHED", "RUNNING"), status, f"device:{cmd['device_id']}",
                               message or ("Spray completed" if success else "Device reported failure"),
                               {"finished_at": utcnow()})
        # Cooldown starts whenever the pump may have run (acknowledged commands).
        self.devices.release(cmd["device_id"], op_id, sprayed=cmd.get("acknowledged_at") is not None)
        if doc:
            self.audit.record("spray", f"operation_{status.lower()}", f"Operation {op_id} {status}",
                              level="info" if success else "error", device_id=cmd["device_id"],
                              simulated=doc["simulated"], context={"message": message})

    # -- emergency stop --------------------------------------------------------------------
    def abort_all(self, actor: str, reason: str) -> int:
        with self._lock:
            n = 0
            for doc in list(self.db.spray_events.find({"status": {"$in": list(OPEN_STATUSES)}})):
                was_active = doc["status"] in ACTIVE_STATUSES
                if self._set_status(doc["_id"], OPEN_STATUSES, "ABORTED", actor, f"Emergency stop: {reason}",
                                    {"finished_at": utcnow()}):
                    n += 1
                    self.devices.release(doc.get("device_id"), doc["_id"], sprayed=was_active)
            self.commands.cancel_pending(None, "SPRAY", "emergency stop")
            policy = self.policy.get()
            for dev in self.devices.list_docs():
                self.commands.enqueue(dev["_id"], "STOP", {"reason": "emergency_stop"},
                                      ttl_s=max(300.0, policy.command_ack_timeout_s), simulated=dev["simulated"])
            return n

    # -- periodic maintenance --------------------------------------------------------------
    def sweep(self) -> None:
        now = utcnow()
        policy = self.policy.get()
        for doc in self.db.spray_events.find({"status": "PENDING_APPROVAL", "expires_at": {"$lte": now}}):
            if self._set_status(doc["_id"], ("PENDING_APPROVAL",), "EXPIRED", "system", "Approval window elapsed"):
                self.audit.record("spray", "expired", f"Operation {doc['_id']} expired awaiting approval",
                                  device_id=doc.get("device_id"), simulated=doc["simulated"])
        for cmd in self.commands.expire():
            if cmd["type"] == "SPRAY" and cmd.get("operation_id"):
                if self._set_status(cmd["operation_id"], ("DISPATCHED",), "FAILED", "system",
                                    "Device did not acknowledge the command in time", {"finished_at": now}):
                    self.devices.release(cmd["device_id"], cmd["operation_id"], sprayed=False)
                    self.audit.record("spray", "ack_timeout", f"Operation {cmd['operation_id']} failed: no ack",
                                      level="error", device_id=cmd["device_id"], simulated=cmd.get("simulated", False))
        grace = policy.command_ack_timeout_s
        for doc in self.db.spray_events.find({"status": "RUNNING"}):
            started = ensure_utc(doc.get("started_at")) or ensure_utc(doc["updated_at"])
            if (now - started).total_seconds() > doc["duration_s"] + grace:
                if self._set_status(doc["_id"], ("RUNNING",), "FAILED", "system",
                                    "No completion report from device; STOP sent as precaution",
                                    {"finished_at": now}):
                    self.devices.release(doc.get("device_id"), doc["_id"], sprayed=True)
                    self.commands.enqueue(doc["device_id"], "STOP", {"reason": "completion_timeout"},
                                          ttl_s=300, simulated=doc["simulated"])
                    self.audit.record("spray", "completion_timeout", f"Operation {doc['_id']} timed out",
                                      level="error", device_id=doc.get("device_id"), simulated=doc["simulated"])

    # -- queries ----------------------------------------------------------------------------
    def list(self, status: str | None = None, device_id: str | None = None,
             page: int = 1, page_size: int = 25) -> tuple[list[dict], int]:
        query: dict[str, Any] = {}
        if status:
            query["status"] = {"$in": status.split(",")}
        if device_id:
            query["device_id"] = device_id
        total = self.db.spray_events.count_documents(query)
        docs = list(self.db.spray_events.find(query).sort("created_at", -1)
                    .skip((page - 1) * page_size).limit(page_size))
        return docs, total

    def evaluate_dry_run(self, scan_id: str, device_id: str | None) -> Decision:
        scan = self.db.scans.find_one({"_id": scan_id})
        if scan is None:
            raise NotFoundError("Scan not found")
        prediction = Prediction(**scan["prediction"])
        return safety.evaluate(self.build_context(prediction, device_id or scan.get("device_id"),
                                                  approved=False, stage="scan"))
