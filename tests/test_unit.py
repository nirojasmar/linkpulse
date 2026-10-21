"""Unit tests for Linkpulse."""

import pytest

from app.config import Settings
from app.schemas import LinkCreate
from app.services.links import generate_code


def test_generate_code_length():
    code = generate_code(7)
    assert len(code) == 7
    assert code.isalnum()


def test_generate_code_unique():
    codes = {generate_code(7) for _ in range(100)}
    assert len(codes) == 100


def test_url_validation_success():
    req = LinkCreate(url="https://example.com/some/path?param=1")
    assert req.url == "https://example.com/some/path?param=1"


def test_url_validation_invalid_scheme():
    with pytest.raises(ValueError, match="URL must start with http:// or https://"):
        LinkCreate(url="ftp://example.com")


def test_custom_code_validation():
    valid = LinkCreate(url="https://example.com", custom_code="valid_code-123")
    assert valid.custom_code == "valid_code-123"

    with pytest.raises(ValueError):
        LinkCreate(url="https://example.com", custom_code="no")  # Too short

    with pytest.raises(ValueError):
        LinkCreate(url="https://example.com", custom_code="invalid spaces")


def test_settings_secret_redaction():
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://myuser:mypassword@postgres-host:5432/linkpulse",
        REDIS_URL="redis://redis-host:6379/0",
        API_KEY="supersecretapikey",
    )
    redacted = settings.redacted_dict()
    assert redacted["api_key"] == "***REDACTED***"
    assert "mypassword" not in redacted["database_url"]
    assert "***" in redacted["database_url"]
    assert settings.db_target == "postgres-host:5432"
    assert settings.redis_target == "redis-host:6379"
