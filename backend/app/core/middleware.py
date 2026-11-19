"""HTTP middleware: request correlation IDs and request timing logs."""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

REQUEST_ID_HEADER = "X-Request-ID"
# Accept caller-supplied IDs only if they are short and safe to echo/log.
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logger = logging.getLogger("agriguard.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            logger.info(
                "request completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                },
            )
            request_id_ctx.reset(token)
