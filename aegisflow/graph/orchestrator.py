"""Root Orchestrator: deterministic routing over the plan and team results."""

from __future__ import annotations

from typing import Any

from langgraph.types import Command

from config import Settings

from ..database import Database
from ..models import (
    TaskStatus,
    utcnow_iso,
)
from ..validation import ValidationError, validate_routing_choice

WHITELIST = (
    "analysis_team",
    "drafting_team",
    "assurance_team",
    "human_review",
    "blocked",
    "escalate",
)


def _route(
    state: dict[str, Any],
    db: Database,
    goto: str,
    reason: str,
    update: dict[str, Any] | None = None,
) -> Command:
    try:
        choice = validate_routing_choice(goto, WHITELIST + ("__end__",))
    except ValidationError as exc:
        choice = "escalate"
        reason = f"Invalid routing choice: {exc}"
    payload = dict(update or {})
    log = list(payload.get("routing_log") or [])
    log.append(
        {
            "from_node": "orchestrator",
            "to_node": choice,
            "reason": reason,
            "rule": "GR-06",
            "depth": 1,
        }
    )
    payload["routing_log"] = log
    events = list(payload.get("audit_events") or [])
    events.append(
        {
            "event_type": "routing_decision",
            "actor": "system:orchestrator",
            "rule_id": "GR-06",
            "detail": f"to={choice}; reason={reason}",
        }
    )
    payload["audit_events"] = events
    payload["updated_at"] = utcnow_iso()
    db.add_audit(
        state["task_id"],
        "routing_decision",
        "system:orchestrator",
        "GR-06",
        f"to={choice}; reason={reason}",
    )
    return Command(goto=choice, update=payload)


def _set_status(db: Database, task_id: str, status: str) -> None:
    task = db.get_task(task_id)
    if task is None:
        return
    if task.status.value == status:
        return
    try:
        db.transition_task(task_id, status)
    except ValueError:
        # Invalid transitions are surfaced through the escalation path by callers.
        raise


def _team_runs(state: dict[str, Any], team: str) -> int:
    return int((state.get("retry_counts") or {}).get(f"team:{team}", 0))


def orchestrator_node(
    state: dict[str, Any], *, db: Database, settings: Settings
) -> Command:
    task_id = state["task_id"]
    plan = state.get("plan")
    team_status = dict(state.get("team_status") or {})
    status = state.get("status", "in_progress")

    if status == "failed":
        return _route(state, db, "escalate", "Upstream node failed.", {"status": "failed"})
    if status == "blocked":
        return _route(state, db, "blocked", "Upstream node blocked the task.", {"status": "blocked"})
    if not plan:
        return _route(state, db, "blocked", "No validated plan exists.", {"status": "blocked"})
    if plan.get("missing_information"):
        return _route(
            state,
            db,
            "blocked",
            "The plan reports missing information.",
            {"status": "blocked", "blocked_reason": " ".join(plan["missing_information"])},
        )

    subtasks = plan.get("subtasks", [])
    analysis_needed = any(
        s.get("assigned_agent") in {"document_analyst", "evidence_verifier"}
        for s in subtasks
    )
    writer_needed = any(
        s.get("assigned_agent") == "report_writer" for s in subtasks
    )

    # ---------------------------------------------------------------- analysis
    if analysis_needed and team_status.get("analysis") != "completed":
        if _team_runs(state, "analysis") >= 4:
            return _route(
                state,
                db,
                "escalate",
                "Analysis team exceeded its run limit.",
                {"status": "failed", "escalation_reason": "Analysis team run limit exceeded."},
            )
        if team_status.get("analysis") == "blocked":
            return _route(
                state,
                db,
                "blocked",
                "Analysis team reported a blocking input problem.",
                {"status": "blocked"},
            )
        if team_status.get("analysis") == "escalated":
            return _route(
                state,
                db,
                "escalate",
                "Analysis team escalated a worker failure.",
                {"status": "failed", "escalation_reason": state.get("escalation_reason")},
            )
        return _route(
            state,
            db,
            "analysis_team",
            "Plan requires document analysis.",
            {
                "phase": "analysis",
                "retry_counts": {"team:analysis": _team_runs(state, "analysis") + 1},
            },
        )

    # ---------------------------------------------------------------- drafting
    if writer_needed and team_status.get("drafting") != "completed":
        if _team_runs(state, "drafting") >= 4:
            return _route(
                state,
                db,
                "escalate",
                "Drafting team exceeded its run limit.",
                {"status": "failed", "escalation_reason": "Drafting team run limit exceeded."},
            )
        if team_status.get("drafting") == "blocked":
            return _route(
                state,
                db,
                "blocked",
                "Drafting team reported a blocking input problem.",
                {"status": "blocked"},
            )
        if team_status.get("drafting") == "escalated":
            return _route(
                state,
                db,
                "escalate",
                "Drafting team escalated a worker failure.",
                {"status": "failed", "escalation_reason": state.get("escalation_reason")},
            )
        return _route(
            state,
            db,
            "drafting_team",
            "Plan requires a written deliverable.",
            {
                "phase": "drafting",
                "retry_counts": {"team:drafting": _team_runs(state, "drafting") + 1},
            },
        )

    # A summary has no writer; its formatted draft is created by the analysis wrapper.
    if not (state.get("draft") or "").strip():
        version_number = state.get("draft_version")
        blocked_reason = (
            f"No new draft was produced; version {version_number} is unchanged."
            if version_number
            else "No draft was produced."
        )
        return _route(
            state,
            db,
            "blocked",
            "No draft was produced by the selected agents.",
            {"status": "blocked", "blocked_reason": blocked_reason},
        )

    # ---------------------------------------------------------------- assurance
    if team_status.get("assurance") != "completed":
        if _team_runs(state, "assurance") >= 4:
            return _route(
                state,
                db,
                "escalate",
                "Assurance team exceeded its run limit.",
                {"status": "failed", "escalation_reason": "Assurance team run limit exceeded."},
            )
        if team_status.get("assurance") == "escalated":
            return _route(
                state,
                db,
                "escalate",
                "Assurance team escalated a reviewer failure.",
                {"status": "failed", "escalation_reason": state.get("escalation_reason")},
            )
        if team_status.get("assurance") == "needs_revision":
            revision_count = int(state.get("revision_count", 0))
            max_revisions = int(state.get("max_revisions", settings.max_revisions))
            if revision_count >= max_revisions:
                return _route(
                    state,
                    db,
                    "escalate",
                    "Assurance failed and the revision limit is exhausted.",
                    {
                        "status": "failed",
                        "escalation_reason": "Maximum revisions reached after a failed review.",
                    },
                )
            feedback = _feedback_text(state)
            if writer_needed:
                return _route(
                    state,
                    db,
                    "drafting_team",
                    "Assurance asked for a bounded revision.",
                    {
                        "status": "in_progress",
                        "phase": "drafting",
                        "revision_count": revision_count + 1,
                        "revision_feedback": feedback,
                        "revision_target": "drafting",
                        "draft": "",
                        "policy_report": None,
                        "review_result": None,
                        "team_status": {"drafting": "pending", "assurance": "pending"},
                        "subtask_status": _reset_status(state, {"report_writer"}),
                        "retry_counts": {
                            "team:drafting": _team_runs(state, "drafting") + 1,
                        },
                    },
                )
            # A summary/outline plan has no writer to revise. Sending it to the
            # drafting team would produce nothing and block the task, so the
            # revision re-runs analysis and lets the analysis wrapper rebuild the
            # formatted summary. This mirrors the human revision path.
            return _route(
                state,
                db,
                "analysis_team",
                "Assurance asked for a bounded revision; the plan has no writer to revise.",
                {
                    "status": "in_progress",
                    "phase": "analysis",
                    "revision_count": revision_count + 1,
                    "revision_feedback": feedback,
                    "revision_target": "analysis",
                    "claims": [],
                    "evidence": [],
                    "analysis_summary": "",
                    "draft": "",
                    "policy_report": None,
                    "review_result": None,
                    "team_status": {
                        "analysis": "pending",
                        "drafting": "pending",
                        "assurance": "pending",
                    },
                    "subtask_status": _reset_status(
                        state, {"document_analyst", "evidence_verifier"}
                    ),
                    "retry_counts": {
                        "team:analysis": _team_runs(state, "analysis") + 1,
                    },
                },
            )
        return _route(
            state,
            db,
            "assurance_team",
            "Draft requires policy checks and independent review.",
            {
                "phase": "assurance",
                "retry_counts": {"team:assurance": _team_runs(state, "assurance") + 1},
            },
        )

    # -------------------------------------------------------------- human gate
    version_id = state.get("current_version_id")
    content_hash = state.get("current_content_hash")
    if not version_id or not content_hash:
        return _route(
            state,
            db,
            "escalate",
            "No versioned draft exists for human review.",
            {"status": "failed", "escalation_reason": "Missing output version."},
        )
    try:
        _set_status(db, task_id, TaskStatus.AWAITING_HUMAN_REVIEW.value)
    except ValueError as exc:
        return _route(
            state,
            db,
            "escalate",
            f"Could not move the task to human review: {exc}",
            {"status": "failed", "escalation_reason": str(exc)},
        )
    return _route(
        state,
        db,
        "human_review",
        "Assurance passed; the human approval gate is now open.",
        {"status": TaskStatus.AWAITING_HUMAN_REVIEW.value, "phase": "human_review"},
    )


def _feedback_text(state: dict[str, Any]) -> str:
    policy = state.get("policy_report") or {}
    review = state.get("review_result") or {}
    parts: list[str] = []
    for finding in policy.get("findings", []):
        if finding.get("severity") == "high":
            parts.append(f"{finding.get('rule_id')}: {finding.get('message')}")
    for issue in review.get("issues", []):
        parts.append(str(issue))
    return "; ".join(parts)[:2000] or "Assurance requested a revision."


def _reset_status(state: dict[str, Any], agents: set[str]) -> dict[str, str]:
    """Mark the given agents' subtasks pending so a lead re-runs only those."""
    statuses = dict(state.get("subtask_status") or {})
    for subtask in (state.get("plan") or {}).get("subtasks", []):
        if subtask.get("assigned_agent") in agents:
            statuses[subtask["id"]] = "pending"
    return statuses
