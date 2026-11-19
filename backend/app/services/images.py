"""Upload validation, safe storage and image-quality heuristics.

Validation layers (all must pass):
1. Size: non-empty and <= MAX_UPLOAD_MB (enforced while reading, see routes).
2. Extension and declared MIME type in the allowlist.
3. Decoded content: Pillow must parse it, the real format must be JPEG/PNG/WebP,
   dimensions within limits (decompression-bomb guard).
Stored files are re-encoded as JPEG under a server-generated name. Re-encoding
drops EXIF metadata (e.g. GPS) and any trailing payload.
"""

from __future__ import annotations

import io
import os
import warnings
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import AppError
from app.schemas.scan import ImageQuality

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "MPO"}  # MPO = multi-picture JPEG from phones
MIN_SIDE = 64


class UnsupportedMediaError(AppError):
    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"


class InvalidImageError(AppError):
    status_code = 422
    code = "INVALID_IMAGE"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "PAYLOAD_TOO_LARGE"


@dataclass
class ValidatedImage:
    image: Image.Image  # RGB, orientation applied
    original_format: str
    size_bytes: int


def validate_image(
    data: bytes, filename: str | None, content_type: str | None, max_bytes: int, max_pixels: int
) -> ValidatedImage:
    if not data:
        raise InvalidImageError("Uploaded file is empty")
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"Image exceeds {max_bytes // (1024 * 1024)} MB limit")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedMediaError(
            "Unsupported file extension", details={"allowed": sorted(ALLOWED_EXTENSIONS)}
        )
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in ALLOWED_MIME:
        raise UnsupportedMediaError("Unsupported content type", details={"allowed": sorted(ALLOWED_MIME)})

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format or ""
                w, h = probe.size
                probe.verify()  # structural check without full decode
            if fmt not in ALLOWED_FORMATS:
                raise UnsupportedMediaError(f"Decoded format '{fmt}' is not allowed")
            if w * h > max_pixels:
                raise InvalidImageError("Image dimensions too large", details={"max_pixels": max_pixels})
            if min(w, h) < MIN_SIDE:
                raise InvalidImageError(f"Image too small; minimum side is {MIN_SIDE}px")
            img = Image.open(io.BytesIO(data))
            img.load()  # full decode catches truncated/corrupted data
            img = ImageOps.exif_transpose(img).convert("RGB")
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImageError("File is not a valid or complete image") from exc
    return ValidatedImage(image=img, original_format=fmt, size_bytes=len(data))


def quality_metrics(img: Image.Image) -> ImageQuality:
    """Cheap heuristics used for warnings (not for classification)."""
    w, h = img.size
    small = img.copy()
    small.thumbnail((512, 512))
    rgb = np.asarray(small, dtype=np.uint8)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)  # OpenCV hue range 0..179
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    # "Plant-coloured": brown/yellow lesions through leaf green (~10°-170°;
    # OpenCV hue units are degrees/2), reasonably saturated and not black.
    plant = (hue >= 5) & (hue <= 85) & (sat >= 50) & (val >= 40)
    return ImageQuality(
        width=w,
        height=h,
        brightness=round(float(gray.mean()), 1),
        sharpness=round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 1),
        green_ratio=round(float(plant.mean()), 3),
    )


def quality_warnings(q: ImageQuality) -> tuple[list[str], bool]:
    """Return (warnings, force_uncertain)."""
    warns: list[str] = []
    force = False
    if q.brightness < 35:
        warns.append("Image is very dark")
    elif q.brightness > 235:
        warns.append("Image is overexposed")
    if q.sharpness < 15:
        warns.append("Image appears blurry")
    if q.green_ratio < 0.03:  # all 644 PlantVillage test leaves score >= 0.058
        warns.append("Image may not show a plant leaf (very little leaf-coloured area)")
        force = True
    return warns, force


def save_jpeg(img: Image.Image, upload_dir: Path, scan_id: str) -> str:
    """Store as ``<upload_dir>/<YYYY-MM>/<scan_id>.jpg``; return the relative path."""
    from app.core.timeutil import utcnow

    sub = utcnow().strftime("%Y-%m")
    target_dir = upload_dir / sub
    target_dir.mkdir(parents=True, exist_ok=True)
    rel = f"{sub}/{scan_id}.jpg"
    img.save(upload_dir / rel, format="JPEG", quality=92)
    return rel
