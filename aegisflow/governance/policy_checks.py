"""Deterministic policy checks applied to a draft before human review."""

from __future__ import annotations

import re
from typing import Any

from ..models import ClaimStatus, Plan, PolicyFinding, PolicyReport
from ..redaction import find_secrets
from ..document_processing import scan_injection

_SECTION_ALIASES = {
    "summary": ("## summary", "# summary", "summary"),
    "findings": ("## key findings", "## findings", "key findings", "findings"),
    "sources": ("## sources", "## references", "sources", "references"),
    "limitations": (
        "## limitations",
        "## unverified",
        "limitations",
        "unverified",
    ),
}

_EXTERNAL_ACTION_PATTERNS = [
    r"(?i)\bi have (successfully )?(sent|emailed|submitted|published|scheduled|deleted|transferred)\b",
    r"(?i)\b(email|message|report) (was|has been) (successfully )?(sent|submitted|published)\b",
    r"(?i)\bsuccessfully (sent|submitted|published|scheduled)\b",
]

_CLAIM_LINE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)\s*$")
_REFERENCE = re.compile(r"\[(S\d+|UNVERIFIED[^\]]*)\]", re.IGNORECASE)


def _sections(draft: str) -> dict[str, str]:
    """Split a markdown-ish draft into lowercase heading -> body."""
    result: dict[str, str] = {}
    current = ""
    buffer: list[str] = []
    for line in draft.splitlines():
        heading = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if heading:
            if current:
                result[current] = "\n".join(buffer).strip()
            current = heading.group(1).strip().lower()
            buffer = []
        else:
            buffer.append(line)
    if current:
        result[current] = "\n".join(buffer).strip()
    return result


def _has_section(sections: dict[str, str], aliases: tuple[str, ...]) -> bool:
    for name in sections:
        if any(alias.lstrip("# ").lower() in name for alias in aliases):
            return True
    return False


def _claim_lines(draft: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    in_exempt = False
    for index, line in enumerate(draft.splitlines(), start=1):
        stripped = line.strip().lower()
        if (
            stripped.startswith("## sources")
            or stripped.startswith("## references")
            or stripped.startswith("## limitations")
            or stripped.startswith("## unverified")
        ):
            in_exempt = True
            continue
        if stripped.startswith("## ") and in_exempt:
            in_exempt = False
        if in_exempt:
            continue
        match = _CLAIM_LINE.match(line)
        if match and len(match.group(1)) > 12:
            lines.append((index, match.group(1)))
    return lines


def run_policy_checks(
    draft: str,
    plan: Plan | dict[str, Any] | None,
    claims: list[dict[str, Any]] | None,
    source_text: str = "",
    simulated: bool = True,
) -> PolicyReport:
    findings: list[PolicyFinding] = []
    checks: list[str] = []
    sections = _sections(draft)
    claims = claims or []

    # GR-02: required sections and claim references.
    checks.append("required_sections")
    for required in ("summary", "findings", "sources", "limitations"):
        if not _has_section(sections, _SECTION_ALIASES[required]):
            findings.append(
                PolicyFinding(
                    rule_id="GR-02",
                    severity="high",
                    message=f"Required section is missing: {required}.",
                    location="draft",
                )
            )

    checks.append("claim_references")
    claim_lines = _claim_lines(draft)
    if not claim_lines:
        findings.append(
            PolicyFinding(
                rule_id="GR-02",
                severity="warning",
                message="No claim lines were detected; groundedness cannot be measured.",
                location="draft",
            )
        )
    for line_number, text in claim_lines:
        if not _REFERENCE.search(text):
            findings.append(
                PolicyFinding(
                    rule_id="GR-02",
                    severity="high",
                    message="A claim line has no [S#] reference or [UNVERIFIED] label.",
                    location=f"line {line_number}",
                )
            )

    # GR-02: unsupported claims must be explicitly labeled.
    checks.append("claim_status")
    for claim in claims:
        status = str(claim.get("status", "unverified"))
        if status in {ClaimStatus.UNSUPPORTED.value, ClaimStatus.CONFLICTING.value}:
            text = str(claim.get("text", ""))
            if text and "[unverified" not in draft.lower() and "unverified" not in text.lower():
                findings.append(
                    PolicyFinding(
                        rule_id="GR-02",
                        severity="high",
                        message="An unsupported/conflicting claim is presented without an UNVERIFIED label.",
                        location="claims",
                    )
                )
                break

    # GR-03: no surviving instruction-like content or untrusted tags.
    checks.append("injection_leftovers")
    for injection in scan_injection(draft):
        findings.append(
            PolicyFinding(
                rule_id="GR-03",
                severity="high",
                message="Instruction-like text from untrusted content appears in the draft.",
                location=f"line {injection.line}",
            )
        )
    if "<untrusted_document" in draft.lower():
        findings.append(
            PolicyFinding(
                rule_id="GR-03",
                severity="high",
                message="Raw untrusted-document delimiter leaked into the draft.",
                location="draft",
            )
        )

    # GR-04: secrets must never be echoed; source PII is a warning for the human.
    checks.append("secret_scan")
    for label in find_secrets(draft):
        findings.append(
            PolicyFinding(
                rule_id="GR-04",
                severity="high",
                message=f"Secret-like value detected in the draft ({label}).",
                location="draft",
            )
        )
    checks.append("source_pii_scan")
    email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    draft_emails = set(email_pattern.findall(draft))
    source_emails = set(email_pattern.findall(source_text or ""))
    new_emails = draft_emails - source_emails
    if new_emails:
        findings.append(
            PolicyFinding(
                rule_id="GR-04",
                severity="high",
                message="The draft contains an email address that does not appear in the source.",
                location="draft",
            )
        )
    elif draft_emails:
        findings.append(
            PolicyFinding(
                rule_id="GR-04",
                severity="warning",
                message="The draft contains source-provided contact information; review before sharing.",
                location="draft",
            )
        )

    # GR-02 / Writer constraint: never claim an external action occurred.
    checks.append("external_action_claims")
    for pattern in _EXTERNAL_ACTION_PATTERNS:
        if re.search(pattern, draft):
            findings.append(
                PolicyFinding(
                    rule_id="GR-02",
                    severity="high",
                    message="The draft claims an external action was performed.",
                    location="draft",
                )
            )
            break

    # GR-08: simulated output must be labeled.
    checks.append("simulated_label")
    if simulated and "simulated" not in draft.lower():
        findings.append(
            PolicyFinding(
                rule_id="GR-08",
                severity="warning",
                message="Simulated output is missing the SIMULATED label in the draft.",
                location="draft",
            )
        )

    # Plan consistency (non-blocking unless a required section is absent).
    checks.append("plan_consistency")
    if plan is not None:
        plan_obj = plan if isinstance(plan, Plan) else Plan.model_validate(plan)
        if plan_obj.missing_information and not _has_section(
            sections, _SECTION_ALIASES["limitations"]
        ):
            findings.append(
                PolicyFinding(
                    rule_id="GR-02",
                    severity="high",
                    message="The plan has missing information but the draft has no limitations section.",
                    location="draft",
                )
            )

    passed = not any(f.severity == "high" for f in findings)
    return PolicyReport(passed=passed, findings=findings, checks_run=checks)


def policy_summary(report: PolicyReport) -> str:
    if report.passed:
        return f"Policy checks passed ({len(report.checks_run)} checks)."
    high = sum(1 for f in report.findings if f.severity == "high")
    return f"Policy checks failed: {high} high-severity finding(s)."
