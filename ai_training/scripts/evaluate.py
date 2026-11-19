"""Evaluate the trained model on the held-out TEST split (never used in training
or model selection) and record real metrics.

Outputs:
* ai_training/reports/metrics.json, confusion_matrix.png, training_curves.png,
  confidence_coverage.png
* metrics merged into ai_training/models/agriguard_model_config.json
* a few test images copied to backend/sample_images/<class>/ for the simulator

Usage (from repo root):
    .\\.venv\\Scripts\\python.exe ai_training\\scripts\\evaluate.py
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import time
from datetime import datetime, timezone

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_recall_fscore_support

from common import (
    CLASS_IDS, CONFIG_PATH, DISPLAY_NAMES, MODEL_PATH, RAW_DIR, REPO_DIR, REPORTS_DIR, mobilenet_v2_scale,
    prepare_image,
)
from train import load_arrays

SAMPLES_PER_CLASS = 4


def main() -> None:
    import keras

    model = keras.models.load_model(MODEL_PATH, compile=False)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    xte, yte, paths = load_arrays()["test"]
    print(f"test images: {len(yte)}")

    t = time.perf_counter()
    probs = model.predict(mobilenet_v2_scale(xte), batch_size=32, verbose=0)
    batch_seconds = time.perf_counter() - t
    pred = probs.argmax(1)
    conf = probs.max(1)

    # Single-image latency (end-to-end: decode + preprocess + predict), CPU.
    root = RAW_DIR.parents[1]
    latencies = []
    for p in paths[:60]:
        t = time.perf_counter()
        with Image.open(root / p) as img:
            arr = mobilenet_v2_scale(prepare_image(img))[None]
        model(arr, training=False)
        latencies.append((time.perf_counter() - t) * 1000)
    latencies = latencies[5:]  # drop warm-up

    acc = accuracy_score(yte, pred)
    p, r, f1, support = precision_recall_fscore_support(yte, pred, labels=range(len(CLASS_IDS)), zero_division=0)
    macro = precision_recall_fscore_support(yte, pred, average="macro", zero_division=0)
    cm = confusion_matrix(yte, pred, labels=range(len(CLASS_IDS)))
    print(classification_report(yte, pred, target_names=CLASS_IDS, digits=4))

    threshold = float(config.get("recommended_confidence_threshold", 0.75))
    coverage_rows = []
    for th in (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95):
        m = conf >= th
        coverage_rows.append({"threshold": th, "coverage": float(m.mean()),
                              "accuracy_on_confident": float((pred[m] == yte[m]).mean()) if m.any() else None})
    m = conf >= threshold

    metrics = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "split": "test (held-out; group-wise split by physical leaf, never used for training or model selection)",
        "n_test": int(len(yte)),
        "accuracy": round(float(acc), 4),
        "macro_precision": round(float(macro[0]), 4),
        "macro_recall": round(float(macro[1]), 4),
        "macro_f1": round(float(macro[2]), 4),
        "per_class": {
            c: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4), "f1": round(float(f1[i]), 4),
                "support": int(support[i])}
            for i, c in enumerate(CLASS_IDS)
        },
        "confusion_matrix": {"labels": CLASS_IDS, "rows_true_cols_pred": cm.tolist()},
        "at_recommended_threshold": {
            "threshold": threshold, "coverage": round(float(m.mean()), 4),
            "accuracy_on_confident": round(float((pred[m] == yte[m]).mean()), 4) if m.any() else None,
            "routed_to_review": int((~m).sum()),
        },
        "threshold_sweep": coverage_rows,
        "inference_time": {
            "device": "CPU (Intel i7-8550U laptop), TensorFlow " + __import__("tensorflow").__version__,
            "single_image_ms_mean": round(statistics.mean(latencies), 1),
            "single_image_ms_p95": round(float(np.percentile(latencies, 95)), 1),
            "batch32_throughput_img_per_s": round(len(yte) / batch_seconds, 1),
        },
        "caveat": "PlantVillage images are lab photos (single leaf, plain background). Accuracy on field "
                  "photographs is expected to be lower and has NOT been measured.",
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    config["metrics"] = metrics
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # --- plots -------------------------------------------------------------------
    names = [DISPLAY_NAMES[c] for c in CLASS_IDS]
    fig, ax = plt.subplots(figsize=(5, 4.2))
    ax.imshow(cm, cmap="Greens")
    ax.set_xticks(range(len(names)), names)
    ax.set_yticks(range(len(names)), names)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(f"Test confusion matrix (n={len(yte)})")
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, cm[i, j], ha="center", va="center", color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "confusion_matrix.png", dpi=130)
    plt.close(fig)

    hist = config.get("history", {})
    if hist.get("loss"):
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.5))
        for ax, key in zip(axes, ("loss", "accuracy")):
            ax.plot(hist[key], label="train")
            ax.plot(hist[f"val_{key}"], label="validation")
            n_head = hist["stage"].count("head")
            ax.axvline(n_head - 0.5, color="gray", ls="--", lw=1)
            ax.set_title(key)
            ax.set_xlabel("epoch (dashed = start of fine-tuning)")
            ax.legend()
        fig.tight_layout()
        fig.savefig(REPORTS_DIR / "training_curves.png", dpi=130)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(5, 3.5))
    ths = [row["threshold"] for row in coverage_rows]
    ax.plot(ths, [row["coverage"] for row in coverage_rows], marker="o", label="coverage (auto-labelled)")
    ax.plot(ths, [row["accuracy_on_confident"] or 0 for row in coverage_rows], marker="s",
            label="accuracy on confident")
    ax.set_xlabel("confidence threshold")
    ax.set_ylim(0.5, 1.01)
    ax.legend()
    ax.set_title("Threshold trade-off (test split)")
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "confidence_coverage.png", dpi=130)
    plt.close(fig)

    # --- simulator sample images (correctly classified test images) ---------------
    samples_root = REPO_DIR / "backend" / "sample_images"
    rng = np.random.default_rng(0)
    for ci, cls in enumerate(CLASS_IDS):
        dest = samples_root / cls
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        idx = np.nonzero((yte == ci) & (pred == ci))[0]
        for k, i in enumerate(rng.choice(idx, size=min(SAMPLES_PER_CLASS, len(idx)), replace=False)):
            shutil.copy(root / paths[i], dest / f"{cls}_{k + 1}.jpg")
    print(json.dumps({k: metrics[k] for k in ("accuracy", "macro_f1", "at_recommended_threshold",
                                              "inference_time")}, indent=2))


if __name__ == "__main__":
    main()
