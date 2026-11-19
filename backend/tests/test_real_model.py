"""Integration test against the real trained artifact (skipped if absent).

Loads ai_training/models/agriguard_model.keras through the production
InferenceService and classifies the bundled sample images (held-out test
images, see backend/sample_images/ATTRIBUTION.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings
from app.services.inference import InferenceService

settings = Settings(_env_file=None)
pytestmark = pytest.mark.skipif(
    not settings.model_path.exists(), reason="trained model artifact not present"
)


@pytest.fixture(scope="module")
def service() -> InferenceService:
    pytest.importorskip("keras")
    svc = InferenceService(settings.model_path, settings.model_config_path)
    svc.load()
    assert svc.state == "ready", svc.error
    return svc


def test_model_metadata(service: InferenceService):
    assert service.classes == ("early_blight", "healthy", "late_blight")
    info = service.info()
    assert info["metrics"] is not None and 0 < info["metrics"]["accuracy"] <= 1
    assert info["dataset"]["license"].startswith("CC BY-SA")


@pytest.mark.parametrize("cls", ["early_blight", "healthy", "late_blight"])
def test_sample_images_classified(service: InferenceService, cls: str):
    folder = settings.sample_images_dir / cls
    files = sorted(Path(folder).glob("*.jpg"))
    assert files, f"no samples for {cls}"
    for f in files:
        p = service.classify(Image.open(f), threshold=0.75, min_margin=0.15)
        assert p.top_label == cls, (f.name, p.probabilities)
        assert p.inference_ms is not None


def test_non_leaf_image_not_confident_disease(service: InferenceService):
    p = service.classify(Image.new("RGB", (300, 300), (128, 128, 128)), 0.75, 0.15, force_uncertain=True)
    assert p.status == "UNCERTAIN" and p.label is None
