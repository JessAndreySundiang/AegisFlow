"""Shared agent execution helpers."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from config import Settings
from ..database import Database
from ..models import AgentStatus, ErrorClass, utcnow_iso
from ..services.llm_service import (
    LLMError,
    MalformedOutputError,
    TransientProviderError,
)
from ..validation import ValidationError

T = TypeVar("T", bound=BaseModel)


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
    """Invoke the model with bounded retries and record one execution row."""
    started = utcnow_iso()
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
            )
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
    )
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
