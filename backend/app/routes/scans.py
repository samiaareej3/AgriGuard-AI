from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, File, Form, Query, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.core.errors import ValidationAppError
from app.routes.deps import Operator, ServicesDep, Viewer
from app.routes.upload import read_limited
from app.schemas.base import Page
from app.schemas.scan import ScanOut

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("", response_model=ScanOut, status_code=status.HTTP_201_CREATED,
             summary="Upload a leaf image for disease detection")
async def create_scan(
    request: Request, user: Operator, services: ServicesDep,
    image: UploadFile = File(..., description="JPEG, PNG or WebP leaf photo"),
    device_id: str | None = Form(default=None, max_length=64),
    notes: str | None = Form(default=None, max_length=500),
) -> ScanOut:
    services.rate_limiter.check(f"upload:{user.id}", services.settings.rate_limit_upload_per_min)
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > services.settings.max_upload_bytes + 64 * 1024:
        from app.services.images import PayloadTooLargeError
        raise PayloadTooLargeError(f"Image exceeds {services.settings.max_upload_mb:g} MB limit")
    if device_id:
        services.devices.get_doc(device_id)  # 404 if unknown
    data = await read_limited(image, services.settings.max_upload_bytes)
    doc, _ = await run_in_threadpool(
        lambda: services.scans.create(
            data=data, filename=image.filename, content_type=image.content_type, source="dashboard",
            device_id=device_id or None, actor=user.actor, simulated=False, notes=notes,
        )
    )
    return services.scans.to_out(doc)


@router.get("", response_model=Page[ScanOut])
def list_scans(
    _: Viewer, services: ServicesDep,
    q: str | None = Query(None, max_length=64),
    label: Literal["healthy", "early_blight", "late_blight", "uncertain"] | None = None,
    outcome: Literal["AUTHORIZED", "PENDING_APPROVAL", "BLOCKED", "REVIEW_REQUIRED", "SKIP"] | None = None,
    device_id: str | None = None,
    source: Literal["dashboard", "device", "simulator"] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Page[ScanOut]:
    if date_from and date_to and date_from > date_to:
        raise ValidationAppError("date_from must be before date_to")
    docs, total = services.scans.list(q=q, label=label, outcome=outcome, device_id=device_id, source=source,
                                      date_from=date_from, date_to=date_to, page=page, page_size=page_size)
    return Page[ScanOut](items=[services.scans.to_out(d) for d in docs], total=total, page=page,
                         page_size=page_size)


@router.get("/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: str, _: Viewer, services: ServicesDep) -> ScanOut:
    return services.scans.to_out(services.scans.get_doc(scan_id))


@router.get("/{scan_id}/image", response_class=FileResponse, summary="Stored (EXIF-stripped) scan image")
def scan_image(scan_id: str, _: Viewer, services: ServicesDep) -> FileResponse:
    path = services.scans.image_file(scan_id)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
