"""Contract tests for the real-provider path using fake chat models (no network)."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel

from aegisflow.services import llm_service
from aegisflow.services.llm_service import (
    LLMConfigurationError,
    LLMError,
    MalformedOutputError,
    RealLLMService,
    TransientProviderError,
)
from config import Settings


class Answer(BaseModel):
    text: str


class _ReplyModel(BaseChatModel):
    content: str = ""

    @property
    def _llm_type(self) -> str:
        return "reply"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.content))]
        )


class _BoomModel(BaseChatModel):
    message: str = ""

    @property
    def _llm_type(self) -> str:
        return "boom"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise RuntimeError(self.message)


class _StructuredModel(_ReplyModel):
    """A chat model that advertises native structured output."""

    parsed: Any = None
    parsing_error: Any = None
    usage: dict[str, int] | None = None
    raises: Any = None
    invocations: int = 0

    def with_structured_output(self, schema, **kwargs):
        model = self

        class _Runner:
            def invoke(self, messages, config=None, **kwargs):
                model.invocations += 1
                if model.raises is not None:
                    raise model.raises
                return {
                    "raw": AIMessage(content="", usage_metadata=model.usage),
                    "parsed": model.parsed,
                    "parsing_error": model.parsing_error,
                }

        return _Runner()


def _settings(**overrides) -> Settings:
    values: dict[str, Any] = {
        "mode": "real",
        "provider": "openrouter",
        "model": "test-model",
        "openrouter_api_key": "test-key",
        "allow_external_llm": True,
        "max_retries": 1,
    }
    values.update(overrides)
    return Settings(**values).validate()


def _service(max_retries: int = 1) -> RealLLMService:
    service = object.__new__(RealLLMService)
    service.settings = _settings(max_retries=max_retries)
    return service


def test_valid_json_is_parsed():
    service = _service()
    service.model = _ReplyModel(content='{"text": "ok"}')

    result = service.structured("planner", Answer, "system", {"task": "x"})

    assert result.text == "ok"


def test_markdown_fenced_json_is_accepted():
    service = _service()
    service.model = _ReplyModel(content='```json\n{"text": "fenced"}\n```')

    result = service.structured("planner", Answer, "system", {"task": "x"})

    assert result.text == "fenced"


def test_malformed_json_is_not_retried():
    service = _service()
    service.model = _ReplyModel(content="this is not json")

    with pytest.raises(MalformedOutputError):
        service.structured("planner", Answer, "system", {"task": "x"})


def test_timeout_becomes_transient_after_retries(monkeypatch):
    monkeypatch.setattr(llm_service.time, "sleep", lambda _seconds: None)
    service = _service(max_retries=1)
    service.model = _BoomModel(message="request timed out")

    with pytest.raises(TransientProviderError):
        service.structured("planner", Answer, "system", {"task": "x"})


def test_rate_limit_becomes_transient(monkeypatch):
    monkeypatch.setattr(llm_service.time, "sleep", lambda _seconds: None)
    service = _service(max_retries=1)
    service.model = _BoomModel(message="429 rate limit exceeded")

    with pytest.raises(TransientProviderError):
        service.structured("planner", Answer, "system", {"task": "x"})


def test_unauthorized_is_not_transient():
    service = _service()
    service.model = _BoomModel(message="401 Unauthorized: invalid api key")

    with pytest.raises(LLMError) as excinfo:
        service.structured("planner", Answer, "system", {"task": "x"})

    assert not isinstance(excinfo.value, TransientProviderError)


def test_construction_requires_authorization():
    with pytest.raises(LLMConfigurationError):
        RealLLMService(_settings(allow_external_llm=False))


def test_construction_requires_key():
    with pytest.raises(LLMConfigurationError):
        RealLLMService(_settings(openrouter_api_key=""))


def test_structured_output_is_preferred_when_supported():
    service = _service()
    service.model = _StructuredModel(parsed=Answer(text="native"))

    result = service.structured("planner", Answer, "system", {"task": "x"})

    assert result.text == "native"
    assert service.model.invocations == 1


def test_structured_dict_payload_is_revalidated():
    service = _service()
    service.model = _StructuredModel(parsed={"text": "from-dict"})

    result = service.structured("planner", Answer, "system", {"task": "x"})

    assert result.text == "from-dict"


def test_structured_parsing_error_is_malformed_and_not_retried():
    service = _service(max_retries=2)
    service.model = _StructuredModel(parsing_error=ValueError("schema mismatch"))

    with pytest.raises(MalformedOutputError):
        service.structured("planner", Answer, "system", {"task": "x"})

    assert service.model.invocations == 1


def test_structured_without_parsed_output_is_malformed():
    service = _service()
    service.model = _StructuredModel(parsed=None)

    with pytest.raises(MalformedOutputError):
        service.structured("planner", Answer, "system", {"task": "x"})


def test_structured_transient_error_is_retried_then_transient(monkeypatch):
    monkeypatch.setattr(llm_service.time, "sleep", lambda _seconds: None)
    service = _service(max_retries=1)
    service.model = _StructuredModel(raises=RuntimeError("request timed out"))

    with pytest.raises(TransientProviderError):
        service.structured("planner", Answer, "system", {"task": "x"})

    assert service.model.invocations == 2


def test_structured_usage_is_recorded():
    service = _service()
    service.model = _StructuredModel(
        parsed=Answer(text="ok"),
        usage={"input_tokens": 11, "output_tokens": 4, "total_tokens": 15},
    )

    service.structured("planner", Answer, "system", {"task": "x"})

    assert service.last_usage == {
        "input_tokens": 11,
        "output_tokens": 4,
        "total_tokens": 15,
    }


def test_missing_usage_report_is_not_estimated():
    service = _service()
    service.model = _StructuredModel(parsed=Answer(text="ok"))

    service.structured("planner", Answer, "system", {"task": "x"})

    assert service.last_usage is None


def test_unsupported_model_falls_back_to_text_path():
    service = _service()
    service.model = _ReplyModel(content='{"text": "fallback"}')

    result = service.structured("planner", Answer, "system", {"task": "x"})

    assert result.text == "fallback"
    assert service.last_usage is None
