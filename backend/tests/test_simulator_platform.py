"""Simulator behaviour, analytics, insights, websocket, DB outage and retention."""

from __future__ import annotations

import os
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.timeutil import utcnow
from app.main import create_app
from app.services import retention
from app.services.weather import WeatherService

API = "/api/v1"


def test_seeded_devices_and_heartbeat(make_settings):
    app = create_app(make_settings(simulator_seed_devices=2), load_model=False)
    with TestClient(app) as client:
        services = app.state.services
        services.simulator.tick()
        headers = {"Authorization": "Bearer " + client.post(
            f"{API}/auth/login", json={"username": "admin", "password": "test-admin-password"}).json()["access_token"]}
        devices = client.get(f"{API}/devices", headers=headers).json()
        assert len(devices) == 2 and all(d["simulated"] and d["source"] == "simulator" for d in devices)
        assert all(d["connectivity"] == "online" for d in devices)
        assert devices[0]["last_telemetry"]["tank_level_pct"] is not None


def test_simulated_connection_lost_goes_offline_after_timeout(client, services, operator_headers, sim_device):
    services.simulator.set_connection(sim_device, "connection_lost", actor="t")
    d = client.get(f"{API}/devices/{sim_device}", headers=operator_headers).json()
    assert d["connectivity"] == "online"  # server hasn't noticed yet (honest)
    services.db.devices.update_one({"_id": sim_device}, {"$set": {"last_seen": utcnow() - timedelta(minutes=2)}})
    services.maintenance_tick()
    assert client.get(f"{API}/devices/{sim_device}", headers=operator_headers).json()["connectivity"] == "offline"
    client.post(f"{API}/simulator/devices/{sim_device}/connection", headers=operator_headers,
                json={"action": "connect"})
    assert client.get(f"{API}/devices/{sim_device}", headers=operator_headers).json()["connectivity"] == "online"


def test_sensor_fault_makes_device_unhealthy(client, services, operator_headers, sim_device, fake_model):
    client.patch(f"{API}/simulator/devices/{sim_device}", headers=operator_headers, json={"sensor_fault": True})
    services.simulator.agent(sim_device).state.last_heartbeat = 0
    services.simulator.tick()
    d = client.get(f"{API}/devices/{sim_device}", headers=operator_headers).json()
    assert d["reported_status"] == "error" and d["last_telemetry"]["tank_level_pct"] is None
    res = client.post(f"{API}/simulator/devices/{sim_device}/scan", headers=operator_headers,
                      json={"sample_class": "late_blight"})
    assert res.status_code == 200
    assert res.json()["decision"]["outcome"] == "BLOCKED" and res.json()["simulated"] is True


def test_low_tank_blocks(client, services, operator_headers, sim_device):
    client.patch(f"{API}/simulator/devices/{sim_device}", headers=operator_headers, json={"tank_level_pct": 3})
    services.simulator.agent(sim_device).state.last_heartbeat = 0
    services.simulator.tick()
    scan = client.post(f"{API}/simulator/devices/{sim_device}/scan", headers=operator_headers, json={}).json()
    assert scan["source"] == "simulator"
    if scan["decision"]["outcome"] not in ("SKIP", "REVIEW_REQUIRED"):
        assert any("tank" in r for r in scan["decision"]["reasons"])


def test_offline_sim_cannot_scan(client, operator_headers, sim_device):
    client.post(f"{API}/simulator/devices/{sim_device}/connection", headers=operator_headers,
                json={"action": "disconnect"})
    res = client.post(f"{API}/simulator/devices/{sim_device}/scan", headers=operator_headers, json={})
    assert res.status_code == 422


def test_simulator_status(client, operator_headers, sim_device):
    s = client.get(f"{API}/simulator/status", headers=operator_headers).json()
    assert s["enabled"] and s["devices"][0]["device_id"] == sim_device
    assert set(s["samples"]) == {"healthy", "early_blight", "late_blight"}


def test_summary_and_analytics(client, operator_headers, sim_device, fake_model):
    for cls in ("healthy", "early_blight"):
        fake_model.next = cls
        client.post(f"{API}/simulator/devices/{sim_device}/scan", headers=operator_headers, json={})
    s = client.get(f"{API}/dashboard/summary", headers=operator_headers).json()
    assert s["scans"]["total"] == 2 and s["scans"]["last_24h"] == 2 and s["devices"]["online"] == 1
    assert s["database_mode"] == "memory" and s["recent_events"]
    a = client.get(f"{API}/analytics?days=7", headers=operator_headers).json()
    assert a["range"]["days"] == 7 and len(a["scans_per_day"]) == 7
    assert a["totals"]["scans"] == 2 and a["label_distribution"] == {"healthy": 1, "early_blight": 1}
    assert sum(b["count"] for b in a["confidence_histogram"]) == 2
    assert client.get(f"{API}/analytics?days=0", headers=operator_headers).status_code == 422


def test_system_info(client, operator_headers):
    info = client.get(f"{API}/system/info", headers=operator_headers).json()
    assert info["model"]["state"] == "ready" and "decision support" in info["model"]["disclaimer"]
    assert info["database"]["persistent"] is False


def test_readiness_reports_components(client):
    body = client.get(f"{API}/health/ready").json()
    assert body["components"]["database"]["status"] == "degraded"
    assert body["components"]["model"]["status"] == "ok"
    assert body["status"] == "degraded"


def test_websocket_stream(client, admin_headers, operator_headers, sim_device):
    token = admin_headers["Authorization"].split()[1]
    with client.websocket_connect(f"{API}/ws/events?token={token}") as ws:
        assert ws.receive_json()["type"] == "hello"
        client.post(f"{API}/simulator/devices/{sim_device}/scan", headers=operator_headers, json={})
        types = set()
        for _ in range(10):
            types.add(ws.receive_json()["type"])
            if "scan.created" in types:
                break
        assert "scan.created" in types


def test_websocket_requires_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{API}/ws/events?token=bad") as ws:
            ws.receive_json()


# --- external data ---------------------------------------------------------------------------
def test_weather_live_stale_unavailable(services, make_settings):
    settings = make_settings(external_data_enabled=True)
    svc = WeatherService(services.db, settings)
    calls = {"n": 0}

    def ok():
        calls["n"] += 1
        return {"current": {"wind_speed_10m": 8.0}, "next_3h_max_precipitation_probability": 20}

    svc._fetchers["forecast"] = ok
    first = svc.get("forecast")
    assert first["available"] and first["freshness"] == "live" and first["source"] == "Open-Meteo Forecast API"
    svc.get("forecast")
    assert calls["n"] == 1  # cached
    snap = svc.snapshot()
    assert snap.available and snap.wind_kmh == 8.0 and snap.precipitation_probability_pct == 20

    def boom():
        raise TimeoutError("network down")

    svc._fetchers["forecast"] = boom
    stale = svc.get("forecast", force=True)
    assert stale["freshness"] == "stale" and stale["data"] is not None and "TimeoutError" in stale["error"]

    svc._fetchers["climate"] = boom
    svc.db.weather_records.delete_many({"key": "climate"})
    unavailable = svc.get("climate")
    assert unavailable["available"] is False and unavailable["data"] is None


def test_insights_endpoints_disabled_offline(client, operator_headers):
    w = client.get(f"{API}/insights/weather", headers=operator_headers).json()
    assert w["available"] is False and w["freshness"] == "unavailable"
    sources = client.get(f"{API}/insights/sources", headers=operator_headers).json()
    assert any(s["id"] == "open_meteo" and s["status"] == "integrated" for s in sources)


# --- database outage ----------------------------------------------------------------------------
def test_unreachable_mongodb_reports_not_ready(make_settings):
    app = create_app(make_settings(mongodb_uri="mongodb://127.0.0.1:1/?directConnection=true",
                                   mongodb_timeout_ms=500, simulator_enabled=False), load_model=False)
    with TestClient(app) as client:
        res = client.get(f"{API}/health/ready")
        assert res.status_code == 503 and res.json()["components"]["database"]["status"] == "unavailable"
        res = client.post(f"{API}/auth/login", json={"username": "admin", "password": "x"})
        assert res.status_code == 503 and res.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert client.get(f"{API}/health").status_code == 200


# --- retention ------------------------------------------------------------------------------------
def test_retention_removes_old_images(services, tmp_path):
    old = tmp_path / "up" / "2020-01"
    old.mkdir(parents=True)
    f_old, f_new = old / "a.jpg", old / "b.jpg"
    f_old.write_bytes(b"x")
    f_new.write_bytes(b"y")
    past = time.time() - 40 * 86400
    os.utime(f_old, (past, past))
    services.db.system_logs.insert_one({"_id": "l1", "ts": utcnow() - timedelta(days=200)})
    out = retention.cleanup(services.db, tmp_path / "up", upload_days=30, log_days=90)
    assert out["images"] == 1
    # old logs are gone (removed by the TTL index or by the cleanup itself)
    assert services.db.system_logs.count_documents({"_id": "l1"}) == 0
    assert not f_old.exists() and f_new.exists()
