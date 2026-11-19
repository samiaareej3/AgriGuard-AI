"""Application settings loaded from environment variables and an optional .env file.

All configuration lives here so that the rest of the code base never reads
``os.environ`` directly. Values are validated at startup; invalid configuration
fails fast with a clear error instead of surfacing later at request time.

Operational *policy* (confidence threshold, cooldowns, approval rules, ...) is
NOT here: it is stored in the database and editable from the dashboard. The
values below only seed that policy the first time the app starts.
"""

from __future__ import annotations

import secrets
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

DEV_ADMIN_PASSWORD = "agriguard-dev"  # only ever accepted outside production


class Environment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---------------------------------------------------------
    app_name: str = "AgriGuard API"
    app_version: str = "1.0.0"
    environment: Environment = Environment.DEVELOPMENT
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_json: bool = True

    # --- CORS ----------------------------------------------------------------
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # --- Database ------------------------------------------------------------
    # When unset the API runs on an in-memory store (data lost on restart) and
    # says so on the readiness endpoint and in the dashboard.
    mongodb_uri: str | None = None
    database_name: str = "agriguard_db"
    mongodb_timeout_ms: int = Field(default=5000, ge=500, le=60000)

    # --- Auth ----------------------------------------------------------------
    secret_key: str | None = None  # random per-process in dev if unset
    token_ttl_minutes: int = Field(default=720, ge=5, le=10080)
    admin_username: str = "admin"
    admin_password: str | None = None

    # --- Uploads -------------------------------------------------------------
    upload_dir: Path = BACKEND_DIR / "uploads"
    max_upload_mb: float = Field(default=5.0, gt=0, le=25)
    max_image_pixels: int = Field(default=40_000_000, ge=10_000)
    upload_retention_days: int = Field(default=30, ge=1)
    log_retention_days: int = Field(default=90, ge=1)

    # --- AI model ------------------------------------------------------------
    model_path: Path = REPO_DIR / "ai_training" / "models" / "agriguard_model.keras"
    model_config_path: Path = REPO_DIR / "ai_training" / "models" / "agriguard_model_config.json"
    model_enabled: bool = True
    default_confidence_threshold: float = Field(default=0.75, ge=0.5, le=0.99)

    # --- Simulator -----------------------------------------------------------
    simulator_enabled: bool = True
    simulator_seed_devices: int = Field(default=2, ge=0, le=10)
    simulator_tick_seconds: float = Field(default=5.0, ge=0.2, le=60)
    sample_images_dir: Path = BACKEND_DIR / "sample_images"
    background_tasks_enabled: bool = True

    # --- External data ---------------------------------------------------------
    location_name: str = "Hyderabad, Telangana"
    location_lat: float = Field(default=17.385, ge=-90, le=90)
    location_lon: float = Field(default=78.4867, ge=-180, le=180)
    weather_cache_minutes: int = Field(default=30, ge=1, le=1440)
    external_http_timeout_s: float = Field(default=10.0, ge=1, le=60)
    external_data_enabled: bool = True

    # --- Rate limits (requests per minute) -------------------------------------
    rate_limit_login_per_min: int = 10
    rate_limit_upload_per_min: int = 30
    rate_limit_device_per_min: int = 240

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid log level: {value}")
        return level

    @field_validator("mongodb_uri", "secret_key", "admin_password", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("mongodb_uri")
    @classmethod
    def _valid_mongo_scheme(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URI must start with mongodb:// or mongodb+srv://")
        return value

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        if self.environment is Environment.PRODUCTION:
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origins are not allowed in production")
            if not self.secret_key or len(self.secret_key) < 32:
                raise ValueError("SECRET_KEY (>=32 chars) is required in production")
            if not self.admin_password or self.admin_password == DEV_ADMIN_PASSWORD:
                raise ValueError("A non-default ADMIN_PASSWORD is required in production")
        if self.secret_key is None:
            # Tokens become invalid on restart; acceptable for local development.
            object.__setattr__(self, "secret_key", secrets.token_urlsafe(48))
        return self

    @property
    def database_configured(self) -> bool:
        return self.mongodb_uri is not None

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def effective_admin_password(self) -> str:
        return self.admin_password or DEV_ADMIN_PASSWORD

    @property
    def using_dev_admin_password(self) -> bool:
        return self.admin_password is None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
