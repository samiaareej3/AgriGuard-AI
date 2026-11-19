"""Shared API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable machine-readable error code, e.g. VALIDATION_ERROR")
    message: str = Field(description="Human-readable summary safe to show to clients")
    details: Any | None = Field(default=None, description="Optional structured context")
    request_id: str | None = Field(default=None, description="Correlation ID for log lookup")


class ErrorResponse(BaseModel):
    """Envelope used for every non-2xx response from the API."""

    error: ErrorDetail
