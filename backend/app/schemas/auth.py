from __future__ import annotations

from pydantic import Field

from app.core.security import Role
from app.schemas.base import Schema, UTCDateTime


class LoginRequest(Schema):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(Schema):
    id: str
    username: str
    role: Role
    created_at: UTCDateTime
    is_default_password: bool = False


class TokenResponse(Schema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserCreate(Schema):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=256)
    role: Role = Role.VIEWER


class PasswordChange(Schema):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)
