"""Report Writer: formats verified claims into the requested deliverable."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from config import Settings

from ..agents.base import AgentFailure, call_agent, failure_result
from ..database import Database
from ..models import ClaimStatus, StrictModel, utcnow_iso
from ..skills_loader import Skill, render_agent_skills
from ..validation import ValidationError

SYSTEM_PROMPT = """You are the AegisFlow Report Writer.
Build the requested deliverable from the verified claims and evidence supplied.
You format; you do not invent facts.

Required structure:
# Title
**SIMULATED OUTPUT** (only when simulated)
## Summary
## Key Findings
## Sources
## Limitations / Unverified

Every bullet in Key Findings ends with [S#] or [UNVERIFIED: reason].
The Sources section maps each [S#] to filename and location.
Never claim an email, submission, publication, deletion, or other external action occurred.
Return JSON only.
"""

TITLES = {
    "summary": "Document Summary",
    "report": "Document Report",
    "meeting_brief": "Meeting Brief",
    "outline": "Document Outline",
    "action_items": "Action Items",
}


class WriterOutput(StrictModel):
    draft: str
    claims: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _short(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_mock_draft(
    request: str,
    output_format: str,
    plan: dict[str, Any] | None,
    claims: list[dict[str, Any]],
    simulated: bool,
    revision_feedback: str = "",
) -> WriterOutput:
    task_type = (plan or {}).get("task_type", "report")
    title = TITLES.get(task_type, "Document Report")
    supported = [c for c in claims if c.get("status") == ClaimStatus.SUPPORTED.value]
    unverified = [c for c in claims if c.get("status") != ClaimStatus.SUPPORTED.value]
    limitations: list[str] = []

    lines: list[str] = [f"# {title}", ""]
    if simulated:
        lines.append(
            "**SIMULATED OUTPUT** — deterministic mock content; not real AI analysis."
        )
        lines.append("")
    lines.append(f"**Request:** {request.strip()}")
    lines.append("")
    if revision_feedback.strip():
        lines.append(f"> Revision note: {revision_feedback.strip()}")
        lines.append("")
    lines.append("## Summary")
    if supported:
        summary_sentences = " ".join(
            f"{_short(c.get('text', ''))} [{c.get('id', 'S?')}]"
            for c in supported[:2]
        )
        lines.append(
            f"This deliverable summarizes {len(supported)} verified finding(s) from the "
            f"supplied document(s). {summary_sentences}"
        )
    else:
        lines.append(
            "No verified findings were available. The limitations section records the gap; "
            "no facts were invented."
        )
    lines.append("")
    lines.append("## Key Findings")
    if claims:
        for claim in claims:
            status = claim.get("status", "unverified")
            label = f"[{claim.get('id', 'S?')}]"
            if status != ClaimStatus.SUPPORTED.value:
                label = f"[UNVERIFIED: {status}]"
            lines.append(f"- {_short(claim.get('text', ''))} {label}")
    else:
        lines.append("- No source claims were available. [UNVERIFIED: no claims extracted]")
    lines.append("")
    lines.append("## Sources")
    sourced = [c for c in claims if c.get("source_ref")]
    if sourced:
        for claim in sourced:
            lines.append(
                f"[{claim.get('id', 'S?')}] {claim.get('source_ref')} — "
                f"\"{_short(claim.get('text', ''), 180)}\""
            )
    else:
        lines.append("No sources were available.")
    lines.append("")
    lines.append("## Limitations / Unverified")
    if unverified:
        limitations.append(
            f"{len(unverified)} claim(s) are not fully supported and are labeled UNVERIFIED."
        )
    if not supported:
        limitations.append("No claim reached supported status.")
    if simulated:
        limitations.append(
            "This is simulated mock output produced without a remote language model."
        )
    if not limitations:
        limitations.append("No additional limitations were identified in mock mode.")
    for item in limitations:
        lines.append(f"- {item}")
    lines.append("")

    draft = "\n".join(lines)
    return WriterOutput(
        draft=draft,
        claims=claims,
        limitations=limitations,
    )


def _validate_draft(draft: str) -> None:
    if not draft.strip():
        raise ValidationError("Writer returned an empty draft.")
    lowered = draft.lower()
    for section in ("## summary", "## key findings", "## sources", "## limitations"):
        if section not in lowered:
            raise ValidationError(f"Writer draft is missing required section: {section}")
    if "<untrusted_document" in lowered:
        raise ValidationError("Writer leaked an untrusted-document delimiter.")


def run_report_writer(
    state: dict[str, Any],
    *,
    settings: Settings,
    llm: Any,
    db: Database,
    skills: dict[str, Skill],
) -> dict[str, Any]:
    task_id = state["task_id"]
    request = state.get("request", "")
    output_format = state.get("output_format", "markdown")
    plan = state.get("plan")
    claims = state.get("claims", [])
    evidence = state.get("evidence", [])
    revision_feedback = state.get("revision_feedback", "")

    payload = {
        "request": request,
        "output_format": output_format,
        "plan": plan,
        "verified_claims": claims,
        "evidence": evidence,
        "revision_feedback": revision_feedback,
    }
    system_prompt = SYSTEM_PROMPT + "\n\n" + render_agent_skills(
        "report_writer", skills
    )

    def validator(result: WriterOutput) -> None:
        _validate_draft(result.draft)

    try:
        result, retries = call_agent(
            agent="report_writer",
            schema=WriterOutput,
            system_prompt=system_prompt,
            payload=payload,
            mock_builder=lambda: build_mock_draft(
                request, output_format, plan, claims, settings.simulated, revision_feedback
            ),
            settings=settings,
            llm=llm,
            db=db,
            task_id=task_id,
            level=3,
            skill="report-writing",
            input_ref=f"claims={len(claims)}; revision={bool(revision_feedback)}",
            validator=validator,
        )
    except AgentFailure as failure:
        db.add_audit(task_id, "agent_failed", "agent:report_writer", "GR-07", str(failure))
        return {
            "status": "failed",
            "escalation_reason": str(failure),
            "last_team_result": {
                "agent": "report_writer",
                "status": "failed",
                "error_class": failure.error_class,
            },
            "agent_results": [
                failure_result(
                    agent="report_writer",
                    level=3,
                    skill="report-writing",
                    failure=failure,
                    simulated=settings.simulated,
                )
            ],
            "errors": [
                {
                    "agent": "report_writer",
                    "error_class": failure.error_class,
                    "message": str(failure),
                }
            ],
            "retry_counts": {"report_writer": failure.retries},
            "updated_at": utcnow_iso(),
        }

    for subtask in db.list_subtasks(task_id):
        if subtask["assigned_agent"] == "report_writer" and subtask["status"] != "completed":
            db.update_subtask_status(task_id, subtask["id"], "completed")

    db.add_audit(
        task_id,
        "agent_completed",
        "agent:report_writer",
        "GR-02",
        f"draft_chars={len(result.draft)}; claims={len(result.claims)}; retries={retries}",
    )
    return {
        "draft": result.draft,
        "claims": result.claims or claims,
        "phase": "assurance",
        "status": "in_progress",
        "last_team_result": {
            "agent": "report_writer",
            "status": "completed",
            "draft_chars": len(result.draft),
        },
        "subtask_status": {
            **dict(state.get("subtask_status") or {}),
            **{
                s["id"]: "completed"
                for s in db.list_subtasks(task_id)
                if s["assigned_agent"] == "report_writer"
            },
        },
        "agent_results": list(state.get("agent_results") or []) + [
            {
                "agent": "report_writer",
                "level": 3,
                "skill": "report-writing",
                "status": "completed",
                "summary": f"Drafted {len(result.draft)} characters.",
                "output": result.model_dump(mode="json"),
                "claims": result.claims or claims,
                "evidence": evidence,
                "missing_information": [],
                "uncertainty": result.limitations,
                "error_class": "",
                "retries": retries,
                "simulated": settings.simulated,
                "started_at": utcnow_iso(),
                "finished_at": utcnow_iso(),
            }
        ],
        "audit_events": [
            {
                "event_type": "agent_completed",
                "actor": "agent:report_writer",
                "rule_id": "GR-02",
                "detail": f"draft_chars={len(result.draft)}; claims={len(result.claims)}",
            }
        ],
        "updated_at": utcnow_iso(),
    }
