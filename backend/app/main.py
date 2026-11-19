"""AgriGuard FastAPI application factory.

Run locally (from the ``backend`` directory):

    ..\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.config import Settings, get_settings
from app.core.errors import error_response, register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, RequestContextMiddleware
from app.routes.api import api_router
from app.services.container import Services

logger = logging.getLogger("agriguard")


def create_app(settings: Settings | None = None, *, load_model: bool = True) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    services = Services(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services.startup(load_model=load_model)
        await services.start_background()
        logger.info("startup", extra={
            "environment": settings.environment.value, "version": settings.app_version,
            "database_mode": services.db.mode, "simulator": settings.simulator_enabled,
        })
        yield
        await services.shutdown()
        logger.info("shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "AgriGuard: AI-assisted tomato-leaf disease detection with a deterministic, independent "
            "spray-authorization (safety) engine and simulated ESP32-CAM devices.\n\n"
            "**A disease prediction never directly actuates a pump.** Operator endpoints use "
            "`Authorization: Bearer <token>` (POST /auth/login); device endpoints use `X-Device-Token`."
        ),
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.services = services
    app.state.readiness_checks = {"database": services.db.check, "model": services.inference.check}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER, "Idempotency-Key"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.exception_handler(DuplicateKeyError)
    async def _duplicate(request: Request, exc: DuplicateKeyError) -> JSONResponse:
        return error_response(request, 409, "CONFLICT", "Resource already exists")

    @app.exception_handler(PyMongoError)
    async def _db_error(request: Request, exc: PyMongoError) -> JSONResponse:
        logger.error("database error", extra={"error": type(exc).__name__, "path": request.url.path})
        return error_response(request, 503, "DATABASE_UNAVAILABLE",
                              "Database temporarily unavailable; please retry shortly")

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": settings.app_name, "docs": "/docs", "health": f"{settings.api_v1_prefix}/health"}

    return app


app = create_app()
