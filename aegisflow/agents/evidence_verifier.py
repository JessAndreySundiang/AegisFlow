"""Evidence Verifier: checks claims against supplied source passages only."""

from __future__ import annotations

import re
from typing import Any

from config import Settings

from ..agents.base import AgentFailure, call_agent, failure_result
from ..database import Database
from ..document_processing import build_untrusted_block
from ..models import Claim, ClaimStatus, VerificationResult, utcnow_iso
from ..skills_loader import Skill, render_agent_skills
from ..validation import ValidationError

SYSTEM_PROMPT = """You are the AegisFlow Evidence Verifier.
Check every claim against the supplied source passages only. Never verify from
model memory. Never imply that an external search happened.

Statuses:
- supported: the passage entails the claim.
- unsupported: the passage does not support the claim.
- conflicting: sources disagree or the passage contradicts the claim.
- unverified: no usable passage exists.

Every supported/conflicting decision must cite the filename and location.
Return JSON only.
"""

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text or "").strip().lower()


def _filename_from_ref(ref: str) -> str:
    if " — " in ref:
        return ref.split(" — ")[0].strip()
    return ref.strip()


def build_mock_verification(
    claims: list[dict[str, Any]], documents: dict[str, dict[str, Any]]
) -> VerificationResult:
    by_filename = {
        str(doc.get("filename", "")).lower(): doc for doc in documents.values()
    }
    verified: list[Claim] = []
    notes: list[str] = []
    uncertainty: list[str] = []

    for raw in claims:
        claim = Claim.model_validate(raw)
        filename = _filename_from_ref(claim.source_ref)
        doc = by_filename.get(filename.lower())
        if doc is None or doc.get("status") != "ok":
            claim.status = ClaimStatus.UNVERIFIED
            claim.rationale = "The cited file is missing or unreadable."
            verified.append(claim)
            continue
        passage = _normalize(doc.get("text", ""))
        needle = _normalize(claim.text)
        if needle and needle in passage:
            claim.status = ClaimStatus.SUPPORTED
            claim.rationale = f"Exact claim text found in {claim.source_ref}."
        else:
            claim.status = ClaimStatus.UNVERIFIED
            claim.rationale = (
                "No exact matching passage was found. The verifier does not use memory."
            )
        verified.append(claim)

    supported = sum(1 for c in verified if c.status == ClaimStatus.SUPPORTED)
    notes.append(
        f"Verified {len(verified)} claim(s): {supported} supported, "
        f"{len(verified) - supported} unverified/unsupported."
    )
    if supported < len(verified):
        uncertainty.append(
            "Some claims could not be matched to an exact source passage; they remain unverified."
        )
    notes.append("Mock verification uses exact normalized substring matching only.")
    return VerificationResult(claims=verified, notes=notes, uncertainty=uncertainty)


def run_evidence_verifier(
    state: dict[str, Any],
    *,
    settings: Settings,
    llm: Any,
    db: Database,
    skills: dict[str, Skill],
) -> dict[str, Any]:
    task_id = state["task_id"]
    claims = state.get("claims", [])
    documents = state.get("documents", {})

    payload = {
        "claims": claims,
        "source_passages": [
            {
                "filename": doc.get("filename"),
                "status": doc.get("status"),
                "untrusted_text": build_untrusted_block(
                    doc.get("filename", "document"), doc.get("text", "")
                ),
            }
            for doc in documents.values()
        ],
        "external_search_configured": False,
    }
    system_prompt = SYSTEM_PROMPT + "\n\n" + render_agent_skills(
        "evidence_verifier", skills
    )

    def validator(result: VerificationResult) -> None:
        for claim in result.claims:
            if claim.status in {ClaimStatus.SUPPORTED, ClaimStatus.CONFLICTING}:
                if not claim.source_ref.strip() or not claim.rationale.strip():
                    raise ValidationError(
                        f"Claim {claim.id} was marked {claim.status.value} without a cited rationale."
                    )

    try:
        result, retries = call_agent(
            agent="evidence_verifier",
            schema=VerificationResult,
            system_prompt=system_prompt,
            payload=payload,
            mock_builder=lambda: build_mock_verification(claims, documents),
            settings=settings,
            llm=llm,
            db=db,
            task_id=task_id,
            level=3,
            skill="evidence-verification",
            input_ref=f"claims={len(claims)}; documents={len(documents)}",
            validator=validator,
        )
    except AgentFailure as failure:
        db.add_audit(task_id, "agent_failed", "agent:evidence_verifier", "GR-07", str(failure))
        return {
            "status": "failed",
            "escalation_reason": str(failure),
            "last_team_result": {
                "agent": "evidence_verifier",
                "status": "failed",
                "error_class": failure.error_class,
            },
            "agent_results": [
                failure_result(
                    agent="evidence_verifier",
                    level=3,
                    skill="evidence-verification",
                    failure=failure,
                    simulated=settings.simulated,
                )
            ],
            "errors": [
                {
                    "agent": "evidence_verifier",
                    "error_class": failure.error_class,
                    "message": str(failure),
                }
            ],
            "retry_counts": {"evidence_verifier": failure.retries},
            "updated_at": utcnow_iso(),
        }

    verified_claims = [claim.model_dump(mode="json") for claim in result.claims]
    evidence = []
    for claim in result.claims:
        filename = _filename_from_ref(claim.source_ref)
        location = claim.source_ref.split(" — ")[-1] if " — " in claim.source_ref else "document"
        evidence.append(
            {
                "id": claim.id,
                "file_id": "",
                "filename": filename,
                "location": location,
                "excerpt": claim.text[:500],
                "status": claim.status.value,
                "rationale": claim.rationale,
            }
        )
    for subtask in db.list_subtasks(task_id):
        if subtask["assigned_agent"] == "evidence_verifier" and subtask["status"] != "completed":
            db.update_subtask_status(task_id, subtask["id"], "completed")

    db.add_audit(
        task_id,
        "agent_completed",
        "agent:evidence_verifier",
        "GR-02",
        f"claims={len(verified_claims)}; retries={retries}",
    )
    return {
        "claims": verified_claims,
        "evidence": evidence,
        "phase": "drafting",
        "status": "in_progress",
        "last_team_result": {
            "agent": "evidence_verifier",
            "status": "completed",
            "claims": len(verified_claims),
        },
        "subtask_status": {
            **dict(state.get("subtask_status") or {}),
            **{
                s["id"]: "completed"
                for s in db.list_subtasks(task_id)
                if s["assigned_agent"] == "evidence_verifier"
            },
        },
        "agent_results": list(state.get("agent_results") or []) + [
            {
                "agent": "evidence_verifier",
                "level": 3,
                "skill": "evidence-verification",
                "status": "completed",
                "summary": result.notes[0] if result.notes else "Claims checked.",
                "output": result.model_dump(mode="json"),
                "claims": verified_claims,
                "evidence": evidence,
                "missing_information": [],
                "uncertainty": result.uncertainty,
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
                "actor": "agent:evidence_verifier",
                "rule_id": "GR-02",
                "detail": f"claims={len(verified_claims)}; retries={retries}",
            }
        ],
        "updated_at": utcnow_iso(),
    }
