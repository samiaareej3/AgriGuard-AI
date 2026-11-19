from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from app.routes.deps import ServicesDep, Viewer
from app.services.weather import SOURCES

router = APIRouter(tags=["dashboard & insights"])


@router.get("/dashboard/summary")
def summary(_: Viewer, services: ServicesDep) -> dict:
    data = services.analytics.summary()
    data["recent_events"] = services.bus.recent(15)[::-1]
    data["model"] = {"state": services.inference.state, "version": services.inference.model_version}
    data["database_mode"] = services.db.mode
    return data


@router.get("/analytics")
def analytics(_: Viewer, services: ServicesDep, days: int = Query(14, ge=1, le=90)) -> dict:
    return services.analytics.analytics(days)


@router.get("/logs")
def logs(_: Viewer, services: ServicesDep, category: str | None = Query(None, max_length=32),
         level: Literal["debug", "info", "warning", "error", "critical"] | None = None,
         device_id: str | None = None, page: int = Query(1, ge=1),
         page_size: int = Query(50, ge=1, le=200)) -> dict:
    docs, total = services.audit.list(category=category, level=level, device_id=device_id, page=page,
                                      page_size=page_size)
    items = [{**{k: v for k, v in d.items() if k != "_id"}, "id": d["_id"]} for d in docs]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/events/recent")
def recent_events(_: Viewer, services: ServicesDep, limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    return services.bus.recent(limit)[::-1]


@router.get("/system/info")
def system_info(_: Viewer, services: ServicesDep) -> dict:
    s = services.settings
    return {
        "app": {"name": s.app_name, "version": s.app_version, "environment": s.environment.value},
        "database": {"mode": services.db.mode, "name": s.database_name,
                     "persistent": services.db.mode == "mongodb"},
        "model": services.inference.info(),
        "simulator": {"enabled": s.simulator_enabled, "tick_seconds": s.simulator_tick_seconds,
                      "devices": len(services.simulator.agents)},
        "uploads": {"max_mb": s.max_upload_mb, "retention_days": s.upload_retention_days,
                    "allowed": ["image/jpeg", "image/png", "image/webp"]},
        "location": {"name": s.location_name, "lat": s.location_lat, "lon": s.location_lon},
        "security": {"dev_admin_password_in_use": s.using_dev_admin_password,
                     "cors_origins": s.cors_origins, "token_ttl_minutes": s.token_ttl_minutes},
        "realtime": {"websocket_subscribers": services.bus.subscriber_count},
    }


@router.get("/insights/weather")
async def weather(_: Viewer, services: ServicesDep, refresh: bool = False) -> dict:
    return await run_in_threadpool(services.weather.get, "forecast", refresh)


@router.get("/insights/climate")
async def climate(_: Viewer, services: ServicesDep, refresh: bool = False) -> dict:
    return await run_in_threadpool(services.weather.get, "climate", refresh)


@router.get("/insights/sources")
def sources(_: Viewer) -> list[dict]:
    return SOURCES
