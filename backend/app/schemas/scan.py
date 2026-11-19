from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.base import Schema, UTCDateTime
from app.schemas.spray import Decision

PredictionStatus = Literal["CONFIDENT", "UNCERTAIN", "MODEL_UNAVAILABLE"]


class ImageQuality(Schema):
    width: int
    height: int
    brightness: float = Field(description="Mean luminance 0-255")
    sharpness: float = Field(description="Variance of Laplacian; low = blurry")
    green_ratio: float = Field(description="Fraction of plant-coloured pixels (heuristic)")


class Prediction(Schema):
    status: PredictionStatus
    crop: str = "tomato"
    label: str | None = Field(default=None, description="Class id when CONFIDENT, else null")
    display_label: str
    top_label: str | None = Field(default=None, description="Highest-probability class, even if uncertain")
    confidence: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    threshold: float
    model_version: str | None = None
    inference_ms: float | None = None
    warnings: list[str] = Field(default_factory=list)
    timestamp: UTCDateTime


class ScanOut(Schema):
    id: str
    created_at: UTCDateTime
    source: Literal["dashboard", "device", "simulator"]
    simulated: bool
    device_id: str | None = None
    submitted_by: str | None = None
    original_filename: str | None = None
    content_type: str
    size_bytes: int
    quality: ImageQuality
    prediction: Prediction
    decision: Decision
    spray_operation_id: str | None = None
    notes: str | None = None
