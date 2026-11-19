from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.timeutil import utcnow

API = "/api/v1"


# --- auth ------------------------------------------------------------------------------
def test_login_and_me(client: TestClient, admin_headers):
    res = client.get(f"{API}/auth/me", headers=admin_headers)
    assert res.status_code == 200 and res.json()["role"] == "admin"


def test_bad_login(client: TestClient):
    res = client.post(f"{API}/auth/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401 and res.json()["error"]["code"] == "INVALID_CREDENTIALS"
    res = client.post(f"{API}/auth/login", json={"username": "nobody", "password": "x"})
    assert res.status_code == 401


def test_protected_endpoints_require_auth(client: TestClient):
    for path in ("/devices", "/scans", "/spray/operations", "/dashboard/summary", "/spray/policy"):
        assert client.get(API + path).status_code == 401
    assert client.get(f"{API}/devices", headers={"Authorization": "Bearer forged.token"}).status_code == 401


def test_role_enforcement(client: TestClient, viewer_headers, operator_headers):
    assert client.get(f"{API}/devices", headers=viewer_headers).status_code == 200
    assert client.post(f"{API}/safety/emergency-stop", headers=viewer_headers,
                       json={"reason": "test"}).status_code == 403
    assert client.post(f"{API}/safety/emergency-stop/reset", headers=operator_headers,
                       json={"reason": "test"}).status_code == 403
    assert client.get(f"{API}/users", headers=operator_headers).status_code == 403


def test_login_rate_limited(client: TestClient):
    codes = [client.post(f"{API}/auth/login", json={"username": "admin", "password": "bad"}).status_code
             for _ in range(12)]
    assert codes[-1] == 429


def test_change_password(client: TestClient, operator_headers):
    res = client.post(f"{API}/auth/change-password", headers=operator_headers,
                      json={"current_password": "operator-password", "new_password": "new-operator-pass"})
    assert res.status_code == 204
    assert client.post(f"{API}/auth/login", json={"username": "op1", "password": "new-operator-pass"}).status_code == 200


def test_duplicate_user(client: TestClient, admin_headers, operator_headers):
    res = client.post(f"{API}/users", headers=admin_headers,
                      json={"username": "op1", "password": "operator-password", "role": "operator"})
    assert res.status_code == 409


# --- real-device (ESP32) contract ----------------------------------------------------------
def _register(client, headers, name="ESP32 Bench"):
    res = client.post(f"{API}/devices", headers=headers, json={"name": name, "source": "esp32"})
    assert res.status_code == 201, res.text
    return res.json()["device"]["id"], {"X-Device-Token": res.json()["device_token"]}


def test_register_and_heartbeat(client: TestClient, operator_headers):
    device_id, dev = _register(client, operator_headers)
    d = client.get(f"{API}/devices/{device_id}", headers=operator_headers).json()
    assert d["connectivity"] == "never_seen" and d["simulated"] is False
    hb = {"status": "ok", "firmware_version": "1.0.0", "uptime_s": 12,
          "telemetry": {"battery_pct": 90, "tank_level_pct": 80, "temperature_c": 27.5}}
    res = client.post(f"{API}/device/heartbeat", headers=dev, json=hb)
    assert res.status_code == 200
    assert res.json()["emergency_stop_active"] is False and res.json()["pending_commands"] == 0
    d = client.get(f"{API}/devices/{device_id}", headers=operator_headers).json()
    assert d["connectivity"] == "online" and d["last_telemetry"]["temperature_c"] == 27.5
    tel = client.get(f"{API}/devices/{device_id}/telemetry", headers=operator_headers).json()
    assert len(tel) == 1 and tel[0]["simulated"] is False


def test_device_auth_required(client: TestClient):
    assert client.post(f"{API}/device/heartbeat", json={}).status_code == 401
    assert client.post(f"{API}/device/heartbeat", headers={"X-Device-Token": "agd_bogus"}, json={}).status_code == 401


def test_heartbeat_validation(client: TestClient, operator_headers):
    _, dev = _register(client, operator_headers)
    res = client.post(f"{API}/device/heartbeat", headers=dev, json={"telemetry": {"battery_pct": 150}})
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_offline_after_timeout_and_graceful_disconnect(client: TestClient, services, operator_headers):
    device_id, dev = _register(client, operator_headers)
    client.post(f"{API}/device/heartbeat", headers=dev, json={})
    services.db.devices.update_one({"_id": device_id}, {"$set": {"last_seen": utcnow() - timedelta(seconds=120)}})
    services.devices.sweep_connectivity()
    assert client.get(f"{API}/devices/{device_id}", headers=operator_headers).json()["connectivity"] == "offline"
    logs = client.get(f"{API}/logs?category=device", headers=operator_headers).json()["items"]
    assert any(l["action"] == "connectivity_offline" for l in logs)
    client.post(f"{API}/device/heartbeat", headers=dev, json={})
    assert client.get(f"{API}/devices/{device_id}", headers=operator_headers).json()["connectivity"] == "online"
    assert client.post(f"{API}/device/disconnect", headers=dev).status_code == 204
    assert client.get(f"{API}/devices/{device_id}", headers=operator_headers).json()["connectivity"] == "offline"


def test_no_pending_command_returns_204(client: TestClient, operator_headers):
    _, dev = _register(client, operator_headers)
    assert client.get(f"{API}/device/commands/next", headers=dev).status_code == 204


def test_command_ack_and_result_are_idempotent(client: TestClient, services, operator_headers):
    device_id, dev = _register(client, operator_headers)
    cmd = services.commands.enqueue(device_id, "STOP", {}, ttl_s=60)
    got = client.get(f"{API}/device/commands/next", headers=dev).json()
    assert got["id"] == cmd["_id"] and got["status"] == "DELIVERED"
    for _ in range(2):
        res = client.post(f"{API}/device/commands/{cmd['_id']}/ack", headers=dev)
        assert res.status_code == 200 and res.json()["status"] == "ACKNOWLEDGED"
    for _ in range(2):
        res = client.post(f"{API}/device/commands/{cmd['_id']}/result", headers=dev, json={"success": True})
        assert res.status_code == 200 and res.json()["status"] == "COMPLETED"


def test_device_cannot_touch_other_devices_commands(client: TestClient, services, operator_headers):
    a_id, _ = _register(client, operator_headers, "A")
    _, b_dev = _register(client, operator_headers, "B")
    cmd = services.commands.enqueue(a_id, "STOP", {}, ttl_s=60)
    assert client.post(f"{API}/device/commands/{cmd['_id']}/ack", headers=b_dev).status_code == 404


def test_delete_device_admin_only(client: TestClient, operator_headers, admin_headers):
    device_id, dev = _register(client, operator_headers)
    assert client.delete(f"{API}/devices/{device_id}", headers=operator_headers).status_code == 403
    assert client.delete(f"{API}/devices/{device_id}", headers=admin_headers).status_code == 204
    assert client.post(f"{API}/device/heartbeat", headers=dev, json={}).status_code == 401


def test_register_rejects_simulator_source(client: TestClient, operator_headers):
    res = client.post(f"{API}/devices", headers=operator_headers, json={"name": "x", "source": "simulator"})
    assert res.status_code == 422
