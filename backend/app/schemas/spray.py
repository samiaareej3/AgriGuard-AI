from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.base import Schema, UTCDateTime

DecisionOutcome = Literal["AUTHORIZED", "PENDING_APPROVAL", "BLOCKED", "REVIEW_REQUIRED", "SKIP"]
OperationStatus = Literal[
    "PENDING_APPROVAL",  # waiting for an operator
    "BLOCKED",           # a safety rule failed; never dispatched
    "DISPATCHED",        # command queued for the device
    "RUNNING",           # device acknowledged and is spraying
    "COMPLETED",
    "FAILED",
    "ABORTED",           # emergency stop / STOP command
    "REJECTED",          # operator rejected
    "EXPIRED",           # approval window elapsed
]
ACTIVE_STATUSES = ("DISPATCHED", "RUNNING")
OPEN_STATUSES = ("PENDING_APPROVAL", "DISPATCHED", "RUNNING")


class RuleResult(Schema):
    rule: str
    passed: bool | None = Field(description="null = condition unknown (treated as failure when critical)")
    critical: bool = True
    message: str


class Decision(Schema):
    outcome: DecisionOutcome
    reasons: list[str] = Field(default_factory=list, description="Human-readable reasons for the outcome")
    rules: list[RuleResult] = Field(default_factory=list)
    policy_version: int
    evaluated_at: UTCDateTime
    stage: Literal["scan", "approval"] = "scan"


class WeatherPolicy(Schema):
    enabled: bool = True
    blocking: bool = Field(default=False, description="If false, weather issues are warnings only")
    max_wind_kmh: float = Field(default=15, gt=0, le=100)
    max_precip_probability_pct: float = Field(default=60, ge=0, le=100)


class SprayPolicy(Schema):
    version: int = 1
    confidence_threshold: float = Field(default=0.75, ge=0.5, le=0.99)
    min_confidence_margin: float = Field(default=0.15, ge=0, le=0.9)
    sprayable_labels: list[str] = Field(default_factory=lambda: ["early_blight", "late_blight"])
    require_operator_approval: bool = True
    spray_duration_s: float = Field(default=3, gt=0, le=60)
    max_spray_duration_s: float = Field(default=10, gt=0, le=60)
    cooldown_s: float = Field(default=60, ge=0, le=86400)
    device_offline_timeout_s: float = Field(default=30, ge=5, le=3600)
    min_tank_level_pct: float = Field(default=10, ge=0, le=100)
    min_battery_pct: float = Field(default=20, ge=0, le=100)
    pending_approval_ttl_s: float = Field(default=900, ge=30, le=86400)
    command_ack_timeout_s: float = Field(default=20, ge=3, le=600)
    weather: WeatherPolicy = Field(default_factory=WeatherPolicy)
    updated_at: UTCDateTime | None = None
    updated_by: str | None = None

    @model_validator(mode="after")
    def _duration_within_max(self) -> "SprayPolicy":
        if self.spray_duration_s > self.max_spray_duration_s:
            raise ValueError("spray_duration_s cannot exceed max_spray_duration_s")
        return self


class SprayPolicyUpdate(Schema):
    """Full replacement of editable policy fields (version is managed server-side)."""

    confidence_threshold: float = Field(ge=0.5, le=0.99)
    min_confidence_margin: float = Field(ge=0, le=0.9)
    require_operator_approval: bool
    spray_duration_s: float = Field(gt=0, le=60)
    max_spray_duration_s: float = Field(gt=0, le=60)
    cooldown_s: float = Field(ge=0, le=86400)
    device_offline_timeout_s: float = Field(ge=5, le=3600)
    min_tank_level_pct: float = Field(ge=0, le=100)
    min_battery_pct: float = Field(ge=0, le=100)
    pending_approval_ttl_s: float = Field(ge=30, le=86400)
    command_ack_timeout_s: float = Field(ge=3, le=600)
    weather: WeatherPolicy
    expected_version: int | None = Field(default=None, description="Optimistic concurrency check")

    @model_validator(mode="after")
    def _duration_within_max(self) -> "SprayPolicyUpdate":
        if self.spray_duration_s > self.max_spray_duration_s:
            raise ValueError("spray_duration_s cannot exceed max_spray_duration_s")
        return self


class OperationHistoryEntry(Schema):
    ts: UTCDateTime
    status: OperationStatus
    actor: str
    message: str


class SprayOperationOut(Schema):
    id: str
    scan_id: str | None = None
    device_id: str | None = None
    simulated: bool
    status: OperationStatus
    label: str | None = None
    confidence: float | None = None
    duration_s: float
    decision: Decision
    command_id: str | None = None
    approved_by: str | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    expires_at: UTCDateTime | None = None
    started_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None
    history: list[OperationHistoryEntry] = Field(default_factory=list)


class OperatorNote(Schema):
    note: str | None = Field(default=None, max_length=500)


class EvaluateRequest(Schema):
    scan_id: str
    device_id: str | None = None


class EmergencyStopRequest(Schema):
    reason: str = Field(min_length=3, max_length=300)


class EmergencyStopState(Schema):
    active: bool
    activated_at: UTCDateTime | None = None
    activated_by: str | None = None
    reason: str | None = None
    reset_at: UTCDateTime | None = None
    reset_by: str | None = None
    reset_reason: str | None = None
