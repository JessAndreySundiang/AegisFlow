import pytest

from aegisflow.approvals import (
    ApprovalError,
    assert_finalizable,
    create_output_version,
    record_decision,
)
from aegisflow.models import HumanDecision, TaskStatus


def _ready_task(env, content="g" * 10 + " approved draft"):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    env.db.transition_task(task.id, "planning")
    env.db.transition_task(task.id, "in_progress")
    version = env.db.add_output_version(task.id, content, "agent")
    env.db.transition_task(task.id, "awaiting_human_review")
    return task, version


def test_approve_and_finalize(env):
    task, version = _ready_task(env)
    record = record_decision(
        env.db, task.id, version.id, "approve", "Reviewer", max_revisions=2
    )
    assert record.decision == HumanDecision.APPROVE
    assert env.db.get_task(task.id).status == TaskStatus.APPROVED
    approved = assert_finalizable(env.db, task.id, version.id, version.content_hash)
    assert approved.reviewer == "Reviewer"


def test_agent_actor_cannot_approve(env):
    task, version = _ready_task(env)
    with pytest.raises(ApprovalError):
        record_decision(
            env.db,
            task.id,
            version.id,
            "approve",
            "Agent",
            actor="agent:planner",
            max_revisions=2,
        )


def test_duplicate_approval_rejected(env):
    task, version = _ready_task(env)
    record_decision(env.db, task.id, version.id, "approve", "R", max_revisions=2)
    with pytest.raises(ApprovalError):
        record_decision(env.db, task.id, version.id, "approve", "R", max_revisions=2)


def test_stale_version_rejected(env):
    task, version = _ready_task(env)
    newer = create_output_version(env.db, task.id, "newer content " + "x" * 20, "human_edit")
    with pytest.raises(ApprovalError):
        record_decision(env.db, task.id, version.id, "approve", "R", max_revisions=2)
    with pytest.raises(ApprovalError):
        assert_finalizable(env.db, task.id, version.id, version.content_hash)
    assert newer.version_number == 2


def test_hash_mismatch_rejected(env):
    task, version = _ready_task(env)
    record_decision(env.db, task.id, version.id, "approve", "R", max_revisions=2)
    with pytest.raises(ApprovalError):
        assert_finalizable(env.db, task.id, version.id, "0" * 64)


def test_stored_content_tamper_rejected(env):
    task, version = _ready_task(env)
    record_decision(env.db, task.id, version.id, "approve", "R", max_revisions=2)
    with env.db.conn:
        env.db.conn.execute(
            "UPDATE output_versions SET content = ? WHERE id = ?",
            ("tampered", version.id),
        )
    with pytest.raises(ApprovalError):
        assert_finalizable(env.db, task.id, version.id, version.content_hash)


def test_reject_is_terminal(env):
    task, version = _ready_task(env)
    record_decision(env.db, task.id, version.id, "reject", "R", max_revisions=2)
    assert env.db.get_task(task.id).status == TaskStatus.REJECTED
    with pytest.raises(ApprovalError):
        assert_finalizable(env.db, task.id, version.id, version.content_hash)


def test_revision_requires_feedback_and_reaches_limit(env):
    task, version = _ready_task(env)
    with pytest.raises(ApprovalError):
        record_decision(
            env.db, task.id, version.id, "request_revision", "R", max_revisions=2
        )
    record_decision(
        env.db,
        task.id,
        version.id,
        "request_revision",
        "R",
        feedback="Fix the summary.",
        max_revisions=1,
    )
    assert env.db.get_task(task.id).status == TaskStatus.REVISION_REQUESTED
