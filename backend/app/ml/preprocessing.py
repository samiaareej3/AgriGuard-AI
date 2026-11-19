"""Single source of truth for image preprocessing.

Imported by BOTH the training pipeline (ai_training/scripts) and the backend
inference service, so train-time and serve-time preprocessing cannot drift.

Pipeline:
1. Apply EXIF orientation, convert to RGB.
2. Center-crop to a square (no-op for PlantVillage's 256x256 images; avoids
   distorting 4:3 ESP32-CAM frames).
3. Resize to 224x224 with bilinear filtering  -> uint8 array (H, W, 3).
4. MobileNetV2 scaling: x / 127.5 - 1  -> float32 in [-1, 1].
   (Identical to ``tf.keras.applications.mobilenet_v2.preprocess_input``; a
   test asserts the equivalence.)
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

INPUT_SIZE = 224
PREPROCESSING_ID = "mobilenet_v2"  # recorded in the model config file


def prepare_image(img: Image.Image, size: int = INPUT_SIZE) -> np.ndarray:
    """PIL image -> uint8 RGB array of shape (size, size, 3)."""
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    if img.size != (size, size):
        img = img.resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.uint8)


def mobilenet_v2_scale(arr: np.ndarray) -> np.ndarray:
    """uint8/float array in [0, 255] -> float32 in [-1, 1]."""
    return arr.astype(np.float32) / 127.5 - 1.0


def preprocess_for_model(img: Image.Image, size: int = INPUT_SIZE) -> np.ndarray:
    """PIL image -> model-ready batch of shape (1, size, size, 3)."""
    return mobilenet_v2_scale(prepare_image(img, size))[None, ...]
