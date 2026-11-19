"""User accounts and login."""

from __future__ import annotations

from pymongo.errors import DuplicateKeyError

from app.core.config import Settings
from app.core.errors import ConflictError, UnauthorizedError, ValidationAppError
from app.core.security import Role, create_token, hash_password, verify_password
from app.core.timeutil import new_id, utcnow
from app.db.client import Database
from app.schemas.auth import TokenResponse, UserOut


class UserService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    def bootstrap_admin(self) -> bool:
        """Create the initial admin account if no admin exists. Returns True if created."""
        if self.db.users.find_one({"role": Role.ADMIN.value}):
            return False
        self.db.users.insert_one({
            "_id": new_id("usr"),
            "username": self.settings.admin_username,
            "password_hash": hash_password(self.settings.effective_admin_password),
            "role": Role.ADMIN.value,
            "created_at": utcnow(),
            "is_default_password": self.settings.using_dev_admin_password,
        })
        return True

    @staticmethod
    def to_out(doc: dict) -> UserOut:
        return UserOut.from_doc(doc)

    def login(self, username: str, password: str) -> TokenResponse:
        doc = self.db.users.find_one({"username": username})
        # Verify even for unknown users to keep timing similar.
        stored = doc["password_hash"] if doc else hash_password("timing-equaliser")
        if not verify_password(password, stored) or doc is None:
            raise UnauthorizedError("Invalid username or password", code="INVALID_CREDENTIALS")
        ttl = self.settings.token_ttl_minutes * 60
        token = create_token(doc["_id"], doc["role"], self.settings.secret_key, ttl)
        return TokenResponse(access_token=token, expires_in=ttl, user=self.to_out(doc))

    def get(self, user_id: str) -> dict | None:
        return self.db.users.find_one({"_id": user_id})

    def list(self) -> list[UserOut]:
        return [self.to_out(d) for d in self.db.users.find({}).sort("created_at", 1)]

    def create(self, username: str, password: str, role: Role) -> UserOut:
        doc = {
            "_id": new_id("usr"),
            "username": username,
            "password_hash": hash_password(password),
            "role": role.value,
            "created_at": utcnow(),
            "is_default_password": False,
        }
        try:
            self.db.users.insert_one(doc)
        except DuplicateKeyError as exc:
            raise ConflictError("Username already exists") from exc
        return self.to_out(doc)

    def change_password(self, user_id: str, current: str, new: str) -> None:
        doc = self.get(user_id)
        if doc is None or not verify_password(current, doc["password_hash"]):
            raise UnauthorizedError("Current password is incorrect", code="INVALID_CREDENTIALS")
        if current == new:
            raise ValidationAppError("New password must differ from the current password")
        self.db.users.update_one(
            {"_id": user_id},
            {"$set": {"password_hash": hash_password(new), "is_default_password": False}},
        )
