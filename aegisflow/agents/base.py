"""Shared agent execution helpers."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from config import Settings

from ..database import Database
from ..models import AgentStatus, ErrorClass, utcnow_iso
from ..prompts import prompt_fingerprint
from ..services.llm_service import (
    LLMError,
    MalformedOutputError,
    TransientProviderError,
)
from ..validation import ValidationError

T = TypeVar("T", bound=BaseModel)


def _model_fields(settings: Settings, llm: Any = None) -> dict[str, str]:
    """Identify the model that actually served the call, without exposing secrets.

    Real mode prefers the candidate that answered, so a failover run records the
    winner rather than whatever was configured first.
    """
    provider = getattr(llm, "active_provider", "") or ""
    model_id = getattr(llm, "active_model", "") or ""
    if provider:
        return {"model_backend": provider, "model_id": model_id}
    if settings.simulated:
        return {"model_backend": "mock", "model_id": ""}
    return {"model_backend": settings.provider, "model_id": settings.model}


def _usage_fields(llm: Any) -> dict[str, int | None]:
    """Token counts the provider actually reported; never estimated."""
    usage = getattr(llm, "last_usage", None)
    if not isinstance(usage, dict):
        return {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


def _record_provider_audit(
    db: Database, task_id: str, llm: Any, *, served: bool
) -> None:
    """Record every candidate that was tried and did not answer.

    ``last_attempts`` holds one entry per unusable candidate, in order. Recording
    only the first understated the trail: three skipped candidates looked like
    one, and a call where nothing answered recorded nothing at all.
    """
    attempts = getattr(llm, "last_attempts", None) or []
    if not attempts:
        return
    tried = "; ".join(
        f"{attempt.get('provider')}/{attempt.get('model')} ({attempt.get('error')})"
        for attempt in attempts
    )
    if served:
        event_type = "provider_fallback"
        outcome = (
            f"served_by={getattr(llm, 'active_provider', '')}/"
            f"{getattr(llm, 'active_model', '')}"
        )
    else:
        event_type = "provider_candidates_exhausted"
        outcome = "no candidate answered"
    db.add_audit(task_id, event_type, "system", None, f"tried={tried}; {outcome}")


class AgentFailure(RuntimeError):
    def __init__(self, message: str, error_class: str, retries: int):
        super().__init__(message)
        self.error_class = error_class
        self.retries = retries


def call_agent(
    *,
    agent: str,
    schema: type[T],
    system_prompt: str,
    payload: dict[str, Any],
    mock_builder: Callable[[], Any],
    settings: Settings,
    llm: Any,
    db: Database,
    task_id: str,
    level: int,
    skill: str,
    input_ref: str,
    validator: Callable[[T], None] | None = None,
) -> tuple[T, int]:
    """Invoke the model with bounded retries and record one execution row.

    ``latency_ms`` is the wall clock of the whole call: every attempt plus any
    backoff between them, measured the same way whether the call succeeded or
    failed. It deliberately excludes nothing, so averaging the column across
    rows does not mix per-attempt and per-call durations.

    Token usage is recorded when the provider reports it and left NULL
    otherwise, so an absent metric is never indistinguishable from a measured
    zero.
    """
    started = utcnow_iso()
    started_clock = time.perf_counter()
    retries = 0
    last_error: BaseException | None = None
    for attempt in range(settings.max_retries + 1):
        try:
            result = llm.structured(
                agent=agent,
                schema=schema,
                system_prompt=system_prompt,
                user_payload=payload,
                mock_builder=mock_builder,
            )
            if validator is not None:
                validator(result)
            db.add_agent_execution(
                task_id=task_id,
                agent=agent,
                level=level,
                skill=skill,
                status=AgentStatus.COMPLETED.value,
                retries=retries,
                simulated=settings.simulated,
                input_ref=input_ref,
                output_ref=f"{schema.__name__} ok",
                started_at=started,
                finished_at=utcnow_iso(),
                latency_ms=int((time.perf_counter() - started_clock) * 1000),
                prompt_version=prompt_fingerprint(system_prompt),
                **_model_fields(settings, llm),
                **_usage_fields(llm),
            )
            _record_provider_audit(db, task_id, llm, served=True)
            return result, retries
        except (MalformedOutputError, ValidationError) as exc:
            last_error = exc
            retries = attempt + 1
            if attempt < settings.max_retries:
                continue
            error_class = ErrorClass.MALFORMED_OUTPUT.value
            break
        except TransientProviderError as exc:
            last_error = exc
            retries = attempt + 1
            if attempt < settings.max_retries:
                continue
            error_class = ErrorClass.TRANSIENT.value
            break
        except LLMError as exc:
            last_error = exc
            retries = attempt + 1
            error_class = ErrorClass.CONFIGURATION.value
            break
        except Exception as exc:  # defensive: classify unknown failures
            last_error = exc
            retries = attempt + 1
            error_class = ErrorClass.UNKNOWN.value
            break

    db.add_agent_execution(
        task_id=task_id,
        agent=agent,
        level=level,
        skill=skill,
        status=AgentStatus.FAILED.value,
        retries=retries,
        error_class=error_class,
        simulated=settings.simulated,
        input_ref=input_ref,
        output_ref="failed",
        started_at=started,
        finished_at=utcnow_iso(),
        latency_ms=int((time.perf_counter() - started_clock) * 1000),
        prompt_version=prompt_fingerprint(system_prompt),
        **_model_fields(settings, llm),
        **_usage_fields(llm),
    )
    _record_provider_audit(db, task_id, llm, served=False)
    raise AgentFailure(
        f"{agent} failed after {retries} retry(ies): {type(last_error).__name__}",
        error_class=error_class,
        retries=retries,
    )


def failure_result(
    *,
    agent: str,
    level: int,
    skill: str,
    failure: AgentFailure,
    simulated: bool,
) -> dict[str, Any]:
    return {
        "agent": agent,
        "level": level,
        "skill": skill,
        "status": AgentStatus.FAILED.value,
        "summary": "",
        "output": {},
        "claims": [],
        "evidence": [],
        "missing_information": [],
        "uncertainty": [str(failure)],
        "error_class": failure.error_class,
        "retries": failure.retries,
        "simulated": simulated,
        "started_at": utcnow_iso(),
        "finished_at": utcnow_iso(),
    }
