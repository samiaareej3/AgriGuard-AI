from __future__ import annotations

from fastapi import Query
from fastapi.testclient import TestClient

from app.core.errors import ConflictError
from app.main import create_app


def _app_with_test_routes(make_settings):
    app = create_app(make_settings())

    @app.get("/_test/conflict")
    def conflict() -> None:
        raise ConflictError("spray already active", details={"device_id": "sim-1"})

    @app.get("/_test/crash")
    def crash() -> None:
        raise RuntimeError("db password=hunter2")

    @app.get("/_test/validate")
    def validate(n: int = Query(..., ge=1)) -> dict[str, int]:
        return {"n": n}

    return app


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    err = res.json()["error"]
    assert err["code"] == "NOT_FOUND"
    assert err["request_id"] == res.headers["X-Request-ID"]


def test_app_error_envelope(make_settings) -> None:
    with TestClient(_app_with_test_routes(make_settings)) as client:
        res = client.get("/_test/conflict")
    assert res.status_code == 409
    err = res.json()["error"]
    assert err == {
        "code": "CONFLICT",
        "message": "spray already active",
        "details": {"device_id": "sim-1"},
        "request_id": res.headers["X-Request-ID"],
    }


def test_validation_error_envelope(make_settings) -> None:
    with TestClient(_app_with_test_routes(make_settings)) as client:
        res = client.get("/_test/validate", params={"n": 0})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"][0]["loc"] == ["query", "n"]
    assert "input" not in err["details"][0]


def test_unhandled_error_hides_internals(make_settings) -> None:
    app = _app_with_test_routes(make_settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/_test/crash")
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in res.text
    assert "Traceback" not in res.text


def test_request_id_propagated_when_safe(client: TestClient) -> None:
    res = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert res.headers["X-Request-ID"] == "abc-123"


def test_request_id_replaced_when_unsafe(client: TestClient) -> None:
    for unsafe in ("has spaces <script>", "x" * 65):
        res = client.get("/api/v1/health", headers={"X-Request-ID": unsafe})
        assert res.headers["X-Request-ID"] != unsafe
        assert len(res.headers["X-Request-ID"]) == 32


def test_cors_allowlist(client: TestClient) -> None:
    allowed = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    denied = client.options(
        "/api/v1/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in denied.headers
