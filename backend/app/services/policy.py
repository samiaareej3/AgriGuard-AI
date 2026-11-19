"""Spray policy and emergency-stop state, persisted in the ``settings`` collection."""

from __future__ import annotations

import threading

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.core.errors import ConflictError
from app.core.timeutil import utcnow
from app.db.client import Database
from app.schemas.spray import EmergencyStopState, SprayPolicy, SprayPolicyUpdate

POLICY_ID = "spray_policy"
ESTOP_ID = "emergency_stop"


class PolicyService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._lock = threading.Lock()

    def get(self) -> SprayPolicy:
        doc = self.db.settings.find_one({"_id": POLICY_ID})
        if doc is None:
            with self._lock:
                doc = self.db.settings.find_one({"_id": POLICY_ID})
                if doc is None:
                    policy = SprayPolicy(
                        confidence_threshold=self.settings.default_confidence_threshold,
                        updated_at=utcnow(),
                        updated_by="system",
                    )
                    self.db.settings.insert_one({"_id": POLICY_ID, **policy.model_dump()})
                    return policy
        doc.pop("_id", None)
        return SprayPolicy.model_validate(doc)

    def update(self, update: SprayPolicyUpdate, actor: str) -> SprayPolicy:
        current = self.get()
        if update.expected_version is not None and update.expected_version != current.version:
            raise ConflictError(
                "Policy was changed by someone else; reload and try again",
                details={"current_version": current.version},
            )
        data = current.model_dump() | update.model_dump(exclude={"expected_version"})
        data |= {"version": current.version + 1, "updated_at": utcnow(), "updated_by": actor}
        policy = SprayPolicy.model_validate(data)  # re-validates cross-field rules
        result = self.db.settings.find_one_and_update(
            {"_id": POLICY_ID, "version": current.version},
            {"$set": policy.model_dump()},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise ConflictError("Policy was changed concurrently; reload and try again")
        return policy


class EmergencyStopService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self) -> EmergencyStopState:
        doc = self.db.settings.find_one({"_id": ESTOP_ID})
        if doc is None:
            return EmergencyStopState(active=False)
        doc.pop("_id", None)
        return EmergencyStopState.model_validate(doc)

    def is_active_or_unknown(self) -> bool | None:
        """``True``/``False`` when known; ``None`` if the state cannot be read."""
        try:
            return self.get().active
        except PyMongoError:
            return None

    def activate(self, actor: str, reason: str) -> tuple[EmergencyStopState, bool]:
        """Returns (state, changed). Idempotent: activating twice is a no-op."""
        current = self.get()
        if current.active:
            return current, False
        state = EmergencyStopState(active=True, activated_at=utcnow(), activated_by=actor, reason=reason)
        self.db.settings.update_one({"_id": ESTOP_ID}, {"$set": state.model_dump()}, upsert=True)
        return state, True

    def reset(self, actor: str, reason: str) -> tuple[EmergencyStopState, bool]:
        current = self.get()
        if not current.active:
            return current, False
        state = current.model_copy(update={
            "active": False, "reset_at": utcnow(), "reset_by": actor, "reset_reason": reason,
        })
        self.db.settings.update_one({"_id": ESTOP_ID}, {"$set": state.model_dump()}, upsert=True)
        return state, True
