from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings


def test_defaults_are_safe() -> None:
    s = Settings(_env_file=None)
    assert s.database_name == "agriguard_db"
    assert "*" not in s.cors_origins
    assert s.database_configured is False
    assert s.max_upload_bytes == 5 * 1024 * 1024


def test_cors_origins_parsed_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    s = Settings(_env_file=None)
    assert s.cors_origins == ["https://a.example", "https://b.example"]


def test_wildcard_cors_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment=Environment.PRODUCTION, cors_origins=["*"])


def test_invalid_mongodb_uri_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mongodb_uri="http://not-mongo")


def test_blank_mongodb_uri_means_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGODB_URI", "   ")
    assert Settings(_env_file=None).database_configured is False


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, log_level="LOUD")


def test_upload_limit_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_upload_mb=0)
