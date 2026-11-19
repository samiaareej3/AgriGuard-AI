from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Environment, Settings
from app.main import create_app

TEST_CONFIG = {
    "model_version": "test-model-1",
    "classes": ["early_blight", "healthy", "late_blight"],
    "display_names": {"early_blight": "Early Blight", "healthy": "Healthy", "late_blight": "Late Blight"},
    "input_size": 224,
    "preprocessing": "mobilenet_v2",
}
PROBS = {
    "early_blight": [0.92, 0.05, 0.03],
    "late_blight": [0.03, 0.05, 0.92],
    "healthy": [0.02, 0.95, 0.03],
    "uncertain": [0.45, 0.15, 0.40],
}


def leaf_image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (256, 256), seed: int = 0) -> bytes:
    """A synthetic leaf-coloured image with texture (passes quality heuristics)."""
    rng = np.random.default_rng(seed)
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    arr[..., 0] = 60 + rng.integers(0, 40, size=(size[1], size[0]))
    arr[..., 1] = 140 + rng.integers(0, 60, size=(size[1], size[0]))
    arr[..., 2] = 40 + rng.integers(0, 30, size=(size[1], size[0]))
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format=fmt)
    return buf.getvalue()


class FakeModel:
    """Injectable predictor; tests set ``next`` to the class whose probabilities to return."""

    def __init__(self) -> None:
        self.next = "early_blight"
        self.calls = 0

    def __call__(self, batch: np.ndarray) -> np.ndarray:
        assert batch.shape == (1, 224, 224, 3) and batch.dtype == np.float32
        assert batch.min() >= -1.0001 and batch.max() <= 1.0001
        self.calls += 1
        return np.array(PROBS[self.next], dtype=np.float32)


@pytest.fixture
def samples_dir(tmp_path: Path) -> Path:
    root = tmp_path / "samples"
    for i, cls in enumerate(("healthy", "early_blight", "late_blight")):
        (root / cls).mkdir(parents=True)
        (root / cls / f"{cls}_1.jpg").write_bytes(leaf_image_bytes(seed=i))
    return root


@pytest.fixture
def make_settings(tmp_path: Path, samples_dir: Path) -> Callable[..., Settings]:
    def _make(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "environment": Environment.TEST,
            "log_json": False,
            "log_level": "WARNING",
            "upload_dir": tmp_path / "uploads",
            "mongodb_uri": None,
            "model_enabled": False,
            "simulator_enabled": True,
            "simulator_seed_devices": 0,
            "background_tasks_enabled": False,
            "external_data_enabled": False,
            "sample_images_dir": samples_dir,
            "admin_password": "test-admin-password",
            "secret_key": "x" * 48,
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return _make


@pytest.fixture
def fake_model() -> FakeModel:
    return FakeModel()


@pytest.fixture
def app(make_settings: Callable[..., Settings], fake_model: FakeModel) -> FastAPI:
    application = create_app(make_settings(), load_model=False)
    application.state.services.inference.use_predictor(fake_model, TEST_CONFIG)
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def services(app: FastAPI, client: TestClient):
    """Services after app startup (database connected)."""
    return app.state.services


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    return _login(client, "admin", "test-admin-password")


@pytest.fixture
def operator_headers(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    res = client.post("/api/v1/users", headers=admin_headers,
                      json={"username": "op1", "password": "operator-password", "role": "operator"})
    assert res.status_code == 201, res.text
    return _login(client, "op1", "operator-password")


@pytest.fixture
def viewer_headers(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    client.post("/api/v1/users", headers=admin_headers,
                json={"username": "viewer1", "password": "viewer-password", "role": "viewer"})
    return _login(client, "viewer1", "viewer-password")


@pytest.fixture
def sim_device(client: TestClient, services, operator_headers) -> str:
    """A simulated device that is online (one heartbeat sent)."""
    res = client.post("/api/v1/simulator/devices", headers=operator_headers, json={"name": "Test Sim"})
    assert res.status_code == 201, res.text
    device_id = res.json()["id"]
    services.simulator.tick()
    return device_id
