"""Shared paths and constants for the AgriGuard training pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

TRAINING_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = TRAINING_DIR.parent
DATASET_DIR = TRAINING_DIR / "dataset"
RAW_DIR = DATASET_DIR / "plantvillage_src" / "raw" / "color"
LEAF_MAP = DATASET_DIR / "plantvillage_src" / "leaf-map.json"
WORK_DIR = DATASET_DIR / "_work"          # generated (git-ignored)
MANIFEST = WORK_DIR / "manifest.csv"
CACHE = WORK_DIR / "images_224.npz"
MODELS_DIR = TRAINING_DIR / "models"
REPORTS_DIR = TRAINING_DIR / "reports"
MODEL_PATH = MODELS_DIR / "agriguard_model.keras"
CONFIG_PATH = MODELS_DIR / "agriguard_model_config.json"

# Source folder -> AgriGuard class id. Order of CLASS_IDS defines model outputs.
SOURCE_FOLDERS = {
    "Tomato___Early_blight": "early_blight",
    "Tomato___Late_blight": "late_blight",
    "Tomato___healthy": "healthy",
}
CLASS_IDS = ["early_blight", "healthy", "late_blight"]
DISPLAY_NAMES = {"early_blight": "Early Blight", "healthy": "Healthy", "late_blight": "Late Blight"}
SEED = 42

# Import the backend's preprocessing so training and serving are identical.
sys.path.insert(0, str(REPO_DIR / "backend"))
from app.ml.preprocessing import INPUT_SIZE, PREPROCESSING_ID, mobilenet_v2_scale, prepare_image  # noqa: E402,F401
