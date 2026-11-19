"""Aggregates all versioned API routers."""

from fastapi import APIRouter

from app.routes import auth, dashboard, device_api, devices, health, scans, spray, ws

api_router = APIRouter()
for module in (health, auth, devices, device_api, scans, spray, dashboard, ws):
    api_router.include_router(module.router)
