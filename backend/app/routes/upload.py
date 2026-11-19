from __future__ import annotations

from fastapi import UploadFile

from app.services.images import PayloadTooLargeError


async def read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read at most ``max_bytes`` (+1 to detect overflow) without buffering more."""
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"Image exceeds {max_bytes / (1024 * 1024):g} MB limit")
    return data
