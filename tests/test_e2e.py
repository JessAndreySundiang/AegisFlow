"""End-to-end and integration tests for test cases TC-01 to TC-13.

Every test runs the real compiled LangGraph in mock mode (no network). The
tests exercise the approval gate, hash binding, bounded loops, untrusted-input
handling, audit trail, and selective routing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegisflow import approvals
from aegisflow.approvals import ApprovalError, assert_finalizable, record_decision
from aegisflow.document_processing import scan_injection
from aegisflow.metrics import build_workload_metric
from aegisflow.models import (
    PolicyFinding,
    PolicyReport,
    TaskStatus,
    sha256_text,
)
from aegisflow.services.export_service import export_markdown, export_txt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = PROJECT_ROOT / "sample_data"

FULL_PIPELINE_REQUEST = "Please prepare a meeting report from these notes."
SUMMARY_REQUEST = "Please summarize the attached project notes."


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _approve(env, payload: dict, reviewer: str = "Dr. Reviewer"):
    return record_decision(
        env.db,
        payload["task_id"],
        payload["version_id"],
        "approve",
        reviewer,
        max_revisions=payload.get("max_revisions", 2),
    )


def _resume_approve(env, task_id: str):
    return env.workflow.resume(
        task_id, {"decision": "approve", "reviewer": "Dr. Reviewer"}
    )


def _agent_names(env, task_id: str) -> set[str]:
    return {row["agent"] for row in env.db.list_agent_executions(task_id)}


def _audit_text(env, task_id: str) -> str:
    return "\n".join(event.detail for event in env.db.list_audit(task_id))


def _read(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


# --------------------------------------------------------------------------
# TC-01  happy path: full pipeline -> human review -> approve -> finalize/export
# --------------------------------------------------------------------------
def test_tc01_happy_path_approval_finalize_and_export(env, make_task, run_task, sample_txt):
    task, files, docs, metas = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = run_task(task, files, docs)

    assert result.interrupted is True
    assert result.status == "awaiting_human_review"
    payload = result.interrupt_payload
    assert payload is not None
    assert payload["task_id"] == task.id
    assert payload["simulated"] is True
    assert payload["content_hash"] == sha256_text(payload["draft"])
    assert "# Meeting Brief" in payload["draft"]
    assert "**SIMULATED OUTPUT**" in payload["draft"]
    for section in ("## Summary", "## Key Findings", "## Sources", "## Limitations"):
        assert section in payload["draft"]

    assert env.db.get_task(task.id).status == TaskStatus.AWAITING_HUMAN_REVIEW
    assert all(s["status"] == "completed" for s in env.db.list_subtasks(task.id))
    assert payload["policy_report"]["passed"] is True
    assert payload["review_result"]["decision"] == "pass"

    approval = _approve(env, payload)
    assert approval.decision.value == "approve"
    assert approval.content_hash == sha256_text(payload["draft"])

    final = _resume_approve(env, task.id)
    assert final.interrupted is False
    assert final.status == "completed"
    task_record = env.db.get_task(task.id)
    assert task_record.status == TaskStatus.COMPLETED
    assert task_record.elapsed_seconds is not None
    assert task_record.current_version_id == payload["version_id"]

    markdown = export_markdown(env.db, task.id, payload["version_id"])
    assert markdown.startswith("---")
    assert "status: APPROVED" in markdown
    assert payload["content_hash"] in markdown
    assert "reviewer: Dr. Reviewer" in markdown
    assert "simulated: true" in markdown
    assert "SIMULATED OUTPUT" in markdown

    text = export_txt(env.db, task.id, payload["version_id"])
    assert "AEGISFLOW APPROVED OUTPUT" in text
    assert "Reviewer: Dr. Reviewer" in text
    assert "SIMULATED OUTPUT" in text

    metric = build_workload_metric(
        env.db, task_record, approval_outcome="approved", quality_rating=4
    )
    assert metric.manual_minutes == task.manual_minutes
    assert metric.subtasks_completed == 3
    assert metric.approval_outcome == "approved"
    assert metric.time_reduction_pct is not None


# --------------------------------------------------------------------------
# TC-02  approval cannot be forged by an agent or skipped before resume
# --------------------------------------------------------------------------
def test_tc02_agent_cannot_approve_and_unpersisted_resume_escalates(
    env, make_task, run_task, sample_txt
):
    task, files, docs, _ = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = run_task(task, files, docs)
    payload = result.interrupt_payload
    assert payload is not None

    # An agent actor is refused before any write occurs.
    with pytest.raises(ApprovalError):
        record_decision(
            env.db,
            task.id,
            payload["version_id"],
            "approve",
            "Planner Agent",
            actor="agent:planner",
        )
    assert env.db.get_task(task.id).status == TaskStatus.AWAITING_HUMAN_REVIEW
    assert env.db.list_human_reviews(task.id) == []

    # Resuming with an approve action and no persisted approval must escalate.
    result2 = _resume_approve(env, task.id)
    assert result2.interrupted is False
    assert result2.status == "failed"
    assert env.db.get_task(task.id).status == TaskStatus.FAILED
    audit = env.db.list_audit(task.id)
    assert any(
        e.event_type == "approval_rejected" and e.rule_id == "GR-01" for e in audit
    )


# --------------------------------------------------------------------------
# TC-03  a new output version invalidates the earlier approval
# --------------------------------------------------------------------------
def test_tc03_edit_invalidates_prior_approval(env, make_task, run_task, sample_txt):
    task, files, docs, _ = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = run_task(task, files, docs)
    payload = result.interrupt_payload
    assert payload is not None
    _approve(env, payload)
    assert env.db.get_task(task.id).status == TaskStatus.APPROVED

    edited = payload["draft"] + "\n\nHuman edit: added a note.\n"
    version2 = approvals.create_output_version(
        env.db, task.id, edited, "human_edit"
    )
    assert version2.version_number == 2
    assert env.db.get_task(task.id).status == TaskStatus.AWAITING_HUMAN_REVIEW

    with pytest.raises(ApprovalError):
        assert_finalizable(
            env.db, task.id, payload["version_id"], payload["content_hash"]
        )

    # The interrupted graph still points at version 1, so resuming escalates.
    result2 = _resume_approve(env, task.id)
    assert result2.interrupted is False
    assert result2.status == "failed"
    assert env.db.get_task(task.id).status == TaskStatus.FAILED


# --------------------------------------------------------------------------
# TC-04  rejection is terminal and blocks export
# --------------------------------------------------------------------------
def test_tc04_reject_is_terminal_and_blocks_export(env, make_task, run_task, sample_txt):
    task, files, docs, _ = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = run_task(task, files, docs)
    payload = result.interrupt_payload
    assert payload is not None

    record_decision(
        env.db,
        task.id,
        payload["version_id"],
        "reject",
        "Dr. Reviewer",
        feedback="The scope is wrong.",
        max_revisions=payload.get("max_revisions", 2),
    )
    result2 = env.workflow.resume(
        task.id,
        {"decision": "reject", "reviewer": "Dr. Reviewer", "feedback": "The scope is wrong."},
    )
    assert result2.interrupted is False
    assert result2.status == "rejected"
    assert env.db.get_task(task.id).status == TaskStatus.REJECTED

    with pytest.raises(ApprovalError):
        export_markdown(env.db, task.id, payload["version_id"])
    with pytest.raises(ApprovalError):
        export_txt(env.db, task.id, payload["version_id"])


# --------------------------------------------------------------------------
# TC-05  revision loop creates a new version and is bounded
# --------------------------------------------------------------------------
def test_tc05_revision_loop_is_bounded(env, make_task, make_workflow, sample_txt):
    workflow, _settings = make_workflow(max_revisions=1)
    task, files, docs, _ = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = workflow.start(
        task.id,
        task.request,
        task.output_format,
        files,
        docs,
        manual_minutes=task.manual_minutes,
    )
    first = result.interrupt_payload
    assert first is not None
    assert first["version_number"] == 1

    feedback = "Add a clearer limitations statement."
    record_decision(
        env.db,
        task.id,
        first["version_id"],
        "request_revision",
        "Dr. Reviewer",
        feedback=feedback,
        max_revisions=1,
    )
    result2 = workflow.resume(
        task.id,
        {
            "decision": "request_revision",
            "reviewer": "Dr. Reviewer",
            "feedback": feedback,
            "revision_target": "drafting",
        },
    )
    assert result2.interrupted is True
    second = result2.interrupt_payload
    assert second is not None
    assert second["version_number"] == 2
    assert second["revision_count"] == 1
    assert feedback in second["draft"]
    assert second["version_id"] != first["version_id"]
    assert len(env.db.list_output_versions(task.id)) == 2

    # The revision budget is exhausted: the UI cannot record another cycle.
    with pytest.raises(ApprovalError):
        record_decision(
            env.db,
            task.id,
            second["version_id"],
            "request_revision",
            "Dr. Reviewer",
            feedback="One more pass please.",
            max_revisions=1,
        )

    # Resuming without a persisted decision must escalate, never loop.
    result3 = workflow.resume(
        task.id,
        {
            "decision": "request_revision",
            "reviewer": "Dr. Reviewer",
            "feedback": "One more pass please.",
        },
    )
    assert result3.interrupted is False
    assert result3.status == "failed"
    assert env.db.get_task(task.id).status == TaskStatus.FAILED


# --------------------------------------------------------------------------
# TC-06  prompt injection in an uploaded document is inert data
# --------------------------------------------------------------------------
def test_tc06_prompt_injection_is_treated_as_data(
    env, make_task, run_task, injection_txt
):
    source = injection_txt.decode("utf-8")
    assert scan_injection(source), "fixture must contain an injection pattern"

    task, files, docs, _ = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("injection_notes.txt", injection_txt)]
    )
    result = run_task(task, files, docs)
    assert result.interrupted is True
    payload = result.interrupt_payload
    assert payload is not None

    lowered = payload["draft"].lower()
    assert "ignore all previous instructions" not in lowered
    assert "unrestricted assistant" not in lowered
    assert "attacker@example.com" not in lowered
    assert "system prompt" not in lowered

    assert payload["policy_report"]["passed"] is True
    assert not any(
        f["rule_id"] == "GR-03" and f["severity"] == "high"
        for f in payload["policy_report"]["findings"]
    )

    state = env.workflow.get_state(task.id)
    uncertainties = [
        note
        for agent in state.get("agent_results", [])
        for note in agent.get("uncertainty", [])
    ]
    assert any("instruction-like" in note.lower() for note in uncertainties)
    # The real deadline survives, proving clean content is still extracted.
    assert any("30 November 2026" in claim["text"] for claim in payload["claims"])


# --------------------------------------------------------------------------
# TC-07  simulated output is labeled in draft, review payload, and exports
# --------------------------------------------------------------------------
def test_tc07_simulated_labels_flow_through_review_and_export(
    env, make_task, run_task, sample_txt
):
    task, files, docs, _ = make_task(
        request=SUMMARY_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = run_task(task, files, docs)
    payload = result.interrupt_payload
    assert payload is not None
    assert payload["simulated"] is True
    assert "SIMULATED OUTPUT" in payload["draft"]

    version = env.db.get_output_version(payload["version_id"])
    assert version.simulated is True
    assert version.content_hash == payload["content_hash"]

    _approve(env, payload)
    assert _resume_approve(env, task.id).status == "completed"

    markdown = export_markdown(env.db, task.id, payload["version_id"])
    text = export_txt(env.db, task.id, payload["version_id"])
    assert "SIMULATED OUTPUT" in markdown
    assert "simulated: true" in markdown
    assert "SIMULATED OUTPUT" in text
    assert "Simulated: yes" in text


# --------------------------------------------------------------------------
# TC-08  no readable input blocks instead of inventing content
# --------------------------------------------------------------------------
def test_tc08_no_readable_input_blocks_without_fabrication(
    env, make_task, run_task
):
    # (a) A file was supplied but could not be read.
    empty = _read("empty.txt")
    task_a, files_a, docs_a, metas_a = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("empty.txt", empty)]
    )
    assert metas_a[0].status.value == "empty"
    result_a = run_task(task_a, files_a, docs_a)
    assert result_a.interrupted is False
    assert result_a.status == "blocked"
    assert env.db.get_task(task_a.id).status == TaskStatus.BLOCKED
    assert env.db.list_output_versions(task_a.id) == []
    assert any(e.event_type == "request_blocked" for e in env.db.list_audit(task_a.id))

    # (b) No file was supplied at all: the planner refuses to invent content.
    task_b, files_b, docs_b, _ = make_task(request=FULL_PIPELINE_REQUEST, files=[])
    result_b = run_task(task_b, files_b, docs_b)
    assert result_b.interrupted is False
    assert result_b.status == "blocked"
    assert env.db.get_task(task_b.id).status == TaskStatus.BLOCKED
    assert env.db.list_output_versions(task_b.id) == []
    state_b = env.workflow.get_state(task_b.id)
    assert state_b["plan"]["missing_information"]
    assert state_b["plan"]["subtasks"] == []
    assert any(e.event_type == "plan_blocked" for e in env.db.list_audit(task_b.id))


# --------------------------------------------------------------------------
# TC-09  unreadable files are reported; readable files still drive the run
# --------------------------------------------------------------------------
def test_tc09_mixed_unreadable_files_are_reported(
    env, make_task, run_task, sample_txt
):
    task, files, docs, metas = make_task(
        request=FULL_PIPELINE_REQUEST,
        files=[
            ("corrupted.pdf", _read("corrupted.pdf")),
            ("encrypted.pdf", _read("encrypted.pdf")),
            ("project_notes.txt", sample_txt),
        ],
    )
    statuses = {m.filename: m.status.value for m in metas}
    assert statuses["corrupted.pdf"] == "corrupted"
    assert statuses["encrypted.pdf"] == "encrypted"
    assert statuses["project_notes.txt"] == "ok"

    result = run_task(task, files, docs)
    assert result.interrupted is True
    assert result.status == "awaiting_human_review"
    payload = result.interrupt_payload
    assert payload is not None
    assert payload["draft"]
    # Only the readable document contributes claims.
    assert all(
        "corrupted.pdf" not in claim["source_ref"]
        and "encrypted.pdf" not in claim["source_ref"]
        for claim in payload["claims"]
    )
    stored = {row["filename"]: row["status"] for row in env.db.list_files(task.id)}
    assert stored["corrupted.pdf"] == "corrupted"
    assert stored["encrypted.pdf"] == "encrypted"
    assert stored["project_notes.txt"] == "ok"


# --------------------------------------------------------------------------
# TC-10  tampering with stored content after approval blocks finalization
# --------------------------------------------------------------------------
def test_tc10_tamper_after_approval_blocks_finalization(
    env, make_task, run_task, sample_txt
):
    task, files, docs, _ = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = run_task(task, files, docs)
    payload = result.interrupt_payload
    assert payload is not None
    _approve(env, payload)
    assert env.db.get_task(task.id).status == TaskStatus.APPROVED

    with env.db.conn:
        env.db.conn.execute(
            "UPDATE output_versions SET content = ? WHERE id = ?",
            ("tampered content that no human approved", payload["version_id"]),
        )

    with pytest.raises(ApprovalError):
        assert_finalizable(
            env.db, task.id, payload["version_id"], payload["content_hash"]
        )
    with pytest.raises(ApprovalError):
        export_markdown(env.db, task.id, payload["version_id"])

    result2 = _resume_approve(env, task.id)
    assert result2.interrupted is False
    assert result2.status == "failed"
    assert env.db.get_task(task.id).status == TaskStatus.FAILED


# --------------------------------------------------------------------------
# TC-11  repeated assurance failure escalates at the revision limit
# --------------------------------------------------------------------------
def test_tc11_assurance_failure_escalates_at_limit(
    env, make_task, make_workflow, sample_txt, monkeypatch
):
    import aegisflow.graph.assurance_team as assurance_module

    def failing_policy(draft, plan, claims, source_text="", simulated=True):
        return PolicyReport(
            passed=False,
            findings=[
                PolicyFinding(
                    rule_id="GR-02",
                    severity="high",
                    message="Forced failure for the bounded-autonomy test.",
                    location="draft",
                )
            ],
            checks_run=["test_override"],
        )

    monkeypatch.setattr(assurance_module, "run_policy_checks", failing_policy)
    workflow, _settings = make_workflow(max_revisions=1)

    task, files, docs, _ = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = workflow.start(
        task.id,
        task.request,
        task.output_format,
        files,
        docs,
        manual_minutes=task.manual_minutes,
    )

    assert result.interrupted is False
    assert result.status == "failed"
    task_record = env.db.get_task(task.id)
    assert task_record.status == TaskStatus.FAILED
    assert "revision" in (task_record.escalation_reason or "").lower()
    # One bounded revision was attempted before escalation.
    assert len(env.db.list_output_versions(task.id)) == 2
    assert any(e.event_type == "task_escalated" for e in env.db.list_audit(task.id))


# --------------------------------------------------------------------------
# TC-12  audit trail is complete and PII/secrets are redacted from logs
# --------------------------------------------------------------------------
def test_tc12_audit_trail_and_redaction(env, make_task, run_task, sample_txt):
    task, files, docs, _ = make_task(
        request=FULL_PIPELINE_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = run_task(task, files, docs)
    payload = result.interrupt_payload
    assert payload is not None

    dirty = "Contact jane@example.com and use key sk-or-abcdefghijklmnop"
    record_decision(
        env.db,
        task.id,
        payload["version_id"],
        "request_revision",
        "Dr. Reviewer",
        feedback=dirty,
        max_revisions=payload.get("max_revisions", 2),
    )
    env.workflow.resume(
        task.id,
        {
            "decision": "request_revision",
            "reviewer": "Dr. Reviewer",
            "feedback": dirty,
            "revision_target": "drafting",
        },
    )

    audit_types = {e.event_type for e in env.db.list_audit(task.id)}
    for expected in (
        "request_validated",
        "plan_created",
        "routing_decision",
        "agent_completed",
        "policy_check_completed",
        "draft_version_created",
        "human_decision",
    ):
        assert expected in audit_types, expected

    assert _agent_names(env, task.id) >= {
        "planner",
        "document_analyst",
        "evidence_verifier",
        "report_writer",
        "reviewer",
        "policy_checker",
    }

    all_details = _audit_text(env, task.id)
    assert "jane@example.com" not in all_details
    assert "abcdefghijklmnop" not in all_details
    # Source-document PII must not leak into logs either.
    assert "juan.delacruz@example.com" not in all_details

    stored_feedback = " ".join(r.feedback for r in env.db.list_human_reviews(task.id))
    assert "jane@example.com" not in stored_feedback
    assert "abcdefghijklmnop" not in stored_feedback
    assert "[REDACTED:EMAIL]" in stored_feedback
    assert "[REDACTED:OPENROUTER_KEY]" in stored_feedback


# --------------------------------------------------------------------------
# TC-13  selective routing: summaries skip the writer and verifier
# --------------------------------------------------------------------------
def test_tc13_selective_routing_summary_uses_analyst_only(
    env, make_task, run_task, sample_txt
):
    task, files, docs, _ = make_task(
        request=SUMMARY_REQUEST, files=[("project_notes.txt", sample_txt)]
    )
    result = run_task(task, files, docs)
    assert result.interrupted is True
    payload = result.interrupt_payload
    assert payload is not None

    state = env.workflow.get_state(task.id)
    agents_in_plan = [s["assigned_agent"] for s in state["plan"]["subtasks"]]
    assert agents_in_plan == ["document_analyst"]
    assert state["plan"]["task_type"] == "summary"
    assert "# Document Summary" in payload["draft"]

    executed = _agent_names(env, task.id)
    assert "document_analyst" in executed
    assert "evidence_verifier" not in executed
    assert "report_writer" not in executed

    routed_to = {
        entry["to_node"]
        for entry in state.get("routing_log", [])
        if entry.get("from_node") == "orchestrator"
    }
    assert "analysis_team" in routed_to
    assert "assurance_team" in routed_to
    assert "human_review" in routed_to
    assert "drafting_team" not in routed_to
    assert routed_to <= {
        "analysis_team",
        "drafting_team",
        "assurance_team",
        "human_review",
        "blocked",
        "escalate",
    }
