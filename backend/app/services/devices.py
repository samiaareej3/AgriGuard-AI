"""Device registry, connectivity, telemetry and the command queue.

Connectivity is *derived* from the last heartbeat time and the policy's
offline timeout. It is never set optimistically. A device may also announce a
graceful disconnect, which takes effect immediately.

Commands are pulled by devices (HTTP polling), which works behind NAT and is
identical for the simulator and for real ESP32 firmware.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pymongo import ReturnDocument

from app.core.errors import NotFoundError
from app.core.security import generate_device_token, hash_device_token
from app.core.timeutil import ensure_utc, new_id, utcnow
from app.db.client import Database
from app.schemas.device import (
    CommandOut, DeviceOut, DeviceRegister, HeartbeatRequest, Telemetry, TelemetryPoint,
)
from app.services.audit import AuditLog
from app.services.events import EventBus
from app.services.policy import PolicyService


class DeviceService:
    def __init__(self, db: Database, bus: EventBus, audit: AuditLog, policy: PolicyService) -> None:
        self.db = db
        self.bus = bus
        self.audit = audit
        self.policy = policy

    # -- registry --------------------------------------------------------------
    def register(self, data: DeviceRegister, actor: str) -> tuple[dict, str]:
        token = generate_device_token()
        now = utcnow()
        doc = {
            "_id": new_id("dev"),
            "name": data.name,
            "source": data.source,
            "simulated": data.source == "simulator",
            "location": data.location,
            "firmware_version": data.firmware_version,
            "capabilities": data.capabilities.model_dump(),
            "token_hash": hash_device_token(token),
            "created_at": now,
            "last_seen": None,
            "connected": False,
            "known_connectivity": "never_seen",
            "reported_status": None,
            "last_telemetry": None,
            "uptime_s": None,
            "last_spray_completed_at": None,
            "active_operation_id": None,
        }
        self.db.devices.insert_one(doc)
        self.audit.record("device", "registered", f"Device '{data.name}' registered ({data.source})",
                          actor=actor, device_id=doc["_id"], simulated=doc["simulated"])
        self.bus.publish("device.updated", self.to_out(doc).model_dump(), simulated=doc["simulated"])
        return doc, token

    def rotate_token(self, device_id: str) -> str:
        token = generate_device_token()
        res = self.db.devices.update_one({"_id": device_id}, {"$set": {"token_hash": hash_device_token(token)}})
        if res.matched_count == 0:
            raise NotFoundError("Device not found")
        return token

    def authenticate(self, token: str | None) -> dict | None:
        if not token:
            return None
        return self.db.devices.find_one({"token_hash": hash_device_token(token)})

    def get_doc(self, device_id: str) -> dict:
        doc = self.db.devices.find_one({"_id": device_id})
        if doc is None:
            raise NotFoundError("Device not found", details={"device_id": device_id})
        return doc

    def list_docs(self, source: str | None = None) -> list[dict]:
        query = {"source": source} if source else {}
        return list(self.db.devices.find(query).sort("created_at", 1))

    def delete(self, device_id: str, actor: str) -> None:
        doc = self.get_doc(device_id)
        self.db.devices.delete_one({"_id": device_id})
        self.db.device_commands.update_many(
            {"device_id": device_id, "status": {"$in": ["QUEUED", "DELIVERED"]}},
            {"$set": {"status": "CANCELLED", "finished_at": utcnow(), "result_message": "device deleted"}},
        )
        self.audit.record("device", "deleted", f"Device '{doc['name']}' deleted", actor=actor,
                          device_id=device_id, simulated=doc["simulated"])
        self.bus.publish("device.deleted", {"id": device_id}, simulated=doc["simulated"])

    # -- connectivity ------------------------------------------------------------
    def connectivity(self, doc: dict, now: datetime | None = None, timeout_s: float | None = None) -> str:
        last = ensure_utc(doc.get("last_seen"))
        if last is None:
            return "never_seen"
        if not doc.get("connected", True):
            return "offline"
        now = now or utcnow()
        timeout_s = timeout_s if timeout_s is not None else self.policy.get().device_offline_timeout_s
        return "online" if (now - last).total_seconds() <= timeout_s else "offline"

    def to_out(self, doc: dict, timeout_s: float | None = None) -> DeviceOut:
        data = dict(doc)
        data["connectivity"] = self.connectivity(doc, timeout_s=timeout_s)
        return DeviceOut.from_doc(data)

    def list_out(self, source: str | None = None) -> list[DeviceOut]:
        timeout = self.policy.get().device_offline_timeout_s
        return [self.to_out(d, timeout) for d in self.list_docs(source)]

    def _transition(self, doc: dict, new_state: str, reason: str) -> None:
        old = doc.get("known_connectivity")
        if old == new_state:
            return
        self.db.devices.update_one({"_id": doc["_id"]}, {"$set": {"known_connectivity": new_state}})
        level = "warning" if new_state == "offline" else "info"
        self.audit.record("device", f"connectivity_{new_state}",
                          f"Device '{doc['name']}' is {new_state} ({reason})", level=level,
                          device_id=doc["_id"], simulated=doc["simulated"])
        self.bus.publish("device.connectivity", {"id": doc["_id"], "name": doc["name"], "state": new_state,
                                                 "previous": old}, simulated=doc["simulated"])

    def sweep_connectivity(self) -> None:
        """Detect devices whose heartbeats stopped (called periodically)."""
        timeout = self.policy.get().device_offline_timeout_s
        now = utcnow()
        for doc in self.db.devices.find({"known_connectivity": "online"}):
            if self.connectivity(doc, now, timeout) != "online":
                self._transition(doc, "offline", "heartbeat timeout")

    # -- device-originated events -------------------------------------------------------
    def heartbeat(self, device: dict, hb: HeartbeatRequest) -> dict:
        now = utcnow()
        update: dict[str, Any] = {
            "last_seen": now,
            "connected": True,
            "reported_status": hb.status,
            "last_telemetry": hb.telemetry.model_dump(),
            "uptime_s": hb.uptime_s,
        }
        if hb.firmware_version:
            update["firmware_version"] = hb.firmware_version
        doc = self.db.devices.find_one_and_update(
            {"_id": device["_id"]}, {"$set": update}, return_document=ReturnDocument.AFTER
        )
        self.db.telemetry.insert_one({
            "_id": new_id("tel"), "device_id": device["_id"], "ts": now,
            "simulated": device["simulated"], "telemetry": hb.telemetry.model_dump(), "status": hb.status,
        })
        self._transition(doc, "online", "heartbeat received")
        self.bus.publish("device.heartbeat", {
            "id": doc["_id"], "name": doc["name"], "status": hb.status,
            "telemetry": hb.telemetry.model_dump(), "ts": now,
        }, simulated=doc["simulated"])
        return doc

    def disconnect(self, device: dict, reason: str = "device announced disconnect") -> None:
        doc = self.db.devices.find_one_and_update(
            {"_id": device["_id"]}, {"$set": {"connected": False}}, return_document=ReturnDocument.AFTER
        )
        if doc:
            self._transition(doc, "offline", reason)

    def telemetry_history(self, device_id: str, minutes: int = 30, limit: int = 500) -> list[TelemetryPoint]:
        since = utcnow() - timedelta(minutes=minutes)
        cursor = (self.db.telemetry.find({"device_id": device_id, "ts": {"$gte": since}})
                  .sort("ts", -1).limit(limit))
        points = [TelemetryPoint(ts=d["ts"], simulated=d["simulated"], telemetry=Telemetry(**d["telemetry"]))
                  for d in cursor]
        return list(reversed(points))

    # -- device lock (prevents overlapping spray operations) ------------------------------
    def claim(self, device_id: str, operation_id: str) -> bool:
        res = self.db.devices.update_one(
            {"_id": device_id, "active_operation_id": None}, {"$set": {"active_operation_id": operation_id}}
        )
        return res.modified_count == 1

    def release(self, device_id: str | None, operation_id: str, sprayed: bool) -> None:
        if not device_id:
            return
        update: dict[str, Any] = {"active_operation_id": None}
        if sprayed:
            update["last_spray_completed_at"] = utcnow()
        self.db.devices.update_one({"_id": device_id, "active_operation_id": operation_id}, {"$set": update})
        if sprayed:  # cooldown applies even if the lock was already released
            self.db.devices.update_one({"_id": device_id}, {"$set": {"last_spray_completed_at": utcnow()}})


class CommandService:
    def __init__(self, db: Database, bus: EventBus) -> None:
        self.db = db
        self.bus = bus

    @staticmethod
    def to_out(doc: dict) -> CommandOut:
        return CommandOut.from_doc(doc)

    def enqueue(self, device_id: str, ctype: str, params: dict, ttl_s: float,
                operation_id: str | None = None, simulated: bool = False) -> dict:
        now = utcnow()
        doc = {
            "_id": new_id("cmd"), "device_id": device_id, "type": ctype, "params": params,
            "status": "QUEUED", "operation_id": operation_id, "simulated": simulated,
            "created_at": now, "expires_at": now + timedelta(seconds=ttl_s),
            "delivered_at": None, "acknowledged_at": None, "finished_at": None, "result_message": None,
            "delivery_count": 0,
        }
        self.db.device_commands.insert_one(doc)
        self.bus.publish("command.queued", self.to_out(doc).model_dump(), simulated=simulated)
        return doc

    def next_for(self, device_id: str) -> dict | None:
        """Deliver the next command. STOP has priority. Un-acked deliveries are
        re-delivered (at-least-once); devices de-duplicate by command id."""
        now = utcnow()
        self.expire(device_id)
        for ctype in ("STOP", "SPRAY"):
            doc = self.db.device_commands.find_one_and_update(
                {"device_id": device_id, "type": ctype, "status": {"$in": ["QUEUED", "DELIVERED"]},
                 "expires_at": {"$gt": now}},
                {"$set": {"status": "DELIVERED", "delivered_at": now}, "$inc": {"delivery_count": 1}},
                sort=[("created_at", 1)],
                return_document=ReturnDocument.AFTER,
            )
            if doc:
                return doc
        return None

    def expire(self, device_id: str | None = None) -> list[dict]:
        now = utcnow()
        query: dict[str, Any] = {"status": {"$in": ["QUEUED", "DELIVERED"]}, "expires_at": {"$lte": now}}
        if device_id:
            query["device_id"] = device_id
        expired = list(self.db.device_commands.find(query))
        for doc in expired:
            self.db.device_commands.update_one(
                {"_id": doc["_id"], "status": {"$in": ["QUEUED", "DELIVERED"]}},
                {"$set": {"status": "EXPIRED", "finished_at": now,
                          "result_message": "not acknowledged before expiry"}},
            )
        return expired

    def get(self, command_id: str, device_id: str) -> dict:
        doc = self.db.device_commands.find_one({"_id": command_id, "device_id": device_id})
        if doc is None:
            raise NotFoundError("Command not found for this device")
        return doc

    def acknowledge(self, command_id: str, device_id: str) -> tuple[dict, bool]:
        """Idempotent. Returns (command, changed)."""
        doc = self.db.device_commands.find_one_and_update(
            {"_id": command_id, "device_id": device_id, "status": {"$in": ["QUEUED", "DELIVERED"]},
             "expires_at": {"$gt": utcnow()}},
            {"$set": {"status": "ACKNOWLEDGED", "acknowledged_at": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            return doc, True
        return self.get(command_id, device_id), False

    def finish(self, command_id: str, device_id: str, success: bool, message: str | None) -> tuple[dict, bool]:
        """Idempotent. Returns (command, changed)."""
        doc = self.db.device_commands.find_one_and_update(
            {"_id": command_id, "device_id": device_id, "status": {"$in": ["DELIVERED", "ACKNOWLEDGED"]}},
            {"$set": {"status": "COMPLETED" if success else "FAILED", "finished_at": utcnow(),
                      "result_message": message}},
            return_document=ReturnDocument.AFTER,
        )
        if doc:
            return doc, True
        return self.get(command_id, device_id), False

    def cancel_pending(self, device_id: str | None = None, ctype: str | None = "SPRAY",
                       reason: str = "cancelled") -> int:
        query: dict[str, Any] = {"status": {"$in": ["QUEUED", "DELIVERED"]}}
        if device_id:
            query["device_id"] = device_id
        if ctype:
            query["type"] = ctype
        res = self.db.device_commands.update_many(
            query, {"$set": {"status": "CANCELLED", "finished_at": utcnow(), "result_message": reason}}
        )
        return res.modified_count

    def pending_count(self, device_id: str) -> int:
        return self.db.device_commands.count_documents(
            {"device_id": device_id, "status": {"$in": ["QUEUED", "DELIVERED"]}, "expires_at": {"$gt": utcnow()}}
        )

    def list_for(self, device_id: str, limit: int = 50) -> list[CommandOut]:
        cur = self.db.device_commands.find({"device_id": device_id}).sort("created_at", -1).limit(limit)
        return [self.to_out(d) for d in cur]
