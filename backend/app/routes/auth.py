from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.routes.deps import Admin, ServicesDep, Viewer, client_ip
from app.schemas.auth import LoginRequest, PasswordChange, TokenResponse, UserCreate, UserOut

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse, summary="Exchange credentials for a bearer token")
def login(body: LoginRequest, request: Request, services: ServicesDep) -> TokenResponse:
    services.rate_limiter.check(f"login:{client_ip(request)}", services.settings.rate_limit_login_per_min)
    result = services.users.login(body.username, body.password)
    services.audit.record("auth", "login", f"User '{body.username}' logged in", actor=f"user:{body.username}")
    return result


@router.get("/auth/me", response_model=UserOut)
def me(user: Viewer, services: ServicesDep) -> UserOut:
    return services.users.to_out(services.users.get(user.id))


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, user: Viewer, services: ServicesDep, request: Request) -> None:
    services.rate_limiter.check(f"pwd:{user.id}", services.settings.rate_limit_login_per_min)
    services.users.change_password(user.id, body.current_password, body.new_password)
    services.audit.record("auth", "password_changed", f"User '{user.username}' changed password", actor=user.actor)


@router.get("/users", response_model=list[UserOut])
def list_users(_: Admin, services: ServicesDep) -> list[UserOut]:
    return services.users.list()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, admin: Admin, services: ServicesDep) -> UserOut:
    out = services.users.create(body.username, body.password, body.role)
    services.audit.record("auth", "user_created", f"User '{body.username}' ({body.role.value}) created",
                          actor=admin.actor)
    return out
