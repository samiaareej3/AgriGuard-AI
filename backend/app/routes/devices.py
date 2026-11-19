"""Operator-facing device management and simulator controls."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, status
from pydantic import Field

from app.core.errors import ValidationAppError
from app.routes.deps import Admin, Operator, ServicesDep, Viewer
from app.schemas.base import Schema
from app.schemas.device import CommandOut, DeviceOut, DeviceRegister, DeviceRegisterResponse, TelemetryPoint
from app.schemas.scan import ScanOut

router = APIRouter(tags=["devices"])


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(_: Viewer, services: ServicesDep,
                 source: Literal["simulator", "esp32"] | None = None) -> list[DeviceOut]:
    return services.devices.list_out(source)


@router.post("/devices", response_model=DeviceRegisterResponse, status_code=status.HTTP_201_CREATED,
             summary="Register a device (returns its token once)")
def register_device(body: DeviceRegister, user: Operator, services: ServicesDep) -> DeviceRegisterResponse:
    if body.source == "simulator":
        raise ValidationAppError("Use POST /simulator/devices to create simulated devices")
    doc, token = services.devices.register(body, actor=user.actor)
    return DeviceRegisterResponse(device=services.devices.to_out(doc), device_token=token)


@router.get("/devices/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, _: Viewer, services: ServicesDep) -> DeviceOut:
    return services.devices.to_out(services.devices.get_doc(device_id))


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: str, admin: Admin, services: ServicesDep) -> None:
    services.devices.delete(device_id, actor=admin.actor)
    services.simulator.remove(device_id)


@router.post("/devices/{device_id}/rotate-token", response_model=DeviceRegisterResponse)
def rotate_token(device_id: str, admin: Admin, services: ServicesDep) -> DeviceRegisterResponse:
    doc = services.devices.get_doc(device_id)
    if doc["simulated"]:
        raise ValidationAppError("Simulated device tokens are managed by the simulator")
    token = services.devices.rotate_token(device_id)
    services.audit.record("device", "token_rotated", f"Token rotated for '{doc['name']}'", actor=admin.actor,
                          device_id=device_id)
    return DeviceRegisterResponse(device=services.devices.to_out(doc), device_token=token)


@router.get("/devices/{device_id}/telemetry", response_model=list[TelemetryPoint])
def device_telemetry(device_id: str, _: Viewer, services: ServicesDep,
                     minutes: int = Query(30, ge=1, le=1440)) -> list[TelemetryPoint]:
    services.devices.get_doc(device_id)
    return services.devices.telemetry_history(device_id, minutes)


@router.get("/devices/{device_id}/commands", response_model=list[CommandOut])
def device_commands(device_id: str, _: Viewer, services: ServicesDep) -> list[CommandOut]:
    services.devices.get_doc(device_id)
    return services.commands.list_for(device_id)


# --- simulator controls (all actions are labelled SIMULATED) ------------------------------
class SimDeviceCreate(Schema):
    name: str = Field(min_length=1, max_length=64)
    location: str | None = Field(default="Demo farm (simulated)", max_length=120)


class SimConnection(Schema):
    action: Literal["connect", "disconnect", "connection_lost"]


class SimFaults(Schema):
    tank_level_pct: float | None = Field(default=None, ge=0, le=100)
    battery_pct: float | None = Field(default=None, ge=0, le=100)
    fail_next_command: bool | None = None
    ignore_commands: bool | None = None
    sensor_fault: bool | None = None


class SimScan(Schema):
    sample_class: Literal["healthy", "early_blight", "late_blight"] | None = None


def _require_simulator(services) -> None:
    if not services.settings.simulator_enabled:
        raise ValidationAppError("Simulator is disabled (SIMULATOR_ENABLED=false)")


@router.get("/simulator/status", tags=["simulator"])
def simulator_status(_: Viewer, services: ServicesDep) -> dict:
    return {"enabled": services.settings.simulator_enabled, "tick_seconds": services.settings.simulator_tick_seconds,
            "devices": services.simulator.status() if services.settings.simulator_enabled else [],
            "samples": services.simulator.list_samples()}


@router.post("/simulator/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED, tags=["simulator"])
def simulator_create(body: SimDeviceCreate, user: Operator, services: ServicesDep) -> DeviceOut:
    _require_simulator(services)
    doc = services.simulator.create_device(body.name, body.location, actor=user.actor)
    return services.devices.to_out(doc)


@router.post("/simulator/devices/{device_id}/connection", tags=["simulator"])
def simulator_connection(device_id: str, body: SimConnection, user: Operator, services: ServicesDep) -> dict:
    _require_simulator(services)
    services.simulator.set_connection(device_id, body.action, actor=user.actor)
    return services.simulator.status_of(device_id)


@router.patch("/simulator/devices/{device_id}", tags=["simulator"])
def simulator_faults(device_id: str, body: SimFaults, user: Operator, services: ServicesDep) -> dict:
    _require_simulator(services)
    return services.simulator.set_faults(device_id, actor=user.actor, **body.model_dump())


@router.post("/simulator/devices/{device_id}/scan", response_model=ScanOut, tags=["simulator"])
def simulator_scan(device_id: str, body: SimScan, user: Operator, services: ServicesDep) -> ScanOut:
    _require_simulator(services)
    doc, _ = services.simulator.submit_sample_scan(device_id, body.sample_class, actor=user.actor)
    return services.scans.to_out(doc)
