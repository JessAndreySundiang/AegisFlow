"""Ordered model candidates: failover, error classification, provenance."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel

from aegisflow.agents.base import _model_fields
from aegisflow.services import llm_service
from aegisflow.services.llm_service import (
    LLMError,
    MalformedOutputError,
    RealLLMService,
    TransientProviderError,
)
from config import Settings


class Answer(BaseModel):
    text: str


class _Client:
    """A chat client that returns fixed text or raises a fixed error."""

    def __init__(
        self, *, content: str = '{"text": "ok"}', error: Exception | None = None
    ):
        self.content = content
        self.error = error
        self.calls = 0

    def invoke(self, messages, config=None, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return AIMessage(content=self.content)


def _settings(items: str, **overrides) -> Settings:
    values: dict[str, Any] = {
        "mode": "real",
        "provider": "openrouter",
        "model": items,
        "openrouter_api_key": "sk-test",
        "google_api_key": "gm-test",
        "allow_external_llm": True,
        "max_retries": 1,
    }
    values.update(overrides)
    return Settings(**values).validate()


def _service(
    items: str, clients: dict[tuple[str, str], Any], **overrides
) -> RealLLMService:
    service = RealLLMService(_settings(items, **overrides))
    service._clients.update(clients)
    return service


def test_model_candidates_parse_provider_prefixes():
    settings = _settings(
        "gemini:gemini-3.8-flash, nvidia/x:free ,openrouter/nvidia/y:free,"
        " ,openai:gpt-test"
    )

    assert settings.model_candidates() == (
        ("gemini", "gemini-3.8-flash"),
        ("openrouter", "nvidia/x:free"),
        ("openrouter", "nvidia/y:free"),
        ("openai", "gpt-test"),
    )


def test_explicit_prefix_routes_an_ambiguous_id_to_the_named_provider():
    settings = Settings(
        provider="gemini",
        model="gemini:gemini-3.8-flash,openrouter:openai/gpt-4o",
    )

    assert settings.model_candidates() == (
        ("gemini", "gemini-3.8-flash"),
        ("openrouter", "openai/gpt-4o"),
    )


def test_cross_provider_slash_is_rejected_instead_of_guessed():
    """B4: 'openai/gpt-4o' must not silently mean the native OpenAI provider."""
    settings = Settings(
        mode="real",
        provider="gemini",
        model="openai/gpt-4o",
        google_api_key="gm-test",
        openai_api_key="oa-test",
        allow_external_llm=True,
    )

    with pytest.raises(ValueError) as excinfo:
        settings.model_candidates()

    message = str(excinfo.value)
    assert "ambiguous" in message
    # Both readings are spelled out, so the fix needs no documentation lookup.
    assert "openai:gpt-4o" in message
    assert "gemini:openai/gpt-4o" in message


def test_missing_model_fails_over_to_the_next_candidate():
    missing = _Client(error=RuntimeError("404 model not found"))
    working = _Client(content='{"text": "from-second"}')
    service = _service(
        "nvidia/gone:free,openrouter/recursive/flint-v1.0:free",
        {
            ("openrouter", "nvidia/gone:free"): missing,
            ("openrouter", "recursive/flint-v1.0:free"): working,
        },
    )

    result = service.structured("planner", Answer, "system", {"task": "x"})

    assert result.text == "from-second"
    assert service.active_model == "recursive/flint-v1.0:free"
    assert len(service.last_attempts) == 1
    assert service.last_attempts[0]["error"] == "LLMError"


def test_rate_limited_candidate_fails_over_after_retries(monkeypatch):
    monkeypatch.setattr(llm_service.time, "sleep", lambda _seconds: None)
    limited = _Client(error=RuntimeError("429 rate limit exceeded"))
    working = _Client(content='{"text": "second"}')
    service = _service(
        "openrouter/a,openrouter/b",
        {("openrouter", "a"): limited, ("openrouter", "b"): working},
    )

    result = service.structured("planner", Answer, "system", {})

    assert result.text == "second"
    assert limited.calls == 2
    assert service.last_attempts[0]["transient"] is True


def test_authentication_failure_aborts_without_trying_next_candidate():
    unauthorized = _Client(error=RuntimeError("401 Unauthorized: invalid api key"))
    working = _Client(content='{"text": "unused"}')
    service = _service(
        "openrouter/a,openrouter/b",
        {("openrouter", "a"): unauthorized, ("openrouter", "b"): working},
    )

    with pytest.raises(LLMError):
        service.structured("planner", Answer, "system", {})

    assert working.calls == 0


def test_malformed_output_is_not_masked_by_failover():
    broken = _Client(content="this is not json")
    working = _Client(content='{"text": "second"}')
    service = _service(
        "openrouter/a,openrouter/b",
        {("openrouter", "a"): broken, ("openrouter", "b"): working},
    )

    with pytest.raises(MalformedOutputError):
        service.structured("planner", Answer, "system", {})

    assert working.calls == 0


def test_candidate_without_a_key_is_skipped():
    working = _Client(content='{"text": "second"}')
    service = _service(
        "gemini:x,openrouter:b",
        {("openrouter", "b"): working},
        google_api_key="",
    )

    result = service.structured("planner", Answer, "system", {})

    assert result.text == "second"
    assert len(service.last_attempts) == 1


def test_all_candidates_failing_reports_the_last_error():
    first = _Client(error=RuntimeError("404 model not found"))
    second = _Client(error=RuntimeError("404 also missing"))
    service = _service(
        "openrouter/a,openrouter/b",
        {("openrouter", "a"): first, ("openrouter", "b"): second},
    )

    with pytest.raises(LLMError):
        service.structured("planner", Answer, "system", {})

    assert len(service.last_attempts) == 2
    assert first.calls == 1
    assert second.calls == 1


def test_single_candidate_keeps_transient_classification(monkeypatch):
    monkeypatch.setattr(llm_service.time, "sleep", lambda _seconds: None)
    slow = _Client(error=RuntimeError("request timed out"))
    service = _service("openrouter/a", {("openrouter", "a"): slow})

    with pytest.raises(TransientProviderError):
        service.structured("planner", Answer, "system", {})

    assert slow.calls == 2


def test_model_fields_prefers_the_serving_candidate():
    service = _service("openrouter/a,openrouter/b", {})
    service.active_provider = "openrouter"
    service.active_model = "b"

    assert _model_fields(service.settings, service) == {
        "model_backend": "openrouter",
        "model_id": "b",
    }


def test_model_fields_falls_back_to_mock_without_an_active_candidate():
    settings = Settings(mode="mock").validate()

    assert _model_fields(settings, None) == {"model_backend": "mock", "model_id": ""}


def test_classification_prefers_the_exception_type_over_message_text():
    class RateLimitError(RuntimeError):
        pass

    class AuthenticationError(RuntimeError):
        pass

    assert llm_service._is_transient(RateLimitError("upstream refused"))
    assert not llm_service._is_auth_failure(RateLimitError("upstream refused"))
    assert llm_service._is_auth_failure(AuthenticationError("no"))
    assert not llm_service._is_transient(AuthenticationError("no"))


def test_numeric_codes_are_matched_only_as_whole_tokens():
    # A request id or model name must not read as an HTTP status code.
    assert not llm_service._is_auth_failure(RuntimeError("request req_40391 failed"))
    assert not llm_service._is_transient(RuntimeError("model-v4290 not found"))
    assert llm_service._is_auth_failure(RuntimeError("HTTP 403 Forbidden"))
    assert llm_service._is_transient(RuntimeError("503 Service Unavailable"))


def test_message_fallback_still_catches_unnamed_sdk_errors():
    assert llm_service._is_transient(RuntimeError("Rate limit exceeded, retry later"))
    assert llm_service._is_auth_failure(RuntimeError("Unauthorized"))
