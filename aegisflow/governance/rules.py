"""Deterministic AI governance rules (GR-01 to GR-08)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GovernanceRule:
    id: str
    title: str
    purpose: str
    enforcement_point: str
    evidence: str
    owner: str


RULES: tuple[GovernanceRule, ...] = (
    GovernanceRule(
        id="GR-01",
        title="Human approval precedes finalization",
        purpose=(
            "No output may be finalized, exported as final, or marked completed "
            "without a human approval bound to the exact output version and hash."
        ),
        enforcement_point="human_review interrupt; approvals.py; finalize node re-check",
        evidence="human_reviews row + audit_log; TC-01, TC-02, TC-09, TC-10",
        owner="Human reviewer; system enforces",
    ),
    GovernanceRule(
        id="GR-02",
        title="No fabrication; source or unverified label",
        purpose=(
            "Every claim carries a source reference or an explicit UNVERIFIED label. "
            "Missing evidence is stated as a gap, never filled from model memory."
        ),
        enforcement_point="Writer prompt; Evidence Verifier; Policy Checker; Reviewer",
        evidence="claims/evidence tables; policy findings; TC-01, TC-06",
        owner="Report Writer; Evidence Verifier; Reviewer",
    ),
    GovernanceRule(
        id="GR-03",
        title="Uploaded content is untrusted data",
        purpose=(
            "Document text is delimited data, never instructions. Instruction-like "
            "content must not change permissions, reveal secrets, or bypass approval."
        ),
        enforcement_point="Ingestion scan; untrusted-content skill; tool allowlist; policy scan",
        evidence="injection findings; TC-06",
        owner="Document Analyst; all workers; Policy Checker",
    ),
    GovernanceRule(
        id="GR-04",
        title="Protect personal information and secrets",
        purpose=(
            "Redact secrets and PII from logs/audit records. Send documents to an "
            "external provider only when the user has configured and authorized it."
        ),
        enforcement_point="Redaction filter; startup config check; external LLM gate",
        evidence="audit_log sanitization; config warnings; TC-12",
        owner="System; user (authorization)",
    ),
    GovernanceRule(
        id="GR-05",
        title="Least privilege",
        purpose=(
            "Each agent receives only the state it needs and has no shell, email, "
            "calendar, financial, or external-action tools."
        ),
        enforcement_point="State slicing in wrappers; fixed tool allowlist (empty for v1)",
        evidence="agent input refs; architecture review; TC-12",
        owner="Orchestrator; system",
    ),
    GovernanceRule(
        id="GR-06",
        title="Auditable activity",
        purpose=(
            "Record routing decisions, agent executions, errors, escalations, "
            "output versions, and human decisions in an append-only audit trail."
        ),
        enforcement_point="audit_log writes from graph, agents, approvals",
        evidence="audit_log table; workflow view; TC-12",
        owner="System",
    ),
    GovernanceRule(
        id="GR-07",
        title="Bounded autonomy",
        purpose=(
            "Retry, revision, delegation-depth, and recursion limits are enforced. "
            "The system escalates instead of looping or guessing indefinitely."
        ),
        enforcement_point="Agent retry loop; orchestrator; graph recursion_limit",
        evidence="retry_counters; escalation reason; TC-05, TC-11",
        owner="Orchestrator; team leads",
    ),
    GovernanceRule(
        id="GR-08",
        title="Transparency",
        purpose=(
            "Simulated output is labeled in the UI and exports; uncertainty and "
            "reviewer findings are shown; mock results are never presented as real."
        ),
        enforcement_point="simulated flag; UI banner; draft header; export metadata",
        evidence="simulated columns; screenshot/doc; TC-07",
        owner="UI; Report Writer",
    ),
)

RULES_BY_ID: dict[str, GovernanceRule] = {rule.id: rule for rule in RULES}


def rule(rule_id: str) -> GovernanceRule:
    try:
        return RULES_BY_ID[rule_id]
    except KeyError as exc:
        raise KeyError(f"Unknown governance rule: {rule_id}") from exc
