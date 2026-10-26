"""Rule-based team leads.

Team leads are deterministic supervisors: they validate prerequisites, choose the
next worker from the plan, apply bounded retries, and report completed, blocked,
or escalated upward. They make no model calls.
"""

from __future__ import annotations

from typing import Any

from ..models import utcnow_iso


def _with_routing(
    state: dict[str, Any], from_node: str, to_node: str, reason: str, rule: str
) -> list[dict[str, Any]]:
    log = list(state.get("routing_log") or [])
    log.append(
        {
            "from_node": from_node,
            "to_node": to_node,
            "reason": reason,
            "rule": rule,
            "depth": 2,
        }
    )
    return log


def _merge_team_status(state: dict[str, Any], team: str, value: str) -> dict[str, str]:
    statuses = dict(state.get("team_status") or {})
    statuses[team] = value
    return statuses


def analysis_lead(state: dict[str, Any]) -> dict[str, Any]:
    iterations = int(state.get("lead_iterations", 0)) + 1
    subtasks = (state.get("plan") or {}).get("subtasks", [])
    statuses = dict(state.get("subtask_status") or {})
    analyst_ids = [
        s["id"] for s in subtasks if s.get("assigned_agent") == "document_analyst"
    ]
    verifier_ids = [
        s["id"] for s in subtasks if s.get("assigned_agent") == "evidence_verifier"
    ]
    readable = [
        d
        for d in (state.get("documents") or {}).values()
        if d.get("status") == "ok" and d.get("text", "").strip()
    ]

    if iterations > 8:
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "analysis", "escalated"),
            "status": "failed",
            "escalation_reason": "Analysis Lead exceeded its internal delegation limit.",
            "routing_log": _with_routing(
                state,
                "analysis_lead",
                "escalate",
                "Internal delegation limit exceeded.",
                "GR-07",
            ),
            "updated_at": utcnow_iso(),
        }
    if not readable:
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "analysis", "blocked"),
            "status": "blocked",
            "blocked_reason": "No readable document is available for analysis.",
            "routing_log": _with_routing(
                state,
                "analysis_lead",
                "blocked",
                "No readable document input.",
                "GR-02",
            ),
            "updated_at": utcnow_iso(),
        }

    failed = [
        r
        for r in (state.get("agent_results") or [])
        if r.get("agent") in {"document_analyst", "evidence_verifier"}
        and r.get("status") == "failed"
    ]
    if failed:
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "analysis", "escalated"),
            "status": "failed",
            "escalation_reason": f"Analysis worker failed: {failed[-1].get('error_class')}",
            "routing_log": _with_routing(
                state,
                "analysis_lead",
                "escalate",
                "A worker exhausted its retries.",
                "GR-07",
            ),
            "updated_at": utcnow_iso(),
        }

    if any(statuses.get(sid) != "completed" for sid in analyst_ids):
        return {
            "lead_iterations": iterations,
            "next_action": "document_analyst",
            "team_status": _merge_team_status(state, "analysis", "in_progress"),
            "routing_log": _with_routing(
                state,
                "analysis_lead",
                "document_analyst",
                "Document-analyst subtask is pending.",
                "PLAN",
            ),
            "updated_at": utcnow_iso(),
        }
    if verifier_ids and any(statuses.get(sid) != "completed" for sid in verifier_ids):
        if not state.get("claims"):
            return {
                "lead_iterations": iterations,
                "next_action": "END",
                "team_status": _merge_team_status(state, "analysis", "blocked"),
                "status": "blocked",
                "blocked_reason": "No claims were extracted, so there is nothing to verify.",
                "routing_log": _with_routing(
                    state,
                    "analysis_lead",
                    "blocked",
                    "Verifier has no claims to check.",
                    "GR-02",
                ),
                "updated_at": utcnow_iso(),
            }
        return {
            "lead_iterations": iterations,
            "next_action": "evidence_verifier",
            "team_status": _merge_team_status(state, "analysis", "in_progress"),
            "routing_log": _with_routing(
                state,
                "analysis_lead",
                "evidence_verifier",
                "Verification subtask is pending.",
                "PLAN",
            ),
            "updated_at": utcnow_iso(),
        }

    has_writer = any(
        s.get("assigned_agent") == "report_writer" for s in subtasks
    )
    return {
        "lead_iterations": iterations,
        "next_action": "END",
        "team_status": _merge_team_status(state, "analysis", "completed"),
        "phase": "drafting" if has_writer else "assurance",
        "status": "in_progress",
        "routing_log": _with_routing(
            state,
            "analysis_lead",
            "orchestrator",
            "Analysis team completed.",
            "PLAN",
        ),
        "updated_at": utcnow_iso(),
    }


def drafting_lead(state: dict[str, Any]) -> dict[str, Any]:
    iterations = int(state.get("lead_iterations", 0)) + 1
    subtasks = (state.get("plan") or {}).get("subtasks", [])
    statuses = dict(state.get("subtask_status") or {})
    writer_ids = [
        s["id"] for s in subtasks if s.get("assigned_agent") == "report_writer"
    ]
    if iterations > 6:
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "drafting", "escalated"),
            "status": "failed",
            "escalation_reason": "Drafting Lead exceeded its internal delegation limit.",
            "routing_log": _with_routing(
                state, "drafting_lead", "escalate", "Delegation limit.", "GR-07"
            ),
            "updated_at": utcnow_iso(),
        }
    failed = [
        r
        for r in (state.get("agent_results") or [])
        if r.get("agent") == "report_writer" and r.get("status") == "failed"
    ]
    if failed:
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "drafting", "escalated"),
            "status": "failed",
            "escalation_reason": "Report Writer exhausted its retries.",
            "routing_log": _with_routing(
                state, "drafting_lead", "escalate", "Writer failed.", "GR-07"
            ),
            "updated_at": utcnow_iso(),
        }
    if not state.get("claims") and not state.get("analysis_summary"):
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "drafting", "blocked"),
            "status": "blocked",
            "blocked_reason": "Drafting requires claims or an analysis summary.",
            "routing_log": _with_routing(
                state,
                "drafting_lead",
                "blocked",
                "No verified material to write from.",
                "GR-02",
            ),
            "updated_at": utcnow_iso(),
        }
    if writer_ids and any(statuses.get(sid) != "completed" for sid in writer_ids):
        return {
            "lead_iterations": iterations,
            "next_action": "report_writer",
            "team_status": _merge_team_status(state, "drafting", "in_progress"),
            "routing_log": _with_routing(
                state,
                "drafting_lead",
                "report_writer",
                "Drafting subtask is pending or was reset for revision.",
                "PLAN",
            ),
            "updated_at": utcnow_iso(),
        }
    return {
        "lead_iterations": iterations,
        "next_action": "END",
        "team_status": _merge_team_status(state, "drafting", "completed"),
        "phase": "assurance",
        "status": "in_progress",
        "routing_log": _with_routing(
            state,
            "drafting_lead",
            "orchestrator",
            "Drafting team completed.",
            "PLAN",
        ),
        "updated_at": utcnow_iso(),
    }


def assurance_lead(state: dict[str, Any]) -> dict[str, Any]:
    iterations = int(state.get("lead_iterations", 0)) + 1
    if iterations > 6:
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "assurance", "escalated"),
            "status": "failed",
            "escalation_reason": "Assurance Lead exceeded its internal delegation limit.",
            "routing_log": _with_routing(
                state, "assurance_lead", "escalate", "Delegation limit.", "GR-07"
            ),
            "updated_at": utcnow_iso(),
        }
    if not (state.get("draft") or "").strip():
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "assurance", "blocked"),
            "status": "blocked",
            "blocked_reason": "Assurance requires a non-empty draft.",
            "routing_log": _with_routing(
                state, "assurance_lead", "blocked", "No draft to review.", "GR-01"
            ),
            "updated_at": utcnow_iso(),
        }
    failed = [
        r
        for r in (state.get("agent_results") or [])
        if r.get("agent") == "reviewer" and r.get("status") == "failed"
    ]
    if failed:
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "assurance", "escalated"),
            "status": "failed",
            "escalation_reason": "Reviewer exhausted its retries.",
            "routing_log": _with_routing(
                state, "assurance_lead", "escalate", "Reviewer failed.", "GR-07"
            ),
            "updated_at": utcnow_iso(),
        }
    if state.get("policy_report") is None:
        return {
            "lead_iterations": iterations,
            "next_action": "policy_checker",
            "team_status": _merge_team_status(state, "assurance", "in_progress"),
            "routing_log": _with_routing(
                state,
                "assurance_lead",
                "policy_checker",
                "Deterministic policy checks have not run.",
                "GR-02",
            ),
            "updated_at": utcnow_iso(),
        }
    if state.get("review_result") is None:
        return {
            "lead_iterations": iterations,
            "next_action": "reviewer",
            "team_status": _merge_team_status(state, "assurance", "in_progress"),
            "routing_log": _with_routing(
                state,
                "assurance_lead",
                "reviewer",
                "Independent review has not run.",
                "GR-02",
            ),
            "updated_at": utcnow_iso(),
        }

    policy = state.get("policy_report") or {}
    review = state.get("review_result") or {}
    if policy.get("passed") and review.get("decision") == "pass":
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "assurance", "completed"),
            "phase": "human_review",
            "status": "in_progress",
            "routing_log": _with_routing(
                state,
                "assurance_lead",
                "orchestrator",
                "Policy checks and independent review passed.",
                "GR-01",
            ),
            "updated_at": utcnow_iso(),
        }

    if int(state.get("revision_count", 0)) >= int(state.get("max_revisions", 2)):
        return {
            "lead_iterations": iterations,
            "next_action": "END",
            "team_status": _merge_team_status(state, "assurance", "escalated"),
            "status": "failed",
            "escalation_reason": "Assurance failed and the revision limit is exhausted.",
            "routing_log": _with_routing(
                state,
                "assurance_lead",
                "escalate",
                "Revision limit exhausted after a failed review.",
                "GR-07",
            ),
            "updated_at": utcnow_iso(),
        }
    return {
        "lead_iterations": iterations,
        "next_action": "END",
        "team_status": _merge_team_status(state, "assurance", "needs_revision"),
        "phase": "assurance",
        "status": "in_progress",
        "routing_log": _with_routing(
            state,
            "assurance_lead",
            "orchestrator",
            "Assurance failed; a bounded revision is required.",
            "GR-02",
        ),
        "updated_at": utcnow_iso(),
    }


def route_from_lead(state: dict[str, Any]) -> str:
    action = state.get("next_action") or "END"
    return action if action != "END" else "__end__"
