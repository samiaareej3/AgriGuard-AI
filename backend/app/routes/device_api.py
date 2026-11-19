"""Device ↔ backend contract v1 (used by real ESP32-CAM firmware).

Authentication: ``X-Device-Token: <token returned at registration>``.
See docs/DEVICE_API.md for examples, retry behaviour and idempotency.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Header, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.routes.deps import DeviceDep, ServicesDep
from app.routes.upload import read_limited
from app.schemas.device import CommandOut, CommandResult, HeartbeatRequest, HeartbeatResponse
from app.schemas.scan import ScanOut

router = APIRouter(prefix="/device", tags=["device-api (v1 contract)"])


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(body: HeartbeatRequest, device: DeviceDep, services: ServicesDep) -> HeartbeatResponse:
    return services.gateway.heartbeat(device, body)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT,
             summary="Graceful disconnect (device going offline)")
def disconnect(device: DeviceDep, services: ServicesDep) -> None:
    services.gateway.disconnect(device)


@router.get("/commands/next", response_model=CommandOut | None,
            responses={204: {"description": "No pending command"}})
def next_command(device: DeviceDep, services: ServicesDep, response: Response):
    cmd = services.gateway.next_command(device)
    if cmd is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return services.commands.to_out(cmd)


@router.post("/commands/{command_id}/ack", response_model=CommandOut,
             summary="Acknowledge a command (idempotent)")
def ack_command(command_id: str, device: DeviceDep, services: ServicesDep) -> CommandOut:
    return services.commands.to_out(services.gateway.acknowledge(device, command_id))


@router.post("/commands/{command_id}/result", response_model=CommandOut,
             summary="Report completion or failure (idempotent)")
def command_result(command_id: str, body: CommandResult, device: DeviceDep, services: ServicesDep) -> CommandOut:
    return services.commands.to_out(services.gateway.report_result(device, command_id, body))


@router.post("/scans", response_model=ScanOut, status_code=status.HTTP_201_CREATED,
             summary="Upload a captured leaf image (multipart field 'image')")
async def upload_scan(
    device: DeviceDep, services: ServicesDep, response: Response,
    image: UploadFile = File(...),
    idempotency_key: Annotated[str | None, Header(max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")] = None,
) -> ScanOut:
    data = await read_limited(image, services.settings.max_upload_bytes)
    doc, created = await run_in_threadpool(
        services.gateway.submit_scan, device, data, image.filename, image.content_type,
        f"{device['_id']}:{idempotency_key}" if idempotency_key else None,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return services.scans.to_out(doc)
