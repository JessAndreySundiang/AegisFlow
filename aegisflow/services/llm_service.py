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


class LLMAuthenticationError(LLMError):
    """Credentials were rejected; a different model cannot fix this."""


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


# Exception class names that carry a meaning we can trust without importing the
# provider SDKs. Types are checked before message text, because a bare number
# such as "403" also occurs in request ids, model names, and file paths.
_TRANSIENT_TYPES = frozenset(
    {
        "RateLimitError",
        "TooManyRequests",
        "APITimeoutError",
        "APIConnectionError",
        "TimeoutException",
        "TimeoutError",
        "ConnectionError",
        "ConnectError",
        "InternalServerError",
        "ServiceUnavailable",
        "ResourceExhausted",
        "DeadlineExceeded",
    }
)
_AUTH_TYPES = frozenset(
    {
        "AuthenticationError",
        "PermissionDeniedError",
        "PermissionDenied",
        "Unauthenticated",
        "InvalidAPIKeyError",
    }
)

# Status codes count only as whole tokens, so "req_40391" or "model-v403" is not
# mistaken for an HTTP 403.
_TRANSIENT_CODES = re.compile(r"\b(429|502|503)\b")
_AUTH_CODES = re.compile(r"\b(401|403)\b")
_TRANSIENT_TOKENS = ("timeout", "timed out", "rate limit")
_AUTH_TOKENS = (
    "unauthorized",
    "invalid api key",
    "invalid_api_key",
    "permission denied",
)


def _type_names(exc: BaseException) -> set[str]:
    return {cls.__name__ for cls in type(exc).__mro__}


def _is_transient(exc: BaseException) -> bool:
    """Classify a provider failure as retryable.

    The exception type is authoritative; message text is only consulted when the
    type says nothing, so an unrelated number in the text cannot reclassify it.
    """
    names = _type_names(exc)
    if names & _TRANSIENT_TYPES:
        return True
    if names & _AUTH_TYPES:
        return False
    message = str(exc).lower()
    return bool(_TRANSIENT_CODES.search(message)) or any(
        token in message for token in _TRANSIENT_TOKENS
    )


def _is_auth_failure(exc: BaseException) -> bool:
    """Authentication failures are not fixed by trying a different model."""
    names = _type_names(exc)
    if names & _AUTH_TYPES:
        return True
    if names & _TRANSIENT_TYPES:
        return False
    message = str(exc).lower()
    return bool(_AUTH_CODES.search(message)) or any(
        token in message for token in _AUTH_TOKENS
    )


def _usage_from_message(message: Any) -> dict[str, int] | None:
    """Extract reported token usage, or ``None`` when the provider sent none.

    Usage is never estimated: a missing report stays missing rather than being
    replaced with a guess.
    """
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None
    result = {
        key: usage[key]
        for key in ("input_tokens", "output_tokens", "total_tokens")
        if isinstance(usage.get(key), int)
    }
    return result or None


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
        # Mock mode reports no token usage; the attribute exists for parity.
        self.last_usage: dict[str, int] | None = None
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
        self.last_usage = None
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
        # Structured-output support is probed once per candidate and schema.
        self._structured_models: dict[tuple[str, str, type[BaseModel]], Any | None] = {}
        self._clients: dict[tuple[str, str], Any] = {}
        self.last_usage: dict[str, int] | None = None
        self.last_attempts: list[dict[str, Any]] = []
        self.active_provider = ""
        self.active_model = ""
        # ``model`` stays assignable so a caller (or a test) can inject a client.
        self.model: Any | None = None

        if not settings.allow_external_llm:
            raise LLMConfigurationError(
                "External LLM use is not authorized. Set AEGISFLOW_ALLOW_EXTERNAL_LLM=true."
            )
        if not settings.model:
            raise LLMConfigurationError("AEGISFLOW_MODEL is empty.")
        candidates = settings.model_candidates() or (
            (settings.provider, settings.model),
        )
        if not any(settings.api_key_for(provider) for provider, _ in candidates):
            raise LLMConfigurationError(
                f"No API key configured for provider {settings.provider}."
            )

    def _candidates(self) -> tuple[tuple[str, str], ...]:
        return self.settings.model_candidates() or (
            (self.settings.provider, self.settings.model),
        )

    def _client_for(self, provider: str, model_id: str) -> Any:
        """Build (and cache) one client per provider/model candidate."""
        cache = getattr(self, "_clients", None)
        if cache is None:
            cache = {}
            self._clients = cache
        key = (provider, model_id)
        if key in cache:
            return cache[key]
        api_key = self.settings.api_key_for(provider)
        if not api_key:
            raise LLMConfigurationError(
                f"No API key configured for provider {provider}."
            )
        if provider == "openrouter":
            from langchain_openai import ChatOpenAI

            client = ChatOpenAI(
                model=model_id,
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=0,
                timeout=self.settings.llm_timeout_s,
                max_retries=0,
                default_headers={
                    "HTTP-Referer": "http://localhost:8501",
                    "X-Title": "AegisFlow",
                },
            )
        elif provider == "openai":
            from langchain_openai import ChatOpenAI

            client = ChatOpenAI(
                model=model_id,
                api_key=api_key,
                temperature=0,
                timeout=self.settings.llm_timeout_s,
                max_retries=0,
            )
        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            client = ChatGoogleGenerativeAI(
                model=model_id,
                api_key=api_key,
                temperature=0,
                timeout=self.settings.llm_timeout_s,
                max_retries=0,
            )
        else:  # pragma: no cover - config validation prevents this
            raise LLMConfigurationError(f"Unsupported provider: {provider}")
        cache[key] = client
        return client

    def structured(
        self,
        agent: str,
        schema: type[T],
        system_prompt: str,
        user_payload: dict[str, Any],
        mock_builder: Callable[[], Any] | None = None,
    ) -> T:
        """Call the first model candidate that answers.

        Candidates come from ``AEGISFLOW_MODEL`` in order. A missing model, a
        provider outage, or a rate limit moves on to the next entry; an
        authentication failure stops immediately because another model cannot
        fix a bad key. Malformed model output is deliberately not failed over: it
        stays a ``MalformedOutputError`` so agent-level retry and audit semantics
        do not silently change depending on how many models are configured.
        """
        self.last_usage = None
        self.last_attempts = []
        last_error: Exception | None = None
        for index, (provider, model_id) in enumerate(self._candidates()):
            self.active_provider = provider
            self.active_model = model_id
            try:
                client = (
                    self.model
                    if (index == 0 and self.model is not None)
                    else self._client_for(provider, model_id)
                )
                return self._call_candidate(
                    client, agent, schema, system_prompt, user_payload
                )
            except MalformedOutputError:
                raise
            except LLMAuthenticationError:
                raise
            except LLMError as exc:
                if _is_auth_failure(exc):
                    raise
                self.last_attempts.append(
                    {
                        "provider": provider,
                        "model": model_id,
                        "error": type(exc).__name__,
                        "transient": isinstance(exc, TransientProviderError),
                    }
                )
                last_error = exc
                continue
        raise last_error or LLMError("All model candidates failed.")

    def _call_candidate(
        self,
        client: Any,
        agent: str,
        schema: type[T],
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> T:
        """Run the bounded retry loop against one candidate."""
        runner = self._structured_runner(client, schema)
        system = f"AGENT_NAME: {agent}\n{system_prompt}"
        if runner is None:
            schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False)
            system = f"{system}\n\nRequested JSON schema:\n{schema_text}\n\n{JSON_ONLY}"
        messages = [
            SystemMessage(content=system),
            HumanMessage(
                content=json.dumps(user_payload, ensure_ascii=False, default=str)
            ),
        ]
        last_error: Exception | None = None
        # One budget for the whole candidate, not per attempt: a provider that
        # ignores its own timeout would otherwise be retried max_retries times,
        # turning a 60 s stall into three minutes before failover begins.
        deadline = time.monotonic() + self.settings.llm_timeout_s
        for attempt in range(self.settings.max_retries + 1):
            try:
                if runner is not None:
                    return self._invoke_structured(runner, messages, schema)
                return self._invoke_text(client, messages, schema)
            except MalformedOutputError:
                raise
            except Exception as exc:
                if _is_transient(exc):
                    last_error = exc
                    backoff = 0.5 * (2**attempt)
                    if (
                        attempt < self.settings.max_retries
                        and time.monotonic() + backoff < deadline
                    ):
                        time.sleep(backoff)
                        continue
                    raise TransientProviderError(str(exc)) from exc
                if _is_auth_failure(exc):
                    raise LLMAuthenticationError(
                        f"Provider rejected the credentials: {type(exc).__name__}"
                    ) from exc
                raise LLMError(f"Provider call failed: {type(exc).__name__}") from exc
        raise last_error or LLMError("Provider call failed.")

    def _structured_runner(self, client: Any, schema: type[T]) -> Any | None:
        """Return a structured-output runnable, or ``None`` when unsupported.

        Cached per candidate and schema. Chat models that implement only
        ``_generate`` inherit a ``bind_tools`` that raises ``NotImplementedError``;
        those are remembered as unsupported so the caller can use the text path
        without probing on every retry.
        """
        cache = getattr(self, "_structured_models", None)
        if cache is None:
            cache = {}
            self._structured_models = cache
        key = (
            getattr(self, "active_provider", ""),
            getattr(self, "active_model", ""),
            schema,
        )
        if key in cache:
            return cache[key]
        runner: Any | None
        try:
            runner = client.with_structured_output(schema, include_raw=True)
        except Exception:
            # Unsupported binding (or an integration that cannot express the
            # schema) must degrade to the text path rather than fail the call.
            runner = None
        cache[key] = runner
        return runner

    def _invoke_structured(
        self, runner: Any, messages: list[BaseMessage], schema: type[T]
    ) -> T:
        """Validate one native structured-output response.

        ``include_raw=True`` makes parse failures non-raising: the payload
        carries ``parsed`` and ``parsing_error`` instead. Both are checked here
        so malformed output stays a ``MalformedOutputError`` and is therefore
        not silently retried or accepted as empty.
        """
        payload = runner.invoke(messages)
        if isinstance(payload, schema):
            return payload
        if not isinstance(payload, dict):
            raise MalformedOutputError(
                f"Structured output for {schema.__name__} was not a mapping."
            )
        # Usage is recorded even when the output fails validation: the tokens
        # were spent either way.
        self.last_usage = _usage_from_message(payload.get("raw"))
        parsing_error = payload.get("parsing_error")
        if parsing_error is not None:
            raise MalformedOutputError(
                f"Response did not validate as {schema.__name__}: "
                f"{type(parsing_error).__name__}"
            )
        parsed = payload.get("parsed")
        if parsed is None:
            raise MalformedOutputError(
                f"Response did not validate as {schema.__name__}: no parsed output."
            )
        if isinstance(parsed, schema):
            return parsed
        try:
            return schema.model_validate(parsed)
        except Exception as exc:
            raise MalformedOutputError(
                f"Response did not validate as {schema.__name__}: "
                f"{type(exc).__name__}"
            ) from exc

    def _invoke_text(
        self, client: Any, messages: list[BaseMessage], schema: type[T]
    ) -> T:
        response = client.invoke(messages)
        self.last_usage = _usage_from_message(response)
        return parse_structured(_message_text(response), schema)


def build_llm_service(settings: Settings) -> MockLLMService | RealLLMService:
    if settings.mode == "mock":
        return MockLLMService(settings)
    return RealLLMService(settings)
