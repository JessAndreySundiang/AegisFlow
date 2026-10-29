"""Startup safety: real mode must fail closed to mock unless fully configured."""

from __future__ import annotations

import json

import pytest

from config import Settings

ENV_KEYS = (
    "AEGISFLOW_MODE",
    "AEGISFLOW_PROVIDER",
    "AEGISFLOW_MODEL",
    "AEGISFLOW_ALLOW_EXTERNAL_LLM",
    "AEGISFLOW_DATA_DIR",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AEGISFLOW_DATA_DIR", str(tmp_path / "data"))
    return monkeypatch


def test_defaults_to_mock_mode(clean_env):
    settings = Settings.from_env()

    assert settings.mode == "mock"
    assert settings.fallback_reason is None
    assert any("SIMULATED MODE" in warning for warning in settings.warnings)


def test_default_provider_is_gemini(clean_env):
    """Gemini is the primary: a bare model id is sent there, not to OpenRouter."""
    clean_env.setenv("AEGISFLOW_MODEL", "gemini-3.8-flash")

    settings = Settings.from_env()

    assert settings.provider == "gemini"
    assert settings.model_candidates() == (("gemini", "gemini-3.8-flash"),)


def test_cross_provider_slash_falls_back_to_mock(clean_env):
    """An ambiguous id must never be resolved by guessing at the provider."""
    clean_env.setenv("AEGISFLOW_MODE", "real")
    clean_env.setenv("AEGISFLOW_ALLOW_EXTERNAL_LLM", "true")
    clean_env.setenv("AEGISFLOW_MODEL", "openai/gpt-4o")
    clean_env.setenv("GOOGLE_API_KEY", "not-a-real-key")
    clean_env.setenv("OPENAI_API_KEY", "not-a-real-key")

    settings = Settings.from_env()

    assert settings.mode == "mock"
    assert settings.fallback_reason is not None
    assert "ambiguous" in settings.fallback_reason
    assert settings.describe()["model_candidates"] == [
        "(invalid AEGISFLOW_MODEL, see the fallback reason)"
    ]


def test_real_mode_without_authorization_falls_back(clean_env):
    clean_env.setenv("AEGISFLOW_MODE", "real")
    clean_env.setenv("AEGISFLOW_MODEL", "test-model")
    clean_env.setenv("OPENROUTER_API_KEY", "not-a-real-key")

    settings = Settings.from_env()

    assert settings.mode == "mock"
    assert settings.fallback_reason == "External LLM use was not authorized."


def test_real_mode_without_key_falls_back(clean_env):
    clean_env.setenv("AEGISFLOW_MODE", "real")
    clean_env.setenv("AEGISFLOW_PROVIDER", "openrouter")
    clean_env.setenv("AEGISFLOW_ALLOW_EXTERNAL_LLM", "true")
    clean_env.setenv("AEGISFLOW_MODEL", "test-model")

    settings = Settings.from_env()

    assert settings.mode == "mock"
    assert settings.fallback_reason == "Missing API key for openrouter."


def test_real_mode_without_model_falls_back(clean_env):
    clean_env.setenv("AEGISFLOW_MODE", "real")
    clean_env.setenv("AEGISFLOW_PROVIDER", "openrouter")
    clean_env.setenv("AEGISFLOW_ALLOW_EXTERNAL_LLM", "true")
    clean_env.setenv("OPENROUTER_API_KEY", "not-a-real-key")

    settings = Settings.from_env()

    assert settings.mode == "mock"
    assert settings.fallback_reason == "AEGISFLOW_MODEL is empty."


def test_fully_configured_real_mode_stays_real(clean_env):
    clean_env.setenv("AEGISFLOW_MODE", "real")
    clean_env.setenv("AEGISFLOW_PROVIDER", "openrouter")
    clean_env.setenv("AEGISFLOW_ALLOW_EXTERNAL_LLM", "true")
    clean_env.setenv("AEGISFLOW_MODEL", "test-model")
    clean_env.setenv("OPENROUTER_API_KEY", "not-a-real-key")

    settings = Settings.from_env()

    assert settings.mode == "real"
    assert settings.fallback_reason is None
    assert not any("SIMULATED MODE" in warning for warning in settings.warnings)


def test_gemini_key_alias_is_accepted(clean_env):
    clean_env.setenv("AEGISFLOW_MODE", "real")
    clean_env.setenv("AEGISFLOW_ALLOW_EXTERNAL_LLM", "true")
    clean_env.setenv("AEGISFLOW_PROVIDER", "gemini")
    clean_env.setenv("AEGISFLOW_MODEL", "test-model")
    clean_env.setenv("GEMINI_API_KEY", "not-a-real-key")

    settings = Settings.from_env()

    assert settings.mode == "real"
    assert settings.api_key_for("gemini") == "not-a-real-key"


def test_describe_never_exposes_the_key(clean_env):
    secret = "sk-super-secret-value-do-not-print"
    clean_env.setenv("AEGISFLOW_MODE", "real")
    clean_env.setenv("AEGISFLOW_PROVIDER", "openrouter")
    clean_env.setenv("AEGISFLOW_ALLOW_EXTERNAL_LLM", "true")
    clean_env.setenv("AEGISFLOW_MODEL", "test-model")
    clean_env.setenv("OPENROUTER_API_KEY", secret)

    settings = Settings.from_env()
    described = settings.describe()

    assert described["api_key_configured"] is True
    assert secret not in json.dumps(described)


def test_invalid_mode_is_rejected(clean_env):
    clean_env.setenv("AEGISFLOW_MODE", "turbo")

    with pytest.raises(ValueError, match="AEGISFLOW_MODE"):
        Settings.from_env()


def test_invalid_numeric_setting_is_rejected(clean_env):
    clean_env.setenv("AEGISFLOW_MAX_RETRIES", "many")

    with pytest.raises(ValueError, match="AEGISFLOW_MAX_RETRIES"):
        Settings.from_env()
