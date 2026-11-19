"""Disease-classification inference service.

* Loads the Keras model and its JSON config ONCE (in a background thread at
  startup, so the API is responsive while TensorFlow initialises).
* Preprocesses with app.ml.preprocessing (shared with training).
* Never returns a confident label below the threshold or with an ambiguous
  top-2 margin: those become UNCERTAIN (=> REVIEW_REQUIRED downstream).
* Decision support only — dataset accuracy may not transfer to field photos.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

from app.core.timeutil import utcnow
from app.ml.preprocessing import INPUT_SIZE, PREPROCESSING_ID, preprocess_for_model
from app.schemas.health import ComponentStatus
from app.schemas.scan import Prediction

logger = logging.getLogger("agriguard.inference")

Predictor = Callable[[np.ndarray], np.ndarray]  # (1,H,W,3) float32 -> (n_classes,) probs

DISCLAIMER = (
    "AI-assisted decision support only, not a guaranteed field diagnosis. The model was trained "
    "and evaluated on PlantVillage lab images; accuracy on real field photographs may be lower."
)


class InferenceService:
    def __init__(self, model_path: Path, config_path: Path, enabled: bool = True) -> None:
        self.model_path = model_path
        self.config_path = config_path
        self.enabled = enabled
        self.state: Literal["disabled", "not_loaded", "loading", "ready", "failed"] = (
            "not_loaded" if enabled else "disabled"
        )
        self.error: str | None = None
        self.config: dict[str, Any] = {}
        self._predictor: Predictor | None = None
        self._lock = threading.Lock()
        self.load_seconds: float | None = None

    # -- loading -----------------------------------------------------------------
    def use_predictor(self, predictor: Predictor, config: dict[str, Any]) -> None:
        """Inject a predictor (used by tests and alternative runtimes)."""
        self._validate_config(config)
        self.config, self._predictor, self.state, self.error = config, predictor, "ready", None

    @staticmethod
    def _validate_config(cfg: dict[str, Any]) -> None:
        if cfg.get("preprocessing") != PREPROCESSING_ID:
            raise ValueError(f"model expects preprocessing {cfg.get('preprocessing')!r}, "
                             f"service implements {PREPROCESSING_ID!r}")
        if int(cfg.get("input_size", 0)) != INPUT_SIZE:
            raise ValueError("model input size mismatch")
        if not cfg.get("classes"):
            raise ValueError("config has no classes")

    def load(self) -> None:
        if not self.enabled:
            return
        self.state = "loading"
        t = time.perf_counter()
        try:
            if not self.model_path.exists() or not self.config_path.exists():
                raise FileNotFoundError(
                    "model artifact not found; train it with ai_training/scripts/train.py"
                )
            cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
            self._validate_config(cfg)
            import os
            os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
            import keras  # heavy import, deferred until needed

            model = keras.models.load_model(self.model_path, compile=False)
            n_out = int(model.output_shape[-1])
            if n_out != len(cfg["classes"]):
                raise ValueError(f"model has {n_out} outputs but config lists {len(cfg['classes'])} classes")

            def predictor(batch: np.ndarray) -> np.ndarray:
                return np.asarray(model(batch, training=False))[0]

            predictor(np.zeros((1, INPUT_SIZE, INPUT_SIZE, 3), dtype=np.float32))  # warm-up
            self.config, self._predictor, self.state, self.error = cfg, predictor, "ready", None
            self.load_seconds = round(time.perf_counter() - t, 2)
            logger.info("model loaded", extra={"model_version": cfg.get("model_version"),
                                               "load_seconds": self.load_seconds})
        except Exception as exc:  # noqa: BLE001 - report any load failure as unavailable
            self.state, self.error = "failed", f"{type(exc).__name__}: {exc}"
            logger.error("model load failed", extra={"error": self.error})

    def load_in_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.load, name="model-loader", daemon=True)
        thread.start()
        return thread

    # -- status --------------------------------------------------------------------
    @property
    def ready(self) -> bool:
        return self.state == "ready" and self._predictor is not None

    @property
    def classes(self) -> tuple[str, ...]:
        return tuple(self.config.get("classes", []))

    @property
    def model_version(self) -> str | None:
        return self.config.get("model_version")

    def display_name(self, label: str) -> str:
        return self.config.get("display_names", {}).get(label, label.replace("_", " ").title())

    def check(self) -> ComponentStatus:
        if self.state == "ready":
            return ComponentStatus(status="ok", detail=f"Model {self.model_version} loaded")
        if self.state == "loading":
            return ComponentStatus(status="degraded", detail="Model loading", critical=False)
        if self.state == "disabled":
            return ComponentStatus(status="not_configured", detail="Model disabled by config", critical=False)
        return ComponentStatus(
            status="not_loaded", detail=self.error or "Model not loaded; scans return REVIEW_REQUIRED",
            critical=False,
        )

    def info(self) -> dict[str, Any]:
        cfg = self.config
        return {
            "state": self.state,
            "error": self.error,
            "model_version": cfg.get("model_version"),
            "architecture": cfg.get("architecture"),
            "crop": cfg.get("crop"),
            "classes": [{"id": c, "name": self.display_name(c)} for c in cfg.get("classes", [])],
            "input_size": cfg.get("input_size"),
            "preprocessing": cfg.get("preprocessing_detail") or cfg.get("preprocessing"),
            "trained_at": cfg.get("trained_at"),
            "metrics": cfg.get("metrics"),
            "dataset": {k: (cfg.get("dataset") or {}).get(k) for k in
                        ("dataset", "source_url", "license", "citation", "class_counts", "split_method")},
            "load_seconds": self.load_seconds,
            "disclaimer": DISCLAIMER,
        }

    # -- inference -----------------------------------------------------------------
    def classify(
        self, img: Image.Image, threshold: float, min_margin: float, extra_warnings: list[str] | None = None,
        force_uncertain: bool = False,
    ) -> Prediction:
        warnings = list(extra_warnings or [])
        now = utcnow()
        if not self.ready:
            return Prediction(
                status="MODEL_UNAVAILABLE", display_label="Model unavailable", threshold=threshold,
                warnings=warnings + ["Classification model is not loaded; manual review required"],
                timestamp=now,
            )
        batch = preprocess_for_model(img)
        t = time.perf_counter()
        with self._lock:
            probs = np.asarray(self._predictor(batch), dtype=np.float64)
        elapsed_ms = round((time.perf_counter() - t) * 1000, 1)

        if probs.shape != (len(self.classes),) or not np.all(np.isfinite(probs)):
            return Prediction(
                status="UNCERTAIN", display_label="Review required", threshold=threshold,
                model_version=self.model_version, inference_ms=elapsed_ms,
                warnings=warnings + ["Model produced an invalid output"], timestamp=now,
            )
        probs = probs / probs.sum() if probs.sum() > 0 else probs
        order = np.argsort(probs)[::-1]
        top, second = int(order[0]), int(order[1]) if len(order) > 1 else None
        confidence = float(probs[top])
        margin = confidence - (float(probs[second]) if second is not None else 0.0)
        top_label = self.classes[top]

        reasons = []
        if confidence < threshold:
            reasons.append(f"Confidence {confidence:.1%} is below the {threshold:.0%} threshold")
        if margin < min_margin:
            reasons.append(f"Top two classes are too close ({margin:.1%} margin)")
        if force_uncertain:
            reasons.append("Image quality checks failed")
        status = "UNCERTAIN" if reasons else "CONFIDENT"

        return Prediction(
            status=status,
            label=top_label if status == "CONFIDENT" else None,
            display_label=self.display_name(top_label) if status == "CONFIDENT" else "Review required",
            top_label=top_label,
            confidence=round(confidence, 4),
            probabilities={c: round(float(p), 4) for c, p in zip(self.classes, probs)},
            threshold=threshold,
            model_version=self.model_version,
            inference_ms=elapsed_ms,
            warnings=warnings + reasons,
            timestamp=now,
        )
