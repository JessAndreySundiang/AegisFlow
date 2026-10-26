"""Single LLM access layer for mock and real providers.

Mock mode uses a real LangChain ``BaseChatModel`` subclass (``ScriptedChatModel``)
so the same invoke/parse/validate path is exercised without network access.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel

from config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMConfigurationError(LLMError):
    pass


class TransientProviderError(LLMError):
    """Timeout, rate limit, or a provider-side temporary failure."""


class MalformedOutputError(LLMError):
    """The provider returned text that did not match the requested schema."""


JSON_ONLY = (
    "Return only one JSON object that validates against the requested schema. "
    "Do not wrap it in Markdown fences and do not add commentary."
)


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return str(content)


def parse_structured(text: str, schema: type[T]) -> T:
    if not text or not text.strip():
        raise MalformedOutputError("Provider returned an empty response.")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    # Extract the outermost JSON object if the model added prose.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        return schema.model_validate_json(cleaned)
    except Exception as first_error:
        try:
            return schema.model_validate(json.loads(cleaned))
        except Exception:
            raise MalformedOutputError(
                f"Response did not validate as {schema.__name__}: "
                f"{type(first_error).__name__}"
            ) from first_error


class ScriptedChatModel(BaseChatModel):
    """A deterministic LangChain chat model used in mock mode.

    ``script`` is a callable that receives the agent name and messages and
    returns a JSON string. It may raise ``TransientProviderError`` to simulate a
    provider failure or return malformed text to simulate a semantic failure.
    """

    script: Any = None
    agent_name: str = ""

    @property
    def _llm_type(self) -> str:
        return "aegisflow-scripted"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.script is None:
            raise LLMConfigurationError("ScriptedChatModel has no script configured.")
        content = self.script(self.agent_name, messages)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))]
        )


class MockLLMService:
    simulated = True

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = ScriptedChatModel(script=self._script)
        # Tests can inject failures, e.g. {"report_writer": ["malformed", "transient"]}
        self.scripted_failures: dict[str, list[str]] = {}
        self.calls: list[str] = []

    def _script(self, agent: str, messages: list[BaseMessage]) -> str:
        failures = self.scripted_failures.get(agent) or []
        if failures:
            mode = failures.pop(0)
            if mode == "transient":
                raise TransientProviderError("Simulated provider timeout.")
            if mode == "malformed":
                return "{ this is not valid json"
            if mode == "empty":
                return ""
            if mode == "exception":
                raise RuntimeError("Simulated provider exception.")
        context = getattr(self.model, "_aegis_context", {})
        builder: Callable[[], Any] | None = context.get("builder")
        if builder is None:
            raise LLMConfigurationError(
                f"Mock mode has no deterministic builder for agent {agent}."
            )
        payload = builder()
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        return json.dumps(payload, ensure_ascii=False, default=str)

    def structured(
        self,
        agent: str,
        schema: type[T],
        system_prompt: str,
        user_payload: dict[str, Any],
        mock_builder: Callable[[], Any],
    ) -> T:
        self.calls.append(agent)
        self.model.agent_name = agent
        # A private attribute avoids putting mutable context into Pydantic fields.
        object.__setattr__(self.model, "_aegis_context", {"builder": mock_builder})
        messages = [
            SystemMessage(content=f"AGENT_NAME: {agent}\n{system_prompt}"),
            HumanMessage(
                content=json.dumps(user_payload, ensure_ascii=False, default=str)
            ),
        ]
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self.model.invoke(messages)
                return parse_structured(_message_text(response), schema)
            except TransientProviderError as exc:
                last_error = exc
                if attempt < self.settings.max_retries:
                    time.sleep(0.01 * (attempt + 1))
                    continue
                raise
            except MalformedOutputError:
                raise
        raise last_error or LLMError("Mock provider failed without an error.")


class RealLLMService:
    simulated = False

    def __init__(self, settings: Settings):
        self.settings = settings
        key = settings.api_key_for()
        if not settings.allow_external_llm:
            raise LLMConfigurationError(
                "External LLM use is not authorized. Set AEGISFLOW_ALLOW_EXTERNAL_LLM=true."
            )
        if not key:
            raise LLMConfigurationError(
                f"No API key configured for provider {settings.provider}."
            )
        if not settings.model:
            raise LLMConfigurationError("AEGISFLOW_MODEL is empty.")

        if settings.provider == "openrouter":
            from langchain_openai import ChatOpenAI

            self.model = ChatOpenAI(
                model=settings.model,
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                temperature=0,
                timeout=60,
                max_retries=0,
                default_headers={
                    "HTTP-Referer": "http://localhost:8501",
                    "X-Title": "AegisFlow",
                },
            )
        elif settings.provider == "openai":
            from langchain_openai import ChatOpenAI

            self.model = ChatOpenAI(
                model=settings.model,
                api_key=key,
                temperature=0,
                timeout=60,
                max_retries=0,
            )
        elif settings.provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            self.model = ChatGoogleGenerativeAI(
                model=settings.model,
                api_key=key,
                temperature=0,
                timeout=60,
                max_retries=0,
            )
        else:  # pragma: no cover - config validation prevents this
            raise LLMConfigurationError(f"Unsupported provider: {settings.provider}")

    def structured(
        self,
        agent: str,
        schema: type[T],
        system_prompt: str,
        user_payload: dict[str, Any],
        mock_builder: Callable[[], Any] | None = None,
    ) -> T:
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        messages = [
            SystemMessage(
                content=(
                    f"AGENT_NAME: {agent}\n{system_prompt}\n\n"
                    f"Requested JSON schema:\n{schema_text}\n\n{JSON_ONLY}"
                )
            ),
            HumanMessage(
                content=json.dumps(user_payload, ensure_ascii=False, default=str)
            ),
        ]
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self.model.invoke(messages)
                return parse_structured(_message_text(response), schema)
            except Exception as exc:
                message = str(exc).lower()
                transient = any(
                    token in message
                    for token in ("timeout", "timed out", "rate limit", "429", "503", "502")
                )
                if transient and attempt < self.settings.max_retries:
                    last_error = exc
                    time.sleep(0.5 * (2**attempt))
                    continue
                if transient:
                    raise TransientProviderError(str(exc)) from exc
                if isinstance(exc, MalformedOutputError):
                    raise
                raise LLMError(f"Provider call failed: {type(exc).__name__}") from exc
        raise last_error or LLMError("Provider call failed.")


def build_llm_service(settings: Settings) -> MockLLMService | RealLLMService:
    if settings.mode == "mock":
        return MockLLMService(settings)
    return RealLLMService(settings)
