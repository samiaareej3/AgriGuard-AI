from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.health import ComponentStatus


def test_liveness(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert datetime.fromisoformat(body["timestamp"]).tzinfo is not None  # UTC-aware


def test_readiness_degraded_without_database(client: TestClient) -> None:
    res = client.get("/api/v1/health/ready")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "degraded"
    assert body["components"]["database"]["status"] == "degraded"
    assert "In-memory" in body["components"]["database"]["detail"]
    assert body["components"]["database"]["critical"] is False


def test_readiness_not_ready_when_critical_component_unavailable(make_settings) -> None:
    app = create_app(make_settings())
    app.state.readiness_checks["model"] = lambda: ComponentStatus(status="unavailable")
    with TestClient(app) as client:
        res = client.get("/api/v1/health/ready")
    assert res.status_code == 503
    assert res.json()["status"] == "not_ready"


def test_readiness_survives_crashing_check(make_settings) -> None:
    app = create_app(make_settings())

    def boom() -> ComponentStatus:
        raise RuntimeError("secret connection string here")

    app.state.readiness_checks["database"] = boom
    with TestClient(app) as client:
        res = client.get("/api/v1/health/ready")
    assert res.status_code == 503
    db = res.json()["components"]["database"]
    assert db["status"] == "unavailable"
    assert "secret" not in res.text  # only the exception type is exposed


def test_startup_creates_upload_dir(make_settings, tmp_path) -> None:
    upload_dir = tmp_path / "new_uploads"
    with TestClient(create_app(make_settings(upload_dir=upload_dir))):
        assert upload_dir.is_dir()


def test_openapi_is_versioned(client: TestClient) -> None:
    res = client.get("/api/v1/openapi.json")
    assert res.status_code == 200
    assert "/api/v1/health" in res.json()["paths"]
