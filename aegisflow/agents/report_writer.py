"""Report Writer: formats verified claims into the requested deliverable."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import Field

from config import Settings

from ..agents.base import AgentFailure, call_agent, failure_result
from ..database import Database
from ..models import ClaimStatus, StrictModel, utcnow_iso
from ..skills_loader import Skill, render_agent_skills
from ..validation import ValidationError

SYSTEM_PROMPT = """You are the AegisFlow Report Writer.
You write for a busy manager who must approve or reject this draft.

Voice:
- Plain language, active voice, one idea per sentence, at most 25 words.
- Lead with the substance, never with a count or "This deliverable".
- Never write "the document states", "it is important to note", "in conclusion",
  or any commentary about being a report.
- Never invent facts, themes, owners, dates, amounts, or next steps.

Required structure:
# Title
**SIMULATED OUTPUT** (only when simulated)
**Source:** filename · page count (when known)
## Summary
## Key Findings
## What needs attention (only when the source states decisions, owners, dates, or amounts)
## Sources
## Limitations / Unverified

Summary: 2-4 sentences, substance first, every sentence cited with [S#].
Key Findings: 3-5 complete sentences; group under at most three short theme
headings when the source has clear themes; every item ends with [S#] or
[UNVERIFIED: reason].
What needs attention: decisions, owners, dates, and amounts the source states;
omit the section when there are none.
Sources: map each [S#] to filename and page or line.
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


_ATTENTION_RE = re.compile(
    r"(?i)\b(deadline|budget|owner|prepared by|approved|approval|decision|"
    r"must|required|due|20\d{2})\b"
)
_LABEL_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z /&-]{0,30}):\s*(?P<value>.+)$")


def _sentence(text: str) -> str:
    text = " ".join((text or "").split()).strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


def _doc_label(claims: list[dict[str, Any]]) -> str:
    for claim in claims:
        name = str(claim.get("source_ref") or "").split(" — ")[0].strip()
        if name:
            return Path(name).stem.replace("_", " ").replace("-", " ").strip()
    return ""


def _clean_claim(text: str, doc_label: str) -> str:
    sentence = _sentence(text)
    if doc_label and sentence.lower().startswith(doc_label.lower() + " "):
        remainder = sentence[len(doc_label) :].strip()
        if len(remainder) > 3:
            sentence = _sentence(remainder)
    return sentence


def _fact_sentence(text: str) -> str:
    match = _LABEL_RE.match(text)
    if not match:
        return text
    key = match.group("key").strip()
    value = match.group("value").strip().rstrip(".")
    lowered = key.lower()
    if lowered in {"prepared by", "author"}:
        return _sentence(f"Prepared by {value}")
    if lowered == "owner":
        return _sentence(f"{value} is the owner")
    if lowered == "deadline":
        return _sentence(f"The deadline is {value}")
    if lowered == "budget":
        return _sentence(f"The budget is {value}")
    if lowered == "requirement" and len(value.split()) > 3:
        return _sentence(value)
    if " " not in key:
        return _sentence(f"The {lowered} is {value}")
    return _sentence(f"{key} is {value}")


def _cited(sentence: str, claim_id: str) -> str:
    if not sentence:
        return ""
    return f"{sentence} [{claim_id}]"


def _source_meta(claims: list[dict[str, Any]]) -> str:
    names: list[str] = []
    pages: list[int] = []
    for claim in claims:
        ref = str(claim.get("source_ref") or "")
        if not ref:
            continue
        name, _, location = ref.partition(" — ")
        name = name.strip()
        if name and name not in names:
            names.append(name)
        match = re.search(r"page\s+(\d+)", location)
        if match:
            pages.append(int(match.group(1)))
    if not names:
        return ""
    meta = ", ".join(names[:2]) + ("…" if len(names) > 2 else "")
    if pages:
        low, high = min(pages), max(pages)
        if high == 1:
            meta += " · 1 page"
        elif low == high:
            meta += f" · page {high}"
        else:
            meta += f" · pages {low}–{high}"
    return meta


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
    doc_label = _doc_label(claims)
    source_meta = _source_meta(claims)

    lines: list[str] = [f"# {title}", ""]
    if simulated:
        lines.append(
            "**SIMULATED OUTPUT** — deterministic mock content; not real AI analysis."
        )
        lines.append("")
    if source_meta:
        lines.append(f"**Source:** {source_meta}")
        lines.append("")
    lines.append(f"**Request:** {request.strip()}")
    lines.append("")
    if revision_feedback.strip():
        lines.append(f"> Revision note: {revision_feedback.strip()}")
        lines.append("")
    lines.append("## Summary")
    summary_sentences: list[str] = []
    for claim in supported[:3]:
        text = _fact_sentence(_clean_claim(str(claim.get("text", "")), doc_label))
        if text:
            summary_sentences.append(_cited(text, str(claim.get("id", "S?"))))
    if summary_sentences:
        lines.append(" ".join(summary_sentences))
    else:
        lines.append(
            "Nothing in the source could be verified. The limitations section records "
            "the gap; no facts were invented."
        )
    lines.append("")
    lines.append("## Key Findings")
    if claims:
        for claim in claims:
            status = claim.get("status", "unverified")
            text = _fact_sentence(_clean_claim(str(claim.get("text", "")), doc_label))
            if status == ClaimStatus.SUPPORTED.value:
                lines.append(f"- {_cited(text, str(claim.get('id', 'S?')))}")
            else:
                lines.append(f"- {text} [UNVERIFIED: {status}]")
    else:
        lines.append("- No source claims were available. [UNVERIFIED: no claims extracted]")
    lines.append("")
    attention = []
    for claim in supported:
        text = _fact_sentence(_clean_claim(str(claim.get("text", "")), doc_label))
        if _ATTENTION_RE.search(text):
            attention.append(f"- {_cited(text, str(claim.get('id', 'S?')))}")
    if attention:
        lines.append("## What needs attention")
        lines.extend(attention)
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
