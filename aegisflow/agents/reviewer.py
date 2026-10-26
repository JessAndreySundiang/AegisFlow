"""Independent Reviewer: checks the draft before human review."""

from __future__ import annotations

import re
from typing import Any

from config import Settings

from ..agents.base import AgentFailure, call_agent, failure_result
from ..database import Database
from ..models import (
    ClaimStatus,
    PolicyReport,
    ReviewDecision,
    ReviewResult,
    utcnow_iso,
)
from ..skills_loader import Skill, render_agent_skills
from ..validation import ValidationError

SYSTEM_PROMPT = """You are the AegisFlow Reviewer, an independent checker.
You did not write the draft. Do not rewrite it. Check:
1. Completeness against the plan objective and required sections.
2. Traceability: every key finding has [S#] or [UNVERIFIED].
3. Consistency with verified claim statuses.
4. Consistency with the deterministic Policy Checker report.
5. Visible limitations and missing information.
6. No claim that an external action occurred.

Return pass, needs_revision, or fail with concrete reasons.
Do not invent a quality score. Return JSON only.
"""

_WORD = re.compile(r"[A-Za-z]{5,}")


def build_mock_review(
    plan: dict[str, Any] | None,
    draft: str,
    policy: dict[str, Any] | None,
    claims: list[dict[str, Any]],
    simulated: bool,
) -> ReviewResult:
    issues: list[str] = []
    reasons: list[str] = []
    if not draft.strip():
        return ReviewResult(
            decision=ReviewDecision.FAIL,
            reasons=["Draft is empty."],
            issues=["empty_draft"],
            plan_alignment="No draft to compare.",
            policy_consistency="Not applicable.",
            simulated=simulated,
        )

    policy_obj = PolicyReport.model_validate(policy) if policy else None
    if policy_obj is not None:
        high = [f for f in policy_obj.findings if f.severity == "high"]
        if high:
            issues.extend(f"{f.rule_id}: {f.message} ({f.location})" for f in high)
    if issues:
        return ReviewResult(
            decision=ReviewDecision.NEEDS_REVISION,
            reasons=["The deterministic policy check found blocking issues."],
            issues=issues,
            plan_alignment="Not assessed until policy issues are fixed.",
            policy_consistency="Draft is inconsistent with the policy report.",
            simulated=simulated,
        )

    lowered = draft.lower()
    for section in ("## summary", "## key findings", "## sources", "## limitations"):
        if section not in lowered:
            issues.append(f"Missing section: {section}")
    if not issues:
        reasons.append("Draft contains all required sections.")
    unsupported = [
        c for c in claims if c.get("status") in {
            ClaimStatus.UNSUPPORTED.value,
            ClaimStatus.CONFLICTING.value,
        }
    ]
    for claim in unsupported:
        if "unverified" not in lowered:
            issues.append(
                f"Claim {claim.get('id')} is {claim.get('status')} but the draft has no UNVERIFIED label."
            )
    if not issues:
        reasons.append("Claim statuses are consistent with the draft labels.")

    objective = (plan or {}).get("objective", "")
    objective_words = set(_WORD.findall(objective.lower()))
    draft_words = set(_WORD.findall(lowered))
    if objective_words and not (objective_words & draft_words):
        issues.append("Draft does not visibly address the plan objective.")
        plan_alignment = "Weak: no objective keywords appear in the draft."
    else:
        plan_alignment = "Draft addresses the plan objective at a high level."
    if not issues:
        reasons.append("Draft is broadly aligned with the plan.")
    if simulated:
        reasons.append("Reviewer notes that this is simulated output.")

    if issues:
        return ReviewResult(
            decision=ReviewDecision.NEEDS_REVISION,
            reasons=["Reviewer found issues that require a revision."],
            issues=issues,
            plan_alignment=plan_alignment,
            policy_consistency="Policy checks passed, but review issues remain.",
            simulated=simulated,
        )
    return ReviewResult(
        decision=ReviewDecision.PASS,
        reasons=reasons,
        issues=[],
        plan_alignment=plan_alignment,
        policy_consistency="Consistent with the passing policy report.",
        simulated=simulated,
    )


def run_reviewer(
    state: dict[str, Any],
    *,
    settings: Settings,
    llm: Any,
    db: Database,
    skills: dict[str, Skill],
) -> dict[str, Any]:
    task_id = state["task_id"]
    plan = state.get("plan")
    draft = state.get("draft", "")
    policy = state.get("policy_report")
    claims = state.get("claims", [])

    payload = {
        "plan": plan,
        "draft": draft,
        "policy_report": policy,
        "claims": claims,
        "simulated": settings.simulated,
    }
    system_prompt = SYSTEM_PROMPT + "\n\n" + render_agent_skills("reviewer", skills)

    def validator(result: ReviewResult) -> None:
        if result.decision == ReviewDecision.PASS and result.issues:
            raise ValidationError("Reviewer cannot pass a draft while listing issues.")
        if result.decision != ReviewDecision.PASS and not result.reasons:
            raise ValidationError("Reviewer must give reasons for a non-pass decision.")

    try:
        result, retries = call_agent(
            agent="reviewer",
            schema=ReviewResult,
            system_prompt=system_prompt,
            payload=payload,
            mock_builder=lambda: build_mock_review(
                plan, draft, policy, claims, settings.simulated
            ),
            settings=settings,
            llm=llm,
            db=db,
            task_id=task_id,
            level=3,
            skill="quality-review",
            input_ref=f"draft_chars={len(draft)}; policy_passed={bool(policy and policy.get('passed'))}",
            validator=validator,
        )
    except AgentFailure as failure:
        db.add_audit(task_id, "agent_failed", "agent:reviewer", "GR-07", str(failure))
        return {
            "status": "failed",
            "escalation_reason": str(failure),
            "last_team_result": {
                "agent": "reviewer",
                "status": "failed",
                "error_class": failure.error_class,
            },
            "agent_results": [
                failure_result(
                    agent="reviewer",
                    level=3,
                    skill="quality-review",
                    failure=failure,
                    simulated=settings.simulated,
                )
            ],
            "errors": [
                {
                    "agent": "reviewer",
                    "error_class": failure.error_class,
                    "message": str(failure),
                }
            ],
            "retry_counts": {"reviewer": failure.retries},
            "updated_at": utcnow_iso(),
        }

    db.add_audit(
        task_id,
        "agent_completed",
        "agent:reviewer",
        "GR-02",
        f"decision={result.decision.value}; issues={len(result.issues)}; retries={retries}",
    )
    return {
        "review_result": result.model_dump(mode="json"),
        "phase": "assurance",
        "status": "in_progress",
        "last_team_result": {
            "agent": "reviewer",
            "status": "completed",
            "decision": result.decision.value,
            "issues": len(result.issues),
        },
        "agent_results": list(state.get("agent_results") or []) + [
            {
                "agent": "reviewer",
                "level": 3,
                "skill": "quality-review",
                "status": "completed",
                "summary": f"Review decision: {result.decision.value}",
                "output": result.model_dump(mode="json"),
                "claims": [],
                "evidence": [],
                "missing_information": [],
                "uncertainty": result.issues,
                "error_class": "",
                "retries": retries,
                "simulated": settings.simulated,
                "started_at": utcnow_iso(),
                "finished_at": utcnow_iso(),
            }
        ],
        "audit_events": [
            {
                "event_type": "review_completed",
                "actor": "agent:reviewer",
                "rule_id": "GR-02",
                "detail": f"decision={result.decision.value}; issues={len(result.issues)}",
            }
        ],
        "updated_at": utcnow_iso(),
    }
