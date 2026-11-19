"""Device schemas, including the versioned device ↔ backend contract (v1).

The same contract is used by the in-process simulator and by real ESP32-CAM
firmware; see docs/DEVICE_API.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.base import Schema, UTCDateTime

DeviceSource = Literal["simulator", "esp32"]
ConnectivityState = Literal["online", "offline", "never_seen"]
ReportedStatus = Literal["ok", "warning", "error"]
PumpState = Literal["idle", "running", "fault"]
CommandType = Literal["SPRAY", "STOP"]
CommandStatus = Literal["QUEUED", "DELIVERED", "ACKNOWLEDGED", "COMPLETED", "FAILED", "EXPIRED", "CANCELLED"]


class DeviceCapabilities(Schema):
    camera: bool = True
    pump: bool = True
    sensors: list[str] = Field(default_factory=lambda: ["temperature", "humidity", "battery", "tank_level", "rssi"])
    max_spray_duration_s: float = Field(default=10, gt=0, le=60)


class Telemetry(Schema):
    """Sensor readings. Every field is optional: unknown values stay null and
    are treated as unknown (never guessed) by the safety engine."""

    temperature_c: float | None = Field(default=None, ge=-40, le=85)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    battery_pct: float | None = Field(default=None, ge=0, le=100)
    tank_level_pct: float | None = Field(default=None, ge=0, le=100)
    rssi_dbm: float | None = Field(default=None, ge=-120, le=0)
    pump_state: PumpState | None = None


class DeviceRegister(Schema):
    name: str = Field(min_length=1, max_length=64)
    source: DeviceSource = "esp32"
    location: str | None = Field(default=None, max_length=120)
    firmware_version: str | None = Field(default=None, max_length=32)
    capabilities: DeviceCapabilities = Field(default_factory=DeviceCapabilities)


class DeviceOut(Schema):
    id: str
    name: str
    source: DeviceSource
    simulated: bool
    location: str | None = None
    firmware_version: str | None = None
    capabilities: DeviceCapabilities
    connectivity: ConnectivityState
    reported_status: ReportedStatus | None = None
    last_seen: UTCDateTime | None = None
    last_telemetry: Telemetry | None = None
    uptime_s: float | None = None
    created_at: UTCDateTime
    last_spray_completed_at: UTCDateTime | None = None


class DeviceRegisterResponse(Schema):
    device: DeviceOut
    device_token: str = Field(description="Shown once. Store it on the device; only a hash is kept server-side.")


class HeartbeatRequest(Schema):
    status: ReportedStatus = "ok"
    firmware_version: str | None = Field(default=None, max_length=32)
    uptime_s: float | None = Field(default=None, ge=0)
    telemetry: Telemetry = Field(default_factory=Telemetry)


class HeartbeatResponse(Schema):
    server_time: UTCDateTime
    device_id: str
    pending_commands: int
    emergency_stop_active: bool
    next_heartbeat_s: float


class TelemetryPoint(Schema):
    ts: UTCDateTime
    simulated: bool
    telemetry: Telemetry


class CommandOut(Schema):
    id: str
    device_id: str
    type: CommandType
    params: dict = Field(default_factory=dict)
    status: CommandStatus
    operation_id: str | None = None
    created_at: UTCDateTime
    expires_at: UTCDateTime | None = None
    delivered_at: UTCDateTime | None = None
    acknowledged_at: UTCDateTime | None = None
    finished_at: UTCDateTime | None = None
    result_message: str | None = None


class CommandResult(Schema):
    success: bool
    message: str | None = Field(default=None, max_length=500)
    actual_duration_s: float | None = Field(default=None, ge=0, le=600)
