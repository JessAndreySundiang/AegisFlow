"""Human approval state machine and hash-bound finalization checks.

Approval writes are intentionally restricted to the UI layer by requiring an
actor string that starts with ``human:``. Agents never import or call this
module. This is an application-level control, not a security boundary against a
local user who can edit the SQLite file.
"""

from __future__ import annotations

import uuid
from typing import Any

from .database import Database
from .models import (
    ALLOWED_TRANSITIONS,
    ApprovalRecord,
    HumanDecision,
    OutputSource,
    OutputVersion,
    TaskStatus,
    sha256_text,
    utcnow_iso,
)
from .redaction import sanitize_detail


class ApprovalError(RuntimeError):
    """Raised for invalid, stale, duplicate, or unauthorized approval actions."""


def _require_human(actor: str) -> None:
    if not actor or not actor.startswith("human:"):
        raise ApprovalError(
            "Only the human UI layer may record approval decisions "
            "(actor must start with 'human:')."
        )


def record_decision(
    db: Database,
    task_id: str,
    version_id: str,
    decision: str | HumanDecision,
    reviewer: str,
    feedback: str = "",
    actor: str = "human:local",
    max_revisions: int = 2,
) -> ApprovalRecord:
    """Persist a human decision and update the task state atomically.

    Approve and reject bind to the exact version and content hash. A stale
    version, a hash mismatch, a duplicate approval, or an invalid state
    transition is rejected.
    """
    _require_human(actor)
    decision_value = HumanDecision(decision)
    if not reviewer.strip():
        raise ApprovalError("A reviewer name is required.")
    if decision_value == HumanDecision.REQUEST_REVISION and not feedback.strip():
        raise ApprovalError("Revision feedback is required.")

    task = db.get_task(task_id)
    if task is None:
        raise ApprovalError(f"Task not found: {task_id}")
    if task.status != TaskStatus.AWAITING_HUMAN_REVIEW:
        raise ApprovalError(
            f"Task is not awaiting human review (current status: {task.status.value})."
        )

    version = db.get_output_version(version_id)
    if version is None or version.task_id != task_id:
        raise ApprovalError("Output version does not belong to this task.")
    if task.current_version_id != version_id:
        raise ApprovalError(
            "This version is stale. Only the current output version can be reviewed."
        )
    if sha256_text(version.content) != version.content_hash:
        raise ApprovalError("Output content hash mismatch; the version is corrupted.")

    latest = db.latest_review_for_version(version_id)
    if latest is not None and latest.decision == HumanDecision.APPROVE:
        raise ApprovalError("This version has already been approved.")
    if latest is not None and latest.decision == decision_value:
        raise ApprovalError("Duplicate decision for this version.")

    if decision_value == HumanDecision.REQUEST_REVISION:
        revision_count = sum(
            1
            for review in db.list_human_reviews(task_id)
            if review.decision == HumanDecision.REQUEST_REVISION
        )
        if revision_count >= max_revisions:
            raise ApprovalError(
                "Maximum revision cycles reached for this task. Approve or reject it."
            )

    new_status = {
        HumanDecision.APPROVE: TaskStatus.APPROVED,
        HumanDecision.REJECT: TaskStatus.REJECTED,
        HumanDecision.REQUEST_REVISION: TaskStatus.REVISION_REQUESTED,
    }[decision_value]

    allowed = ALLOWED_TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise ApprovalError(
            f"Invalid transition: {task.status.value} -> {new_status.value}"
        )

    review_id = str(uuid.uuid4())
    now = utcnow_iso()
    detail = (
        f"decision={decision_value.value}; version={version.version_number}; "
        f"hash={version.content_hash[:12]}...; reviewer={sanitize_detail(reviewer)}"
    )
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO human_reviews
               (id, task_id, version_id, content_hash, decision, feedback,
                reviewer, actor, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                review_id,
                task_id,
                version_id,
                version.content_hash,
                decision_value.value,
                sanitize_detail(feedback),
                reviewer,
                actor,
                now,
            ),
        )
        conn.execute(
            """UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?""",
            (new_status.value, now, task_id),
        )
        conn.execute(
            """INSERT INTO audit_log
               (id, task_id, event_type, actor, rule_id, detail, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                task_id,
                "human_decision",
                actor,
                "GR-01",
                detail,
                now,
            ),
        )

    return ApprovalRecord(
        id=review_id,
        task_id=task_id,
        version_id=version_id,
        version_number=version.version_number,
        content_hash=version.content_hash,
        decision=decision_value,
        feedback=feedback,
        reviewer=reviewer,
        actor=actor,
        created_at=now,
    )


def create_output_version(
    db: Database,
    task_id: str,
    content: str,
    source: str | OutputSource,
    validation_status: str = "pending",
    simulated: bool = True,
) -> OutputVersion:
    """Create a new immutable output version and point the task at it.

    Any prior approval is invalidated implicitly because approval is keyed to a
    version id and content hash. The caller decides the subsequent task status.
    """
    if not content.strip():
        raise ApprovalError("Output content cannot be empty.")
    task = db.get_task(task_id)
    if task is None:
        raise ApprovalError(f"Task not found: {task_id}")
    if task.status == TaskStatus.COMPLETED:
        raise ApprovalError(
            "A completed task cannot be edited. Start a new revision cycle or a new task."
        )
    if task.status == TaskStatus.APPROVED:
        db.transition_task(task_id, TaskStatus.AWAITING_HUMAN_REVIEW)
    version = db.add_output_version(
        task_id=task_id,
        content=content,
        source=source,
        validation_status=validation_status,
        simulated=simulated,
    )
    db.add_audit(
        task_id,
        "output_version_created",
        "system",
        "GR-01" if source == OutputSource.HUMAN_EDIT else None,
        f"version={version.version_number}; source={version.source.value}; "
        f"hash={version.content_hash[:12]}...",
    )
    return version


def assert_finalizable(
    db: Database, task_id: str, version_id: str, content_hash: str
) -> ApprovalRecord:
    """Re-verify the exact approval record at finalization/export time."""
    task = db.get_task(task_id)
    if task is None:
        raise ApprovalError(f"Task not found: {task_id}")
    if task.status not in {TaskStatus.APPROVED, TaskStatus.COMPLETED}:
        raise ApprovalError(
            f"Task is not approved (current status: {task.status.value})."
        )
    if task.current_version_id != version_id:
        raise ApprovalError("The approved version is no longer the current version.")
    version = db.get_output_version(version_id)
    if version is None:
        raise ApprovalError("Output version not found.")
    if version.content_hash != content_hash:
        raise ApprovalError("Stale or mismatched approval: content hash differs.")
    if sha256_text(version.content) != content_hash:
        raise ApprovalError("Stored content does not match its hash.")
    latest = db.latest_review_for_version(version_id)
    if latest is None or latest.decision != HumanDecision.APPROVE:
        raise ApprovalError("No valid human approval exists for this version.")
    if latest.content_hash != content_hash:
        raise ApprovalError("Approval is bound to a different content hash.")
    return latest


def approval_history(db: Database, task_id: str) -> list[dict[str, Any]]:
    return [
        {
            "version": review.version_id,
            "decision": review.decision.value,
            "reviewer": review.reviewer,
            "actor": review.actor,
            "feedback": review.feedback,
            "created_at": review.created_at,
            "content_hash": review.content_hash,
        }
        for review in db.list_human_reviews(task_id)
    ]
