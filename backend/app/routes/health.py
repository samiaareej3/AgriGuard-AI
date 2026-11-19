"""Liveness and readiness endpoints.

* ``GET /health``       — liveness: the process is up and serving requests.
* ``GET /health/ready`` — readiness: dependency status (database, model, ...).

Readiness returns 503 only when a *critical* component that is configured is
unavailable. Components that are intentionally not configured (e.g. no Atlas
URI in local dev) report ``degraded`` with HTTP 200 so the demo still runs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response

from app.core.config import Settings
from app.schemas.common import ErrorResponse
from app.schemas.health import ComponentStatus, HealthResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, summary="Liveness probe")
def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe with dependency status",
    responses={503: {"model": ReadinessResponse}, 500: {"model": ErrorResponse}},
)
def readiness(request: Request, response: Response) -> ReadinessResponse:
    checks = getattr(request.app.state, "readiness_checks", {})
    components: dict[str, ComponentStatus] = {}
    for name, check in checks.items():
        try:
            components[name] = check()
        except Exception as exc:  # a failing check must never crash the probe
            components[name] = ComponentStatus(status="unavailable", detail=type(exc).__name__)

    if any(c.critical and c.status == "unavailable" for c in components.values()):
        overall = "not_ready"
        response.status_code = 503
    elif any(c.status != "ok" for c in components.values()):
        overall = "degraded"
    else:
        overall = "ready"

    return ReadinessResponse(
        status=overall, timestamp=datetime.now(timezone.utc), components=components
    )
