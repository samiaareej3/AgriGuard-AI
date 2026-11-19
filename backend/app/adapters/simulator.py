"""Simulated ESP32-CAM devices (clearly labelled SIMULATED everywhere).

Each ``SimulatedDevice`` emulates the planned firmware loop:
heartbeat with sensor readings -> poll command -> ack -> run pump for the
requested duration -> report result. It talks to the platform ONLY through
``DeviceGateway`` — the same boundary real hardware uses over HTTP.

Fault injection for demos and tests: connection loss (silent), graceful
disconnect, next-command failure, ignoring commands (ack timeout), low tank /
battery, sensor fault.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.adapters.gateway import DeviceGateway
from app.core.errors import NotFoundError, ValidationAppError
from app.schemas.device import CommandResult, DeviceCapabilities, DeviceRegister, HeartbeatRequest, Telemetry
from app.services.audit import AuditLog
from app.services.devices import DeviceService

logger = logging.getLogger("agriguard.simulator")

SAMPLE_CLASSES = ("healthy", "early_blight", "late_blight")


@dataclass
class SimState:
    connected: bool = True
    mode: str = "online"  # online | connection_lost | disconnected
    temperature_c: float = 28.0
    humidity_pct: float = 62.0
    battery_pct: float = 92.0
    tank_level_pct: float = 85.0
    rssi_dbm: float = -61.0
    sensor_fault: bool = False
    fail_next_command: bool = False
    ignore_commands: bool = False
    pump_running_until: float | None = None
    current_command: dict | None = None
    started_monotonic: float = field(default_factory=time.monotonic)
    last_heartbeat: float = 0.0


class SimulatedDevice:
    def __init__(self, device_id: str, token: str, name: str, seed: int) -> None:
        self.device_id = device_id
        self.token = token
        self.name = name
        self.rng = random.Random(seed)
        self.state = SimState(
            temperature_c=26 + self.rng.random() * 4, humidity_pct=55 + self.rng.random() * 15,
            battery_pct=85 + self.rng.random() * 14, tank_level_pct=70 + self.rng.random() * 30,
        )
        self.lock = threading.Lock()

    def _walk(self, value: float, step: float, lo: float, hi: float) -> float:
        return min(hi, max(lo, value + self.rng.uniform(-step, step)))

    def telemetry(self) -> Telemetry:
        s = self.state
        s.temperature_c = self._walk(s.temperature_c, 0.3, 18, 40)
        s.humidity_pct = self._walk(s.humidity_pct, 1.0, 30, 98)
        s.rssi_dbm = self._walk(s.rssi_dbm, 2.0, -90, -40)
        s.battery_pct = max(0.0, s.battery_pct - 0.02)
        pump = "running" if s.pump_running_until else "idle"
        if s.sensor_fault:
            return Telemetry(battery_pct=round(s.battery_pct, 1), rssi_dbm=round(s.rssi_dbm), pump_state=pump)
        return Telemetry(
            temperature_c=round(s.temperature_c, 1), humidity_pct=round(s.humidity_pct, 1),
            battery_pct=round(s.battery_pct, 1), tank_level_pct=round(s.tank_level_pct, 1),
            rssi_dbm=round(s.rssi_dbm), pump_state=pump,
        )

    def tick(self, gateway: DeviceGateway, heartbeat_every: float) -> None:
        with self.lock:
            s = self.state
            if not s.connected:
                return
            device = gateway.devices.authenticate(self.token)
            if device is None:  # deleted or token rotated
                s.connected = False
                return
            now = time.monotonic()
            self._advance_pump(gateway, device, now)
            if now - s.last_heartbeat >= heartbeat_every:
                status = "error" if s.sensor_fault else ("warning" if s.battery_pct < 20 else "ok")
                gateway.heartbeat(device, HeartbeatRequest(
                    status=status, firmware_version="sim-1.0.0", uptime_s=round(now - s.started_monotonic, 1),
                    telemetry=self.telemetry(),
                ))
                s.last_heartbeat = now
            if s.ignore_commands:
                return
            cmd = gateway.next_command(device)
            if cmd:
                self._handle(gateway, device, cmd, now)

    def _handle(self, gateway: DeviceGateway, device: dict, cmd: dict, now: float) -> None:
        s = self.state
        if cmd["type"] == "STOP":
            gateway.acknowledge(device, cmd["_id"])
            if s.current_command:
                gateway.report_result(device, s.current_command["_id"],
                                      CommandResult(success=False, message="Stopped by STOP command"))
            s.pump_running_until, s.current_command = None, None
            gateway.report_result(device, cmd["_id"], CommandResult(success=True, message="Pump stopped"))
            return
        if s.current_command and s.current_command["_id"] == cmd["_id"]:
            return  # re-delivery of the command we are already executing (idempotent)
        gateway.acknowledge(device, cmd["_id"])
        if s.fail_next_command:
            s.fail_next_command = False
            gateway.report_result(device, cmd["_id"], CommandResult(
                success=False, message="Simulated pump fault (injected)", actual_duration_s=0))
            return
        if s.tank_level_pct <= 0:
            gateway.report_result(device, cmd["_id"], CommandResult(success=False, message="Tank empty"))
            return
        duration = float(cmd["params"].get("duration_s", 0))
        s.current_command = cmd
        s.pump_running_until = now + duration

    def _advance_pump(self, gateway: DeviceGateway, device: dict, now: float) -> None:
        s = self.state
        if s.pump_running_until is None or s.current_command is None:
            return
        if now >= s.pump_running_until:
            duration = float(s.current_command["params"].get("duration_s", 0))
            s.tank_level_pct = max(0.0, s.tank_level_pct - duration * 0.8)  # ~0.8%/s, water only
            gateway.report_result(device, s.current_command["_id"], CommandResult(
                success=True, message="Simulated spray completed", actual_duration_s=duration))
            s.pump_running_until, s.current_command = None, None


class SimulatorManager:
    def __init__(self, gateway: DeviceGateway, devices: DeviceService, audit: AuditLog,
                 samples_dir: Path, tick_seconds: float) -> None:
        self.gateway = gateway
        self.devices = devices
        self.audit = audit
        self.samples_dir = samples_dir
        self.tick_seconds = tick_seconds
        self.agents: dict[str, SimulatedDevice] = {}
        self._lock = threading.Lock()
        self._rng = random.Random(7)

    # -- lifecycle --------------------------------------------------------------
    def attach_existing(self) -> None:
        """Re-attach simulated devices persisted in the DB (tokens are rotated
        because only hashes are stored)."""
        for i, doc in enumerate(self.devices.list_docs("simulator")):
            token = self.devices.rotate_token(doc["_id"])
            self.agents[doc["_id"]] = SimulatedDevice(doc["_id"], token, doc["name"], seed=100 + i)

    def seed(self, count: int) -> None:
        names = ["Greenhouse A — Row 1", "Greenhouse A — Row 2", "Field Plot North", "Field Plot South"]
        while len(self.agents) < count:
            idx = len(self.agents)
            self.create_device(names[idx] if idx < len(names) else f"Sim Device {idx + 1}",
                               location="Demo farm (simulated)", actor="system")

    def create_device(self, name: str, location: str | None, actor: str) -> dict:
        doc, token = self.devices.register(DeviceRegister(
            name=name, source="simulator", location=location, firmware_version="sim-1.0.0",
            capabilities=DeviceCapabilities(max_spray_duration_s=10),
        ), actor=actor)
        with self._lock:
            self.agents[doc["_id"]] = SimulatedDevice(doc["_id"], token, name, seed=len(self.agents) + 1)
        return doc

    def remove(self, device_id: str) -> None:
        with self._lock:
            self.agents.pop(device_id, None)

    def tick(self) -> None:
        for agent in list(self.agents.values()):
            try:
                agent.tick(self.gateway, heartbeat_every=self.tick_seconds)
            except Exception:  # noqa: BLE001 - one faulty agent must not stop the others
                logger.exception("simulator tick failed", extra={"device_id": agent.device_id})

    # -- controls ------------------------------------------------------------------
    def agent(self, device_id: str) -> SimulatedDevice:
        agent = self.agents.get(device_id)
        if agent is None:
            raise NotFoundError("Simulated device not found (or not attached to the simulator)")
        return agent

    def set_connection(self, device_id: str, action: str, actor: str) -> None:
        agent = self.agent(device_id)
        device = self.devices.get_doc(device_id)
        with agent.lock:
            if action == "connect":
                agent.state.connected, agent.state.mode, agent.state.last_heartbeat = True, "online", 0.0
            elif action == "disconnect":  # graceful: device tells the server
                agent.state.connected, agent.state.mode = False, "disconnected"
                self.gateway.disconnect(device)
            elif action == "connection_lost":  # silent: server notices via heartbeat timeout
                agent.state.connected, agent.state.mode = False, "connection_lost"
            else:
                raise ValidationAppError(f"Unknown action {action}")
        self.audit.record("simulator", action, f"[SIMULATED] {agent.name}: {action.replace('_', ' ')}",
                          actor=actor, device_id=device_id, simulated=True)
        if action == "connect":
            agent.tick(self.gateway, heartbeat_every=self.tick_seconds)

    def set_faults(self, device_id: str, actor: str, **faults) -> dict:
        agent = self.agent(device_id)
        with agent.lock:
            for key, value in faults.items():
                if value is None:
                    continue
                if key in ("tank_level_pct", "battery_pct"):
                    setattr(agent.state, key, float(value))
                elif key in ("fail_next_command", "ignore_commands", "sensor_fault"):
                    setattr(agent.state, key, bool(value))
        changed = {k: v for k, v in faults.items() if v is not None}
        self.audit.record("simulator", "faults_updated", f"[SIMULATED] {agent.name}: {changed}",
                          actor=actor, device_id=device_id, simulated=True)
        return self.status_of(device_id)

    def status_of(self, device_id: str) -> dict:
        s = self.agent(device_id).state
        return {
            "device_id": device_id, "connected": s.connected, "mode": s.mode,
            "tank_level_pct": round(s.tank_level_pct, 1), "battery_pct": round(s.battery_pct, 1),
            "pump_running": s.pump_running_until is not None, "fail_next_command": s.fail_next_command,
            "ignore_commands": s.ignore_commands, "sensor_fault": s.sensor_fault,
        }

    def status(self) -> list[dict]:
        return [self.status_of(d) for d in list(self.agents)]

    # -- sample scans ------------------------------------------------------------------
    def list_samples(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for cls in SAMPLE_CLASSES:
            folder = self.samples_dir / cls
            out[cls] = sorted(p.name for p in folder.glob("*.jpg")) if folder.is_dir() else []
        return out

    def submit_sample_scan(self, device_id: str, sample_class: str | None, actor: str) -> tuple[dict, bool]:
        agent = self.agent(device_id)
        if not agent.state.connected:
            raise ValidationAppError("Simulated device is offline; reconnect it before scanning")
        samples = self.list_samples()
        classes = [c for c in SAMPLE_CLASSES if samples.get(c)]
        if not classes:
            raise NotFoundError("No sample images found in backend/sample_images")
        if sample_class and sample_class not in classes:
            raise ValidationAppError(f"Unknown sample class; choose from {classes}")
        cls = sample_class or self._rng.choice(classes)
        name = self._rng.choice(samples[cls])
        data = (self.samples_dir / cls / name).read_bytes()
        device = self.devices.get_doc(device_id)
        self.audit.record("simulator", "sample_scan", f"[SIMULATED] {agent.name} captured sample '{cls}/{name}'",
                          actor=actor, device_id=device_id, simulated=True)
        return self.gateway.submit_scan(device, data, f"sim_{cls}_{name}", "image/jpeg")
