"""Typed graph state.

The parent graph uses append-only reducers for audit-like fields. Team subgraphs
use a plain ``TeamState`` (no reducers) and are invoked through wrapper nodes
that return only new items. This avoids the classic LangGraph subgraph problem
where inherited append-only state is appended twice.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from .models import utcnow_iso


def append_list(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    return list(left or []) + list(right or [])


def merge_dict(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class AegisState(TypedDict, total=False):
    # identity
    task_id: str
    request: str
    output_format: str
    manual_minutes: float | None
    simulated: bool

    # inputs
    files: list[dict[str, Any]]
    documents: dict[str, dict[str, Any]]

    # planning
    plan: dict[str, Any] | None
    subtask_status: Annotated[dict[str, str], merge_dict]
    team_status: Annotated[dict[str, str], merge_dict]
    phase: str
    next_action: str
    last_team_result: dict[str, Any]

    # analysis
    claims: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    analysis_summary: str

    # output
    draft: str
    draft_version: int
    current_version_id: str | None
    current_content_hash: str | None

    # assurance
    policy_report: dict[str, Any] | None
    review_result: dict[str, Any] | None

    # human approval
    human_decision: dict[str, Any] | None
    approval_id: str | None

    # control
    revision_count: int
    max_revisions: int
    revision_feedback: str
    revision_target: str
    retry_counts: Annotated[dict[str, int], merge_dict]
    status: str
    escalation_reason: str
    blocked_reason: str
    error: str

    # append-only
    agent_results: Annotated[list[dict[str, Any]], append_list]
    errors: Annotated[list[dict[str, Any]], append_list]
    routing_log: Annotated[list[dict[str, Any]], append_list]
    audit_events: Annotated[list[dict[str, Any]], append_list]

    started_at: str
    updated_at: str


class TeamState(TypedDict, total=False):
    """Plain state used inside a team subgraph (no reducers)."""

    task_id: str
    request: str
    output_format: str
    files: list[dict[str, Any]]
    documents: dict[str, dict[str, Any]]
    plan: dict[str, Any] | None
    subtask_status: dict[str, str]
    team_status: dict[str, str]
    phase: str
    next_action: str
    last_team_result: dict[str, Any]
    claims: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    analysis_summary: str
    draft: str
    draft_version: int
    current_version_id: str | None
    current_content_hash: str | None
    policy_report: dict[str, Any] | None
    review_result: dict[str, Any] | None
    revision_count: int
    max_revisions: int
    revision_feedback: str
    revision_target: str
    retry_counts: dict[str, int]
    status: str
    escalation_reason: str
    blocked_reason: str
    error: str
    simulated: bool
    lead_iterations: int
    agent_results: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    routing_log: list[dict[str, Any]]


def initial_state(
    task_id: str,
    request: str,
    output_format: str,
    files: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    simulated: bool,
    max_revisions: int = 2,
    manual_minutes: float | None = None,
) -> AegisState:
    now = utcnow_iso()
    return AegisState(
        task_id=task_id,
        request=request,
        output_format=output_format,
        manual_minutes=manual_minutes,
        simulated=simulated,
        files=files,
        documents=documents,
        plan=None,
        subtask_status={},
        team_status={},
        phase="start",
        next_action="",
        last_team_result={},
        claims=[],
        evidence=[],
        analysis_summary="",
        draft="",
        draft_version=0,
        current_version_id=None,
        current_content_hash=None,
        policy_report=None,
        review_result=None,
        human_decision=None,
        approval_id=None,
        revision_count=0,
        max_revisions=max_revisions,
        revision_feedback="",
        revision_target="",
        retry_counts={},
        status="pending",
        escalation_reason="",
        blocked_reason="",
        error="",
        agent_results=[],
        errors=[],
        routing_log=[],
        audit_events=[],
        started_at=now,
        updated_at=now,
    )
