"""Automatic revision routing must match the plan that exists."""

from __future__ import annotations

from typing import Any

from aegisflow.graph.orchestrator import orchestrator_node


def _plan(*agents: str) -> dict[str, Any]:
    return {
        "task_type": "summary" if "report_writer" not in agents else "report",
        "subtasks": [
            {"id": f"st-{agent}", "assigned_agent": agent, "status": "completed"}
            for agent in agents
        ],
    }


def _state(task_id: str, plan: dict[str, Any], **overrides) -> dict[str, Any]:
    state: dict[str, Any] = {
        "task_id": task_id,
        "status": "in_progress",
        "plan": plan,
        "team_status": {
            "analysis": "completed",
            "drafting": "completed",
            "assurance": "needs_revision",
        },
        "draft": "## Summary\nA draft exists.",
        "draft_version": 1,
        "current_version_id": "version-1",
        "current_content_hash": "hash-1",
        "revision_count": 0,
        "max_revisions": 2,
        "policy_report": {"findings": [], "passed": True},
        "review_result": {"decision": "needs_revision", "issues": ["Add sources."]},
        "subtask_status": {
            item["id"]: "completed" for item in plan["subtasks"]
        },
        "retry_counts": {},
    }
    state.update(overrides)
    return state


def _run(env, state):
    return orchestrator_node(state, db=env.db, settings=env.settings)


def test_summary_revision_goes_back_to_analysis(env):
    """Regression: a summary has no writer, so drafting would produce nothing."""
    task = env.db.create_task("Summarise these notes.", "markdown", True)
    state = _state(task.id, _plan("document_analyst"))

    command = _run(env, state)

    assert command.goto == "analysis_team"
    assert command.update["revision_target"] == "analysis"
    assert command.update["revision_count"] == 1
    assert command.update["claims"] == []
    assert command.update["evidence"] == []
    assert command.update["analysis_summary"] == ""
    assert command.update["subtask_status"] == {"st-document_analyst": "pending"}
    assert command.update["team_status"]["analysis"] == "pending"


def test_writer_revision_goes_to_drafting(env):
    task = env.db.create_task("Write a report.", "markdown", True)
    plan = _plan("document_analyst", "evidence_verifier", "report_writer")
    state = _state(task.id, plan)

    command = _run(env, state)

    assert command.goto == "drafting_team"
    assert command.update["revision_target"] == "drafting"
    statuses = command.update["subtask_status"]
    assert statuses["st-report_writer"] == "pending"
    assert statuses["st-document_analyst"] == "completed"
    assert "claims" not in command.update


def test_revision_limit_escalates(env):
    task = env.db.create_task("Summarise these notes.", "markdown", True)
    state = _state(task.id, _plan("document_analyst"), revision_count=2)

    command = _run(env, state)

    assert command.goto == "escalate"
    assert command.update["status"] == "failed"


def test_blocked_reason_names_the_unchanged_version(env):
    task = env.db.create_task("Summarise these notes.", "markdown", True)
    state = _state(
        task.id,
        _plan("document_analyst"),
        draft="",
        team_status={"analysis": "completed", "assurance": "pending"},
    )

    command = _run(env, state)

    assert command.goto == "blocked"
    assert "version 1 is unchanged" in command.update["blocked_reason"]


def test_blocked_reason_when_no_version_ever_existed(env):
    task = env.db.create_task("Summarise these notes.", "markdown", True)
    state = _state(
        task.id,
        _plan("document_analyst"),
        draft="",
        draft_version=0,
        team_status={"analysis": "completed", "assurance": "pending"},
    )

    command = _run(env, state)

    assert command.goto == "blocked"
    assert command.update["blocked_reason"] == "No draft was produced."
