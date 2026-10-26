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
