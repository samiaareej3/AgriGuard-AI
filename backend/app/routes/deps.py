"""Shared FastAPI dependencies: services, auth, roles, device auth, rate limits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import ROLE_RANK, Role, decode_token
from app.services.container import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


@dataclass(frozen=True)
class CurrentUser:
    id: str
    username: str
    role: Role

    @property
    def actor(self) -> str:
        return f"user:{self.username}"


def user_from_token(services: Services, token: str | None) -> CurrentUser | None:
    if not token:
        return None
    payload = decode_token(token, services.settings.secret_key)
    if payload is None:
        return None
    doc = services.users.get(payload["sub"])
    if doc is None:
        return None
    return CurrentUser(id=doc["_id"], username=doc["username"], role=Role(doc["role"]))


def get_current_user(services: ServicesDep, authorization: Annotated[str | None, Header()] = None) -> CurrentUser:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user = user_from_token(services, token)
    if user is None:
        raise UnauthorizedError("Authentication required" if not token else "Invalid or expired token")
    return user


def require(role: Role):
    def checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if ROLE_RANK[user.role] < ROLE_RANK[role]:
            raise ForbiddenError(f"Requires {role.value} role")
        return user

    return checker


Viewer = Annotated[CurrentUser, Depends(require(Role.VIEWER))]
Operator = Annotated[CurrentUser, Depends(require(Role.OPERATOR))]
Admin = Annotated[CurrentUser, Depends(require(Role.ADMIN))]


def get_device(services: ServicesDep, x_device_token: Annotated[str | None, Header()] = None) -> dict:
    device = services.devices.authenticate(x_device_token)
    if device is None:
        raise UnauthorizedError("Valid X-Device-Token header required", code="DEVICE_UNAUTHORIZED")
    services.rate_limiter.check(f"device:{device['_id']}", services.settings.rate_limit_device_per_min)
    return device


DeviceDep = Annotated[dict, Depends(get_device)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
