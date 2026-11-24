"""Tests for Pydantic Settings parsing and validation."""

from src.config import Settings


def test_default_settings() -> None:
    """Settings initialized with defaults must have sensible development defaults."""
    settings = Settings()
    assert settings.environment == "development"
    assert settings.api_port == 8000
    assert "http://localhost:5173" in settings.cors_origins


def test_cors_origins_json_parsing() -> None:
    """cors_origins specified as a JSON string array must parse properly into list[str]."""
    settings = Settings(
        cors_origins='["https://whiteboard.domain.com", "https://app.domain.com"]'  # type: ignore[arg-type]
    )
    assert settings.cors_origins == [
        "https://whiteboard.domain.com",
        "https://app.domain.com",
    ]


def test_cors_origins_comma_separated_parsing() -> None:
    """cors_origins specified as comma-separated string must parse properly into list[str]."""
    settings = Settings(
        cors_origins="https://alpha.example.com, https://beta.example.com"  # type: ignore[arg-type]
    )
    assert settings.cors_origins == [
        "https://alpha.example.com",
        "https://beta.example.com",
    ]
