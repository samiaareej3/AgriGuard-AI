"""Device gateway — THE adapter boundary between devices and the platform.

Every device-originated action goes through these methods, whether it comes
from real ESP32-CAM firmware via the HTTP device API (app/routes/device_api.py)
or from the in-process simulator (app/adapters/simulator.py). Swapping the
simulator for hardware therefore changes nothing in the dashboard, API,
database or safety engine: real devices simply call the same endpoints.
"""

from __future__ import annotations

from app.schemas.device import CommandResult, HeartbeatRequest, HeartbeatResponse
from app.services.devices import CommandService, DeviceService
from app.services.policy import EmergencyStopService, PolicyService
from app.services.scans import ScanService
from app.services.spray import SprayService
from app.core.timeutil import utcnow


class DeviceGateway:
    def __init__(self, devices: DeviceService, commands: CommandService, spray: SprayService,
                 scans: ScanService, estop: EmergencyStopService, policy: PolicyService,
                 heartbeat_interval_s: float) -> None:
        self.devices, self.commands, self.spray, self.scans = devices, commands, spray, scans
        self.estop, self.policy = estop, policy
        self.heartbeat_interval_s = heartbeat_interval_s

    def heartbeat(self, device: dict, hb: HeartbeatRequest) -> HeartbeatResponse:
        doc = self.devices.heartbeat(device, hb)
        return HeartbeatResponse(
            server_time=utcnow(),
            device_id=doc["_id"],
            pending_commands=self.commands.pending_count(doc["_id"]),
            emergency_stop_active=bool(self.estop.is_active_or_unknown()),
            next_heartbeat_s=self.heartbeat_interval_s,
        )

    def disconnect(self, device: dict) -> None:
        self.devices.disconnect(device)

    def next_command(self, device: dict) -> dict | None:
        return self.commands.next_for(device["_id"])

    def acknowledge(self, device: dict, command_id: str) -> dict:
        cmd, changed = self.commands.acknowledge(command_id, device["_id"])
        if changed:
            self.spray.on_command_acknowledged(cmd)
        return cmd

    def report_result(self, device: dict, command_id: str, result: CommandResult) -> dict:
        cmd, changed = self.commands.finish(command_id, device["_id"], result.success, result.message)
        if changed:
            self.spray.on_command_finished(cmd, result.success, result.message)
        return cmd

    def submit_scan(self, device: dict, data: bytes, filename: str | None, content_type: str | None,
                    idempotency_key: str | None = None) -> tuple[dict, bool]:
        return self.scans.create(
            data=data, filename=filename, content_type=content_type,
            source="simulator" if device["simulated"] else "device",
            device_id=device["_id"], actor=f"device:{device['_id']}", simulated=device["simulated"],
            idempotency_key=idempotency_key,
        )
