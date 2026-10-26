"""Concurrency and database backstop for the human approval gate."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from aegisflow.approvals import ApprovalError, record_decision
from aegisflow.models import HumanDecision, TaskStatus


def _ready_task(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    env.db.transition_task(task.id, "planning")
    env.db.transition_task(task.id, "in_progress")
    version = env.db.add_output_version(
        task.id, "approved draft content for the race test", "agent"
    )
    env.db.transition_task(task.id, "awaiting_human_review")
    return task, version


def test_concurrent_approvals_record_exactly_one(env):
    task, version = _ready_task(env)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def attempt(reviewer: str) -> None:
        barrier.wait(timeout=5)
        try:
            record_decision(
                env.db, task.id, version.id, "approve", reviewer, max_revisions=2
            )
            outcomes.append("approved")
        except ApprovalError:
            outcomes.append("refused")

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, ("Reviewer A", "Reviewer B")))

    approvals = [
        review
        for review in env.db.list_human_reviews(task.id)
        if review.decision == HumanDecision.APPROVE
    ]
    assert len(approvals) == 1
    assert sorted(outcomes) == ["approved", "refused"]
    assert env.db.get_task(task.id).status == TaskStatus.APPROVED


def test_unique_review_index_exists(env):
    row = env.db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' "
        "AND name = 'uq_reviews_version_decision'"
    ).fetchone()
    assert row is not None


def test_unique_index_rejects_direct_duplicate(env):
    task, version = _ready_task(env)
    record_decision(env.db, task.id, version.id, "approve", "Reviewer", max_revisions=2)
    review = env.db.latest_review_for_version(version.id)
    assert review is not None

    with pytest.raises(sqlite3.IntegrityError):
        with env.db.conn:
            env.db.conn.execute(
                """INSERT INTO human_reviews
                   (id, task_id, version_id, content_hash, decision, feedback,
                    reviewer, actor, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "duplicate-direct-insert",
                    task.id,
                    version.id,
                    review.content_hash,
                    HumanDecision.APPROVE.value,
                    "",
                    "Direct SQL",
                    "human:direct",
                    review.created_at,
                ),
            )
