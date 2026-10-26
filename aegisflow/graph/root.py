"""Root LangGraph: validate -> plan -> orchestrate -> teams -> human -> finalize."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from config import Settings

from ..agents.planner import run_planner
from ..approvals import (
    ApprovalError,
    assert_finalizable,
    create_output_version,
)
from ..database import Database
from ..models import (
    ClaimStatus,
    HumanDecision,
    TaskStatus,
    utcnow_iso,
)
from ..skills_loader import Skill
from ..state import AegisState
from ..validation import validate_request
from .analysis_team import build_analysis_team
from .assurance_team import build_assurance_team
from .drafting_team import build_drafting_team
from .orchestrator import WHITELIST, orchestrator_node

TEAM_INPUT_KEYS = (
    "task_id",
    "request",
    "output_format",
    "files",
    "documents",
    "plan",
    "claims",
    "evidence",
    "analysis_summary",
    "draft",
    "draft_version",
    "current_version_id",
    "current_content_hash",
    "policy_report",
    "review_result",
    "revision_count",
    "max_revisions",
    "revision_feedback",
    "revision_target",
    "status",
    "escalation_reason",
    "blocked_reason",
    "error",
    "team_status",
    "subtask_status",
    "retry_counts",
    "simulated",
)

TEAM_OUTPUT_KEYS = (
    "agent_results",
    "errors",
    "routing_log",
    "claims",
    "evidence",
    "analysis_summary",
    "draft",
    "policy_report",
    "review_result",
    "subtask_status",
    "team_status",
    "phase",
    "status",
    "escalation_reason",
    "blocked_reason",
    "last_team_result",
    "retry_counts",
)


def _team_input(state: dict[str, Any]) -> dict[str, Any]:
    data = {key: state.get(key) for key in TEAM_INPUT_KEYS}
    data["agent_results"] = []
    data["errors"] = []
    data["routing_log"] = []
    data["lead_iterations"] = 0
    data["subtask_status"] = dict(state.get("subtask_status") or {})
    data["team_status"] = dict(state.get("team_status") or {})
    data["retry_counts"] = dict(state.get("retry_counts") or {})
    data["simulated"] = bool(state.get("simulated", True))
    return data


def _team_output(result: dict[str, Any]) -> dict[str, Any]:
    out = {key: result[key] for key in TEAM_OUTPUT_KEYS if key in result}
    for key in ("agent_results", "errors", "routing_log"):
        out.setdefault(key, [])
    out.setdefault("subtask_status", {})
    out.setdefault("team_status", {})
    return out


def _persist_evidence(
    db: Database,
    task_id: str,
    version_id: str,
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> None:
    if not claims:
        return
    existing = {
        (row["claim_id"], row["output_version_id"])
        for row in db.list_evidence(task_id)
    }
    by_claim = {str(item.get("id")): item for item in evidence}
    for claim in claims:
        claim_id = str(claim.get("id", ""))
        if not claim_id or (claim_id, version_id) in existing:
            continue
        item = by_claim.get(claim_id, {})
        source_ref = str(claim.get("source_ref", ""))
        filename = source_ref.split(" — ")[0] if " — " in source_ref else source_ref
        location = source_ref.split(" — ")[-1] if " — " in source_ref else "document"
        db.add_evidence(
            task_id=task_id,
            output_version_id=version_id,
            claim_id=claim_id,
            claim_text=str(claim.get("text", ""))[:2000],
            file_id=str(item.get("file_id", "")),
            filename=str(item.get("filename", filename)),
            location=str(item.get("location", location)),
            excerpt=str(item.get("excerpt", claim.get("text", "")))[:2000],
            status=str(claim.get("status", "unverified")),
        )


def _summary_draft(state: dict[str, Any]) -> str:
    claims = state.get("claims", [])
    lines = ["# Document Summary", ""]
    if state.get("simulated", True):
        lines.append(
            "**SIMULATED OUTPUT** — deterministic mock content; not real AI analysis."
        )
        lines.append("")
    lines.append(f"**Request:** {state.get('request', '').strip()}")
    lines.append("")
    lines.append("## Summary")
    lines.append(
        state.get("analysis_summary")
        or "No summary could be produced from the supplied documents."
    )
    lines.append("")
    lines.append("## Key Findings")
    if claims:
        for claim in claims:
            status = claim.get("status", "unverified")
            label = (
                f"[{claim.get('id', 'S?')}]"
                if status == ClaimStatus.SUPPORTED.value
                else f"[UNVERIFIED: {status}]"
            )
            lines.append(f"- {claim.get('text', '')} {label}")
    else:
        lines.append("- No claims were extracted. [UNVERIFIED: no source claims]")
    lines.append("")
    lines.append("## Sources")
    if claims:
        for claim in claims:
            if claim.get("source_ref"):
                lines.append(
                    f"[{claim.get('id', 'S?')}] {claim.get('source_ref')} — "
                    f"\"{str(claim.get('text', ''))[:180]}\""
                )
    else:
        lines.append("No sources were available.")
    lines.append("")
    lines.append("## Limitations / Unverified")
    unverified = [
        c for c in claims if c.get("status") != ClaimStatus.SUPPORTED.value
    ]
    if unverified:
        lines.append(
            f"- {len(unverified)} claim(s) remain unverified or unsupported."
        )
    if not claims:
        lines.append("- No source claims were available.")
    if state.get("simulated", True):
        lines.append("- This is simulated mock output produced without a remote model.")
    lines.append("")
    return "\n".join(lines)


def build_root_graph(
    settings: Settings,
    db: Database,
    llm: Any,
    skills: dict[str, Skill],
    checkpointer: Any,
):
    analysis_team = build_analysis_team(settings, db, llm, skills)
    drafting_team = build_drafting_team(settings, db, llm, skills)
    assurance_team = build_assurance_team(settings, db, llm, skills)

    def validate_request_node(state: dict[str, Any]) -> dict[str, Any]:
        errors = validate_request(
            state.get("request", ""),
            state.get("output_format", "markdown"),
            state.get("files", []),
        )
        if errors:
            reason = "; ".join(errors)
            try:
                db.transition_task(state["task_id"], TaskStatus.BLOCKED, escalation_reason=reason)
            except ValueError:
                pass
            db.add_audit(state["task_id"], "request_blocked", "system:validate", "GR-02", reason)
            return {
                "status": TaskStatus.BLOCKED.value,
                "blocked_reason": reason,
                "audit_events": [
                    {
                        "event_type": "request_blocked",
                        "actor": "system:validate",
                        "rule_id": "GR-02",
                        "detail": reason,
                    }
                ],
                "updated_at": utcnow_iso(),
            }
        try:
            db.transition_task(state["task_id"], TaskStatus.PLANNING)
        except ValueError:
            pass
        db.add_audit(
            state["task_id"],
            "request_validated",
            "system:validate",
            None,
            f"files={len(state.get('files', []))}; format={state.get('output_format')}",
        )
        return {
            "status": TaskStatus.PLANNING.value,
            "phase": "planning",
            "audit_events": [
                {
                    "event_type": "request_validated",
                    "actor": "system:validate",
                    "rule_id": None,
                    "detail": "Request and file metadata passed validation.",
                }
            ],
            "updated_at": utcnow_iso(),
        }

    def planner_node(state: dict[str, Any]) -> dict[str, Any]:
        return run_planner(
            state, settings=settings, llm=llm, db=db, skills=skills
        )

    def analysis_team_node(state: dict[str, Any]) -> dict[str, Any]:
        result = analysis_team.invoke(_team_input(state))
        out = _team_output(result)
        writer_needed = any(
            s.get("assigned_agent") == "report_writer"
            for s in (state.get("plan") or {}).get("subtasks", [])
        )
        if (
            out.get("team_status", {}).get("analysis") == "completed"
            and not writer_needed
            and not (out.get("draft") or "").strip()
        ):
            draft = _summary_draft({**state, **out})
            version = create_output_version(
                db,
                state["task_id"],
                draft,
                "agent",
                validation_status="pending",
                simulated=settings.simulated,
            )
            out.update(
                {
                    "draft": draft,
                    "draft_version": version.version_number,
                    "current_version_id": version.id,
                    "current_content_hash": version.content_hash,
                    "phase": "assurance",
                }
            )
            _persist_evidence(
                db, state["task_id"], version.id, out.get("claims", []), out.get("evidence", [])
            )
        return out

    def drafting_team_node(state: dict[str, Any]) -> dict[str, Any]:
        result = drafting_team.invoke(_team_input(state))
        out = _team_output(result)
        draft = out.get("draft") or ""
        if draft.strip():
            current_hash = state.get("current_content_hash")
            from ..models import sha256_text

            draft_hash = sha256_text(draft)
            if not state.get("current_version_id") or draft_hash != current_hash:
                version = create_output_version(
                    db,
                    state["task_id"],
                    draft,
                    "agent",
                    validation_status="pending",
                    simulated=settings.simulated,
                )
                out.update(
                    {
                        "draft_version": version.version_number,
                        "current_version_id": version.id,
                        "current_content_hash": version.content_hash,
                        "policy_report": None,
                        "review_result": None,
                        "team_status": {
                            **dict(out.get("team_status") or {}),
                            "assurance": "pending",
                        },
                    }
                )
                _persist_evidence(
                    db,
                    state["task_id"],
                    version.id,
                    out.get("claims", []),
                    out.get("evidence", []),
                )
                db.add_audit(
                    state["task_id"],
                    "draft_version_created",
                    "system:drafting",
                    "GR-01",
                    f"version={version.version_number}; hash={version.content_hash[:12]}...",
                )
        return out

    def assurance_team_node(state: dict[str, Any]) -> dict[str, Any]:
        result = assurance_team.invoke(_team_input(state))
        return _team_output(result)

    def human_review_node(state: dict[str, Any]) -> Command | dict[str, Any]:
        version_id = state.get("current_version_id")
        content_hash = state.get("current_content_hash")
        if not version_id or not content_hash:
            return Command(
                goto="escalate",
                update={
                    "status": "failed",
                    "escalation_reason": "Human review reached without a versioned draft.",
                },
            )
        reviews = db.list_human_reviews(state["task_id"])
        payload = {
            "task_id": state["task_id"],
            "request": state.get("request"),
            "draft": state.get("draft", ""),
            "claims": state.get("claims", []),
            "evidence": state.get("evidence", []),
            "policy_report": state.get("policy_report"),
            "review_result": state.get("review_result"),
            "version_id": version_id,
            "version_number": state.get("draft_version", 0),
            "content_hash": content_hash,
            "simulated": bool(state.get("simulated", True)),
            "revision_count": int(state.get("revision_count", 0)),
            "max_revisions": int(state.get("max_revisions", settings.max_revisions)),
            "previous_decisions": [
                {
                    "decision": r.decision.value,
                    "reviewer": r.reviewer,
                    "feedback": r.feedback,
                    "created_at": r.created_at,
                }
                for r in reviews
            ],
        }
        decision = interrupt(payload)
        if not isinstance(decision, dict):
            return Command(
                goto="escalate",
                update={
                    "status": "failed",
                    "escalation_reason": "Invalid human decision payload.",
                },
            )
        action = str(decision.get("decision", ""))
        feedback = str(decision.get("feedback", ""))
        if action == HumanDecision.APPROVE.value:
            try:
                approval = assert_finalizable(db, state["task_id"], version_id, content_hash)
            except ApprovalError as exc:
                db.add_audit(
                    state["task_id"],
                    "approval_rejected",
                    "system:human_review",
                    "GR-01",
                    str(exc),
                )
                return Command(
                    goto="escalate",
                    update={
                        "status": "failed",
                        "escalation_reason": str(exc),
                        "human_decision": decision,
                    },
                )
            return Command(
                goto="finalize",
                update={
                    "human_decision": decision,
                    "approval_id": approval.id,
                    "status": TaskStatus.APPROVED.value,
                    "phase": "finalize",
                },
            )
        if action == HumanDecision.REJECT.value:
            latest = db.latest_review_for_version(version_id)
            if latest is None or latest.decision != HumanDecision.REJECT:
                return Command(
                    goto="escalate",
                    update={
                        "status": "failed",
                        "escalation_reason": "Reject decision was not persisted before resume.",
                    },
                )
            return Command(
                goto="rejected",
                update={
                    "human_decision": decision,
                    "status": TaskStatus.REJECTED.value,
                    "phase": "rejected",
                },
            )
        if action == HumanDecision.REQUEST_REVISION.value:
            latest = db.latest_review_for_version(version_id)
            if latest is None or latest.decision != HumanDecision.REQUEST_REVISION:
                return Command(
                    goto="escalate",
                    update={
                        "status": "failed",
                        "escalation_reason": "Revision decision was not persisted before resume.",
                    },
                )
            if int(state.get("revision_count", 0)) >= int(
                state.get("max_revisions", settings.max_revisions)
            ):
                return Command(
                    goto="escalate",
                    update={
                        "status": "failed",
                        "escalation_reason": "Maximum human revisions reached.",
                    },
                )
            try:
                db.transition_task(state["task_id"], TaskStatus.IN_PROGRESS)
            except ValueError:
                pass
            target = str(decision.get("revision_target", "drafting"))
            has_writer = any(
                s.get("assigned_agent") == "report_writer"
                for s in (state.get("plan") or {}).get("subtasks", [])
            )
            if not has_writer:
                target = "analysis"
            if target == "analysis":
                statuses = dict(state.get("subtask_status") or {})
                for subtask in (state.get("plan") or {}).get("subtasks", []):
                    if subtask.get("assigned_agent") in {
                        "document_analyst",
                        "evidence_verifier",
                    }:
                        statuses[subtask["id"]] = "pending"
                update = {
                    "status": TaskStatus.IN_PROGRESS.value,
                    "phase": "analysis",
                    "revision_count": int(state.get("revision_count", 0)) + 1,
                    "revision_feedback": feedback,
                    "revision_target": "analysis",
                    "claims": [],
                    "evidence": [],
                    "analysis_summary": "",
                    "draft": "",
                    "policy_report": None,
                    "review_result": None,
                    "subtask_status": statuses,
                    "team_status": {"analysis": "pending", "drafting": "pending", "assurance": "pending"},
                    "human_decision": decision,
                }
            else:
                statuses = dict(state.get("subtask_status") or {})
                for subtask in (state.get("plan") or {}).get("subtasks", []):
                    if subtask.get("assigned_agent") == "report_writer":
                        statuses[subtask["id"]] = "pending"
                update = {
                    "status": TaskStatus.IN_PROGRESS.value,
                    "phase": "drafting",
                    "revision_count": int(state.get("revision_count", 0)) + 1,
                    "revision_feedback": feedback,
                    "revision_target": "drafting",
                    "draft": "",
                    "policy_report": None,
                    "review_result": None,
                    "subtask_status": statuses,
                    "team_status": {"drafting": "pending", "assurance": "pending"},
                    "human_decision": decision,
                }
            return Command(goto="orchestrator", update=update)
        return Command(
            goto="escalate",
            update={
                "status": "failed",
                "escalation_reason": f"Unknown human decision: {action}",
            },
        )

    def finalize_node(state: dict[str, Any]) -> Command | dict[str, Any]:
        try:
            approval = assert_finalizable(
                db,
                state["task_id"],
                state.get("current_version_id", ""),
                state.get("current_content_hash", ""),
            )
        except ApprovalError as exc:
            return Command(
                goto="escalate",
                update={
                    "status": "failed",
                    "escalation_reason": f"Finalization refused: {exc}",
                },
            )
        task = db.get_task(state["task_id"])
        elapsed = None
        if task is not None:
            from datetime import datetime

            try:
                created = datetime.fromisoformat(task.created_at)
                elapsed = (datetime.now(created.tzinfo) - created).total_seconds()
            except ValueError:
                elapsed = None
        db.transition_task(
            state["task_id"],
            TaskStatus.COMPLETED,
            elapsed_seconds=elapsed,
        )
        db.add_audit(
            state["task_id"],
            "finalized",
            "system:finalize",
            "GR-01",
            f"version={approval.version_number}; hash={approval.content_hash[:12]}...; "
            f"reviewer={approval.reviewer}",
        )
        return {
            "status": TaskStatus.COMPLETED.value,
            "phase": "done",
            "approval_id": approval.id,
            "updated_at": utcnow_iso(),
        }

    def blocked_node(state: dict[str, Any]) -> dict[str, Any]:
        try:
            db.transition_task(
                state["task_id"],
                TaskStatus.BLOCKED,
                escalation_reason=state.get("blocked_reason") or "Blocked.",
            )
        except ValueError:
            pass
        db.add_audit(
            state["task_id"],
            "task_blocked",
            "system:blocked",
            "GR-07",
            state.get("blocked_reason") or "Blocked.",
        )
        return {
            "status": TaskStatus.BLOCKED.value,
            "phase": "blocked",
            "updated_at": utcnow_iso(),
        }

    def escalate_node(state: dict[str, Any]) -> dict[str, Any]:
        reason = state.get("escalation_reason") or "Escalated to the human."
        try:
            db.transition_task(
                state["task_id"], TaskStatus.FAILED, escalation_reason=reason
            )
        except ValueError:
            pass
        db.add_audit(
            state["task_id"], "task_escalated", "system:escalate", "GR-07", reason
        )
        return {
            "status": TaskStatus.FAILED.value,
            "phase": "escalated",
            "updated_at": utcnow_iso(),
        }

    def rejected_node(state: dict[str, Any]) -> dict[str, Any]:
        db.add_audit(
            state["task_id"],
            "task_rejected",
            "system:rejected",
            "GR-01",
            "Human rejected the output; it cannot be finalized.",
        )
        return {
            "status": TaskStatus.REJECTED.value,
            "phase": "rejected",
            "updated_at": utcnow_iso(),
        }

    def route_after_validate(state: dict[str, Any]) -> str:
        return "blocked" if state.get("status") == "blocked" else "planner"

    def route_after_planner(state: dict[str, Any]) -> str:
        if state.get("status") == "blocked":
            return "blocked"
        if state.get("status") == "failed":
            return "escalate"
        return "orchestrator"

    graph = StateGraph(AegisState)
    graph.add_node("validate_request", validate_request_node)
    graph.add_node("planner", planner_node)
    graph.add_node(
        "orchestrator",
        lambda state: orchestrator_node(state, db=db, settings=settings),
        destinations=WHITELIST,
    )
    graph.add_node("analysis_team", analysis_team_node)
    graph.add_node("drafting_team", drafting_team_node)
    graph.add_node("assurance_team", assurance_team_node)
    graph.add_node(
        "human_review",
        human_review_node,
        destinations=("finalize", "rejected", "orchestrator", "escalate"),
    )
    graph.add_node(
        "finalize", finalize_node, destinations=("escalate",)
    )
    graph.add_node("blocked", blocked_node)
    graph.add_node("escalate", escalate_node)
    graph.add_node("rejected", rejected_node)

    graph.add_edge(START, "validate_request")
    graph.add_conditional_edges(
        "validate_request",
        route_after_validate,
        {"planner": "planner", "blocked": "blocked"},
    )
    graph.add_conditional_edges(
        "planner",
        route_after_planner,
        {"orchestrator": "orchestrator", "blocked": "blocked", "escalate": "escalate"},
    )
    graph.add_edge("analysis_team", "orchestrator")
    graph.add_edge("drafting_team", "orchestrator")
    graph.add_edge("assurance_team", "orchestrator")
    graph.add_edge("finalize", END)
    graph.add_edge("blocked", END)
    graph.add_edge("escalate", END)
    graph.add_edge("rejected", END)
    return graph.compile(checkpointer=checkpointer)
