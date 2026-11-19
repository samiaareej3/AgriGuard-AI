from __future__ import annotations

import io
import json

import numpy as np
import pytest
from PIL import Image

from app.ml.preprocessing import mobilenet_v2_scale, prepare_image, preprocess_for_model
from app.services import images
from app.services.inference import InferenceService
from tests.conftest import PROBS, TEST_CONFIG, FakeModel, leaf_image_bytes

MAX = 5 * 1024 * 1024


# --- upload validation ---------------------------------------------------------------
@pytest.mark.parametrize("fmt,name,ctype", [("JPEG", "a.jpg", "image/jpeg"), ("PNG", "a.png", "image/png"),
                                            ("WEBP", "a.webp", "image/webp")])
def test_valid_images(fmt, name, ctype):
    v = images.validate_image(leaf_image_bytes(fmt), name, ctype, MAX, 40_000_000)
    assert v.image.mode == "RGB" and v.image.size == (256, 256)


def test_empty_file():
    with pytest.raises(images.InvalidImageError):
        images.validate_image(b"", "a.jpg", "image/jpeg", MAX, 40_000_000)


def test_oversized():
    with pytest.raises(images.PayloadTooLargeError):
        images.validate_image(b"x" * 101, "a.jpg", "image/jpeg", 100, 40_000_000)


@pytest.mark.parametrize("name,ctype", [("a.gif", "image/gif"), ("a.exe", "image/jpeg"), ("a.jpg", "text/html")])
def test_bad_extension_or_mime(name, ctype):
    with pytest.raises(images.UnsupportedMediaError):
        images.validate_image(leaf_image_bytes(), name, ctype, MAX, 40_000_000)


def test_disguised_non_image():
    with pytest.raises(images.InvalidImageError):
        images.validate_image(b"<script>alert(1)</script>" * 20, "a.jpg", "image/jpeg", MAX, 40_000_000)


def test_disallowed_real_format_with_jpg_extension():
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, format="GIF")
    with pytest.raises(images.UnsupportedMediaError):
        images.validate_image(buf.getvalue(), "a.jpg", "image/jpeg", MAX, 40_000_000)


def test_truncated_image():
    data = leaf_image_bytes()
    with pytest.raises(images.InvalidImageError):
        images.validate_image(data[: len(data) // 2], "a.jpg", "image/jpeg", MAX, 40_000_000)


def test_too_small_and_too_large_dimensions():
    with pytest.raises(images.InvalidImageError):
        images.validate_image(leaf_image_bytes(size=(32, 32)), "a.jpg", "image/jpeg", MAX, 40_000_000)
    with pytest.raises(images.InvalidImageError):
        images.validate_image(leaf_image_bytes(size=(300, 300)), "a.jpg", "image/jpeg", MAX, 50_000)


def test_saved_file_strips_exif(tmp_path):
    img = Image.open(io.BytesIO(leaf_image_bytes()))
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    v = images.validate_image(buf.getvalue(), "a.jpg", "image/jpeg", MAX, 40_000_000)
    rel = images.save_jpeg(v.image, tmp_path, "scan_x")
    assert b"SecretCam" not in (tmp_path / rel).read_bytes()


def test_quality_flags_non_leaf_image():
    gray = Image.new("RGB", (200, 200), (128, 128, 128))
    q = images.quality_metrics(gray)
    warns, force = images.quality_warnings(q)
    assert force and any("leaf" in w for w in warns)
    leaf = Image.open(io.BytesIO(leaf_image_bytes()))
    assert images.quality_warnings(images.quality_metrics(leaf))[1] is False


# --- preprocessing ------------------------------------------------------------------
def test_prepare_image_center_crops_and_resizes():
    img = Image.new("RGB", (400, 300), (255, 0, 0))
    img.paste((0, 0, 255), (0, 0, 50, 300))  # left band cropped away by center crop
    arr = prepare_image(img)
    assert arr.shape == (224, 224, 3) and arr.dtype == np.uint8
    assert arr[:, :, 2].max() == 0


def test_scaling_range():
    out = mobilenet_v2_scale(np.array([0, 127.5, 255], dtype=np.float32))
    assert np.allclose(out, [-1, 0, 1])
    batch = preprocess_for_model(Image.new("L", (300, 300), 200))  # grayscale converted to RGB
    assert batch.shape == (1, 224, 224, 3) and batch.dtype == np.float32


def test_scaling_matches_keras_mobilenet_v2():
    keras = pytest.importorskip("keras")
    x = np.random.default_rng(0).integers(0, 256, size=(2, 8, 8, 3)).astype(np.float32)
    expected = keras.applications.mobilenet_v2.preprocess_input(x.copy())
    assert np.allclose(mobilenet_v2_scale(x), expected, atol=1e-6)


# --- inference service ---------------------------------------------------------------
def _svc(tmp_path, model=None) -> InferenceService:
    s = InferenceService(tmp_path / "m.keras", tmp_path / "c.json")
    s.use_predictor(model or FakeModel(), TEST_CONFIG)
    return s


def leaf():
    return Image.open(io.BytesIO(leaf_image_bytes())).convert("RGB")


def test_confident_mapping(tmp_path):
    m = FakeModel()
    s = _svc(tmp_path, m)
    for cls in ("early_blight", "late_blight", "healthy"):
        m.next = cls
        p = s.classify(leaf(), 0.75, 0.15)
        assert p.status == "CONFIDENT" and p.label == cls and p.top_label == cls
        assert p.model_version == "test-model-1" and p.inference_ms is not None
        assert set(p.probabilities) == set(TEST_CONFIG["classes"])
        assert abs(sum(p.probabilities.values()) - 1) < 1e-3


def test_low_confidence_is_uncertain(tmp_path):
    m = FakeModel()
    m.next = "uncertain"
    p = _svc(tmp_path, m).classify(leaf(), 0.75, 0.15)
    assert p.status == "UNCERTAIN" and p.label is None and p.top_label == "early_blight"
    assert p.display_label == "Review required" and any("below" in w for w in p.warnings)


def test_threshold_is_configurable(tmp_path):
    m = FakeModel()
    m.next = "early_blight"  # 0.92
    assert _svc(tmp_path, m).classify(leaf(), 0.95, 0.15).status == "UNCERTAIN"
    assert _svc(tmp_path, m).classify(leaf(), 0.90, 0.15).status == "CONFIDENT"


def test_force_uncertain_from_quality(tmp_path):
    p = _svc(tmp_path).classify(leaf(), 0.75, 0.15, extra_warnings=["dark"], force_uncertain=True)
    assert p.status == "UNCERTAIN" and "dark" in p.warnings


def test_invalid_model_output(tmp_path):
    s = _svc(tmp_path, lambda b: np.array([np.nan, 0.5, 0.5]))
    assert s.classify(leaf(), 0.75, 0.15).status == "UNCERTAIN"
    s2 = _svc(tmp_path, lambda b: np.array([0.5, 0.5]))
    assert s2.classify(leaf(), 0.75, 0.15).status == "UNCERTAIN"


def test_model_unavailable(tmp_path):
    s = InferenceService(tmp_path / "missing.keras", tmp_path / "missing.json")
    s.load()
    assert s.state == "failed" and "not found" in s.error
    p = s.classify(leaf(), 0.75, 0.15)
    assert p.status == "MODEL_UNAVAILABLE" and p.label is None
    assert s.check().status == "not_loaded"


def test_config_mismatch_rejected(tmp_path):
    s = InferenceService(tmp_path / "m", tmp_path / "c")
    with pytest.raises(ValueError):
        s.use_predictor(FakeModel(), {**TEST_CONFIG, "preprocessing": "imagenet_caffe"})
    with pytest.raises(ValueError):
        s.use_predictor(FakeModel(), {**TEST_CONFIG, "input_size": 299})


def test_probs_constant_sanity():
    for v in PROBS.values():
        assert abs(sum(v) - 1) < 1e-6
    assert json.dumps(TEST_CONFIG)
