"""Wires all services together (simple manual dependency injection)."""

from __future__ import annotations

import asyncio
import logging
import time

from app.adapters.gateway import DeviceGateway
from app.adapters.simulator import SimulatorManager
from app.core.config import Settings
from app.core.ratelimit import RateLimiter
from app.db.client import Database
from app.services import retention
from app.services.analytics import AnalyticsService
from app.services.audit import AuditLog
from app.services.devices import CommandService, DeviceService
from app.services.events import EventBus
from app.services.inference import InferenceService
from app.services.policy import EmergencyStopService, PolicyService
from app.services.scans import ScanService
from app.services.spray import SprayService
from app.services.users import UserService
from app.services.weather import WeatherService

logger = logging.getLogger("agriguard.services")


class Services:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings)
        self.bus = EventBus()
        self.rate_limiter = RateLimiter()
        self.audit = AuditLog(self.db, self.bus)
        self.policy = PolicyService(self.db, settings)
        self.estop = EmergencyStopService(self.db)
        self.users = UserService(self.db, settings)
        self.devices = DeviceService(self.db, self.bus, self.audit, self.policy)
        self.commands = CommandService(self.db, self.bus)
        self.inference = InferenceService(settings.model_path, settings.model_config_path, settings.model_enabled)
        self.weather = WeatherService(self.db, settings)
        self.spray = SprayService(
            self.db, self.bus, self.audit, self.policy, self.estop, self.devices, self.commands,
            model_labels=lambda: self.inference.classes, weather_snapshot=self.weather.snapshot,
        )
        self.scans = ScanService(self.db, settings, self.bus, self.audit, self.policy, self.inference, self.spray)
        self.gateway = DeviceGateway(self.devices, self.commands, self.spray, self.scans, self.estop,
                                     self.policy, heartbeat_interval_s=settings.simulator_tick_seconds)
        self.simulator = SimulatorManager(self.gateway, self.devices, self.audit, settings.sample_images_dir,
                                          settings.simulator_tick_seconds)
        self.analytics = AnalyticsService(self.db, self.devices, self.estop)
        self._task: asyncio.Task | None = None

    # -- lifecycle ------------------------------------------------------------------
    def startup(self, load_model: bool = True) -> None:
        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        self.db.connect()
        if self.db.last_error:
            logger.error("starting without a reachable database; data endpoints will return 503")
            return
        if self.users.bootstrap_admin() and self.settings.using_dev_admin_password:
            logger.warning("created development admin account with the DEFAULT password; change it in Settings")
        self.policy.get()
        if self.settings.simulator_enabled:
            self.simulator.attach_existing()
            self.simulator.seed(self.settings.simulator_seed_devices)
        if load_model:
            self.inference.load_in_background()

    async def start_background(self) -> None:
        self.bus.bind_loop(asyncio.get_running_loop())
        if self.settings.background_tasks_enabled:
            self._task = asyncio.create_task(self._loop(), name="agriguard-background")

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.db.close()

    def maintenance_tick(self) -> None:
        """One pass of periodic work (also called directly by tests)."""
        if self.settings.simulator_enabled:
            self.simulator.tick()
        self.devices.sweep_connectivity()
        self.spray.sweep()

    async def _loop(self) -> None:
        last_weather = 0.0
        last_retention = 0.0
        tick = min(self.settings.simulator_tick_seconds, 2.0)
        while True:
            try:
                await asyncio.to_thread(self.maintenance_tick)
                now = time.monotonic()
                if self.settings.external_data_enabled and now - last_weather > self.settings.weather_cache_minutes * 60:
                    last_weather = now
                    asyncio.get_running_loop().run_in_executor(None, self.weather.refresh)
                if now - last_retention > 86400:
                    last_retention = now
                    await asyncio.to_thread(
                        retention.cleanup, self.db, self.settings.upload_dir,
                        self.settings.upload_retention_days, self.settings.log_retention_days,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - keep the loop alive (e.g. during a DB outage)
                logger.exception("background maintenance failed")
            await asyncio.sleep(tick)
