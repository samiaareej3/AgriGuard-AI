"""End-to-end workflows through the API with the simulator and a fake model."""

from __future__ import annotations

import threading
from datetime import timedelta

from fastapi.testclient import TestClient

from app.core.timeutil import utcnow
from tests.conftest import leaf_image_bytes

API = "/api/v1"


def upload(client, headers, device_id=None, fmt="JPEG", name="leaf.jpg", ctype="image/jpeg", data=None):
    files = {"image": (name, data if data is not None else leaf_image_bytes(fmt), ctype)}
    form = {"device_id": device_id} if device_id else {}
    return client.post(f"{API}/scans", headers=headers, files=files, data=form)


def op_status(client, headers, op_id):
    return client.get(f"{API}/spray/operations/{op_id}", headers=headers).json()["status"]


# --- scans ---------------------------------------------------------------------------------
def test_upload_without_device_is_blocked(client: TestClient, operator_headers, fake_model):
    res = upload(client, operator_headers)
    assert res.status_code == 201, res.text
    scan = res.json()
    assert scan["prediction"]["label"] == "early_blight" and scan["prediction"]["status"] == "CONFIDENT"
    assert scan["decision"]["outcome"] == "BLOCKED"
    assert "No registered target device" in scan["decision"]["reasons"]
    assert scan["spray_operation_id"] is not None and scan["simulated"] is False


def test_healthy_scan_skips(client: TestClient, operator_headers, fake_model, sim_device):
    fake_model.next = "healthy"
    scan = upload(client, operator_headers, sim_device).json()
    assert scan["decision"]["outcome"] == "SKIP" and scan["spray_operation_id"] is None


def test_uncertain_scan_requires_review(client: TestClient, operator_headers, fake_model, sim_device):
    fake_model.next = "uncertain"
    scan = upload(client, operator_headers, sim_device).json()
    assert scan["prediction"]["status"] == "UNCERTAIN" and scan["prediction"]["label"] is None
    assert scan["decision"]["outcome"] == "REVIEW_REQUIRED" and scan["spray_operation_id"] is None


def test_model_unavailable_requires_review(client: TestClient, services, operator_headers, sim_device):
    services.inference._predictor = None
    services.inference.state = "failed"
    scan = upload(client, operator_headers, sim_device).json()
    assert scan["prediction"]["status"] == "MODEL_UNAVAILABLE"
    assert scan["decision"]["outcome"] == "REVIEW_REQUIRED"


def test_upload_validation_errors(client: TestClient, operator_headers, make_settings):
    assert upload(client, operator_headers, name="a.gif", ctype="image/gif").status_code == 415
    assert upload(client, operator_headers, data=b"not an image at all").status_code == 422
    big = b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 10)
    assert upload(client, operator_headers, data=big).status_code == 413
    assert upload(client, operator_headers, device_id="dev_missing").status_code == 404
    assert upload(client, operator_headers, fmt="PNG", name="leaf.png", ctype="image/png").status_code == 201


def test_viewer_cannot_upload(client: TestClient, viewer_headers):
    assert upload(client, viewer_headers).status_code == 403


def test_scan_history_filters_and_image(client: TestClient, operator_headers, fake_model, sim_device):
    for cls in ("healthy", "early_blight", "late_blight", "uncertain"):
        fake_model.next = cls
        upload(client, operator_headers, sim_device)
    page = client.get(f"{API}/scans?page_size=2", headers=operator_headers).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    assert client.get(f"{API}/scans?label=healthy", headers=operator_headers).json()["total"] == 1
    assert client.get(f"{API}/scans?label=uncertain", headers=operator_headers).json()["total"] == 1
    assert client.get(f"{API}/scans?outcome=SKIP", headers=operator_headers).json()["total"] == 1
    assert client.get(f"{API}/scans?q=late", headers=operator_headers).json()["total"] == 1
    assert client.get(f"{API}/scans?q=.*", headers=operator_headers).json()["total"] == 0  # regex escaped
    future = (utcnow() + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    assert client.get(f"{API}/scans", params={"date_from": future}, headers=operator_headers).json()["total"] == 0
    scan_id = page["items"][0]["id"]
    img = client.get(f"{API}/scans/{scan_id}/image", headers=operator_headers)
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get(f"{API}/scans/scan_nope", headers=operator_headers).status_code == 404


def test_device_scan_upload_idempotency(client: TestClient, services, operator_headers):
    res = client.post(f"{API}/devices", headers=operator_headers, json={"name": "cam"})
    dev = {"X-Device-Token": res.json()["device_token"], "Idempotency-Key": "capture-0001"}
    files = {"image": ("cap.jpg", leaf_image_bytes(), "image/jpeg")}
    first = client.post(f"{API}/device/scans", headers=dev, files=files)
    second = client.post(f"{API}/device/scans", headers=dev, files=files)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert services.db.scans.count_documents({}) == 1
    assert first.json()["source"] == "device"


# --- spray lifecycle ----------------------------------------------------------------------------
def test_full_spray_lifecycle(client: TestClient, services, operator_headers, sim_device):
    scan = upload(client, operator_headers, sim_device).json()
    assert scan["decision"]["outcome"] == "PENDING_APPROVAL"
    op_id = scan["spray_operation_id"]
    assert op_status(client, operator_headers, op_id) == "PENDING_APPROVAL"

    res = client.post(f"{API}/spray/operations/{op_id}/approve", headers=operator_headers, json={"note": "ok"})
    assert res.status_code == 200 and res.json()["status"] == "DISPATCHED"
    assert res.json()["decision"]["stage"] == "approval" and res.json()["approved_by"] == "user:op1"

    agent = services.simulator.agent(sim_device)
    agent.state.last_heartbeat = 0
    services.simulator.tick()  # poll + ack
    assert op_status(client, operator_headers, op_id) == "RUNNING"
    agent.state.pump_running_until = 0  # fast-forward the simulated pump
    services.simulator.tick()
    op = client.get(f"{API}/spray/operations/{op_id}", headers=operator_headers).json()
    assert op["status"] == "COMPLETED"
    assert [h["status"] for h in op["history"]] == ["PENDING_APPROVAL", "PENDING_APPROVAL", "DISPATCHED",
                                                     "RUNNING", "COMPLETED"]
    dev = services.db.devices.find_one({"_id": sim_device})
    assert dev["active_operation_id"] is None and dev["last_spray_completed_at"] is not None

    # cooldown now blocks the next operation at scan time
    scan2 = upload(client, operator_headers, sim_device).json()
    assert scan2["decision"]["outcome"] == "BLOCKED"
    assert any("cooldown" in r for r in scan2["decision"]["reasons"])


def test_double_approve_conflict(client: TestClient, operator_headers, sim_device):
    op_id = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    assert client.post(f"{API}/spray/operations/{op_id}/approve", headers=operator_headers, json={}).status_code == 200
    assert client.post(f"{API}/spray/operations/{op_id}/approve", headers=operator_headers, json={}).status_code == 409


def test_no_overlapping_operations(client: TestClient, services, operator_headers, sim_device):
    a = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    b = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    results = {}

    def approve(op):
        results[op] = client.post(f"{API}/spray/operations/{op}/approve", headers=operator_headers, json={}).json()

    threads = [threading.Thread(target=approve, args=(op,)) for op in (a, b)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    statuses = sorted(results[op]["status"] for op in (a, b))
    assert statuses == ["BLOCKED", "DISPATCHED"]
    assert services.db.device_commands.count_documents({"type": "SPRAY"}) == 1


def test_approval_reevaluates_device_state(client: TestClient, services, operator_headers, sim_device):
    op_id = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    services.simulator.set_connection(sim_device, "disconnect", actor="test")
    res = client.post(f"{API}/spray/operations/{op_id}/approve", headers=operator_headers, json={})
    assert res.json()["status"] == "BLOCKED"
    assert any("offline" in r for r in res.json()["decision"]["reasons"])
    assert services.db.device_commands.count_documents({"type": "SPRAY"}) == 0


def test_reject(client: TestClient, operator_headers, sim_device):
    op_id = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    res = client.post(f"{API}/spray/operations/{op_id}/reject", headers=operator_headers, json={"note": "not needed"})
    assert res.json()["status"] == "REJECTED"
    assert client.post(f"{API}/spray/operations/{op_id}/reject", headers=operator_headers, json={}).status_code == 409


def test_pending_expiry(client: TestClient, services, operator_headers, sim_device):
    op_id = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    services.db.spray_events.update_one({"_id": op_id}, {"$set": {"expires_at": utcnow() - timedelta(seconds=1)}})
    services.spray.sweep()
    assert op_status(client, operator_headers, op_id) == "EXPIRED"


def test_ack_timeout_fails_operation(client: TestClient, services, operator_headers, sim_device):
    services.simulator.set_faults(sim_device, actor="t", ignore_commands=True)
    op_id = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    client.post(f"{API}/spray/operations/{op_id}/approve", headers=operator_headers, json={})
    services.db.device_commands.update_many({}, {"$set": {"expires_at": utcnow() - timedelta(seconds=1)}})
    services.spray.sweep()
    assert op_status(client, operator_headers, op_id) == "FAILED"
    assert services.db.devices.find_one({"_id": sim_device})["active_operation_id"] is None


def test_device_failure_reported(client: TestClient, services, operator_headers, sim_device):
    services.simulator.set_faults(sim_device, actor="t", fail_next_command=True)
    op_id = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    client.post(f"{API}/spray/operations/{op_id}/approve", headers=operator_headers, json={})
    services.simulator.tick()
    op = client.get(f"{API}/spray/operations/{op_id}", headers=operator_headers).json()
    assert op["status"] == "FAILED" and "fault" in op["history"][-1]["message"]


def test_running_without_completion_times_out_and_sends_stop(client: TestClient, services, operator_headers,
                                                               sim_device):
    op_id = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    client.post(f"{API}/spray/operations/{op_id}/approve", headers=operator_headers, json={})
    services.simulator.tick()
    services.simulator.set_connection(sim_device, "connection_lost", actor="t")
    services.db.spray_events.update_one({"_id": op_id}, {"$set": {"started_at": utcnow() - timedelta(minutes=5)}})
    services.spray.sweep()
    assert op_status(client, operator_headers, op_id) == "FAILED"
    assert services.db.device_commands.count_documents({"type": "STOP", "device_id": sim_device}) == 1


def test_emergency_stop_flow(client: TestClient, services, operator_headers, admin_headers, sim_device):
    op_id = upload(client, operator_headers, sim_device).json()["spray_operation_id"]
    client.post(f"{API}/spray/operations/{op_id}/approve", headers=operator_headers, json={})
    services.simulator.tick()
    assert op_status(client, operator_headers, op_id) == "RUNNING"

    res = client.post(f"{API}/safety/emergency-stop", headers=operator_headers, json={"reason": "person in field"})
    assert res.status_code == 200 and res.json()["active"] is True
    assert op_status(client, operator_headers, op_id) == "ABORTED"
    services.simulator.tick()  # device receives STOP
    agent = services.simulator.agent(sim_device)
    assert agent.state.pump_running_until is None
    stop = services.db.device_commands.find_one({"type": "STOP", "device_id": sim_device})
    assert stop["status"] == "COMPLETED"

    # while active, new scans are blocked and approvals impossible
    scan = upload(client, operator_headers, sim_device).json()
    assert scan["decision"]["outcome"] == "BLOCKED"
    assert any("Emergency stop ACTIVE" in r for r in scan["decision"]["reasons"])

    # activation is idempotent; reset requires admin
    assert client.post(f"{API}/safety/emergency-stop", headers=operator_headers,
                       json={"reason": "again"}).json()["active"] is True
    assert client.post(f"{API}/safety/emergency-stop/reset", headers=operator_headers,
                       json={"reason": "clear"}).status_code == 403
    res = client.post(f"{API}/safety/emergency-stop/reset", headers=admin_headers, json={"reason": "area clear"})
    assert res.json()["active"] is False and res.json()["reset_by"] == "user:admin"
    logs = client.get(f"{API}/logs?category=safety", headers=admin_headers).json()["items"]
    assert {l["action"] for l in logs} >= {"estop_activated", "estop_reset"}


def test_auto_dispatch_when_approval_not_required(client: TestClient, services, admin_headers, operator_headers,
                                                  sim_device):
    policy = client.get(f"{API}/spray/policy", headers=admin_headers).json()
    body = {k: policy[k] for k in ("confidence_threshold", "min_confidence_margin", "spray_duration_s",
                                   "max_spray_duration_s", "cooldown_s", "device_offline_timeout_s",
                                   "min_tank_level_pct", "min_battery_pct", "pending_approval_ttl_s",
                                   "command_ack_timeout_s", "weather")}
    body |= {"require_operator_approval": False, "expected_version": policy["version"]}
    res = client.put(f"{API}/spray/policy", headers=admin_headers, json=body)
    assert res.status_code == 200 and res.json()["version"] == policy["version"] + 1
    # stale version -> conflict
    assert client.put(f"{API}/spray/policy", headers=admin_headers, json=body).status_code == 409
    scan = upload(client, operator_headers, sim_device).json()
    assert scan["decision"]["outcome"] == "AUTHORIZED"
    assert op_status(client, operator_headers, scan["spray_operation_id"]) == "DISPATCHED"


def test_policy_validation(client: TestClient, admin_headers, operator_headers):
    policy = client.get(f"{API}/spray/policy", headers=admin_headers).json()
    body = {k: v for k, v in policy.items() if k not in ("version", "sprayable_labels", "updated_at", "updated_by")}
    assert client.put(f"{API}/spray/policy", headers=operator_headers, json=body).status_code == 403
    body["spray_duration_s"] = 20
    body["max_spray_duration_s"] = 10
    assert client.put(f"{API}/spray/policy", headers=admin_headers, json=body).status_code == 422
    body["confidence_threshold"] = 0.2
    assert client.put(f"{API}/spray/policy", headers=admin_headers, json=body).status_code == 422


def test_evaluate_dry_run_has_no_side_effects(client: TestClient, services, operator_headers, sim_device):
    scan = upload(client, operator_headers, sim_device).json()
    n_ops = services.db.spray_events.count_documents({})
    res = client.post(f"{API}/spray/evaluate", headers=operator_headers, json={"scan_id": scan["id"]})
    assert res.status_code == 200 and res.json()["outcome"] in ("PENDING_APPROVAL", "BLOCKED")
    assert services.db.spray_events.count_documents({}) == n_ops
