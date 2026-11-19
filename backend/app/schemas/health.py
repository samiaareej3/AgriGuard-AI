"""Health and readiness schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ComponentState = Literal["ok", "not_configured", "unavailable", "not_loaded", "degraded"]


class ComponentStatus(BaseModel):
    status: ComponentState
    detail: str | None = None
    critical: bool = Field(
        default=True, description="If true, an unavailable state makes the service not ready"
    )


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    timestamp: datetime = Field(description="Server time in UTC")


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded", "not_ready"]
    timestamp: datetime
    components: dict[str, ComponentStatus]
