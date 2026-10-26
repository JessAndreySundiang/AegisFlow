"""Workload and groundedness metrics. No metric is invented."""

from __future__ import annotations

import re
from typing import Any

from .database import Database
from .models import ClaimStatus, TaskRecord, WorkloadMetric

_CLAIM_LINE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*\S)\s*$")
_REFERENCE = re.compile(r"\[(S\d+|UNVERIFIED[^\]]*)\]", re.IGNORECASE)


def groundedness(claims: list[dict[str, Any]]) -> float | None:
    """Share of claims that are supported AND carry a source reference."""
    if not claims:
        return None
    supported = sum(
        1
        for claim in claims
        if claim.get("status") == ClaimStatus.SUPPORTED.value
        and str(claim.get("source_ref", "")).strip()
    )
    return round(supported / len(claims), 4)


def citation_coverage(draft: str) -> float | None:
    """Share of detected claim lines that carry [S#] or [UNVERIFIED]."""
    lines = [
        match.group(1)
        for line in draft.splitlines()
        if (match := _CLAIM_LINE.match(line))
        and len(match.group(1)) > 12
    ]
    if not lines:
        return None
    cited = sum(1 for line in lines if _REFERENCE.search(line))
    return round(cited / len(lines), 4)


def revision_count(db: Database, task_id: str) -> int:
    return sum(
        1
        for review in db.list_human_reviews(task_id)
        if review.decision.value == "request_revision"
    )


def time_reduction_pct(
    manual_minutes: float | None, elapsed_seconds: float | None
) -> float | None:
    """Time reduction only. This is not a quality measure.

    Negative values mean the AI-assisted run was slower than the user's estimate.
    """
    if manual_minutes is None or elapsed_seconds is None or manual_minutes <= 0:
        return None
    manual_seconds = manual_minutes * 60.0
    return round(((manual_seconds - elapsed_seconds) / manual_seconds) * 100.0, 1)


def build_workload_metric(
    db: Database,
    task: TaskRecord,
    *,
    approval_outcome: str,
    quality_rating: int | None = None,
) -> WorkloadMetric:
    subtasks = db.list_subtasks(task.id)
    revisions = revision_count(db, task.id)
    return WorkloadMetric(
        task_id=task.id,
        manual_minutes=task.manual_minutes,
        elapsed_seconds=task.elapsed_seconds,
        subtasks_completed=sum(1 for s in subtasks if s.get("status") == "completed"),
        revisions_requested=revisions,
        approval_outcome=approval_outcome,
        quality_rating=quality_rating,
        time_reduction_pct=time_reduction_pct(
            task.manual_minutes, task.elapsed_seconds
        ),
    )


def save_workload_metric(
    db: Database,
    task: TaskRecord,
    *,
    approval_outcome: str,
    quality_rating: int | None = None,
) -> WorkloadMetric:
    metric = build_workload_metric(
        db, task, approval_outcome=approval_outcome, quality_rating=quality_rating
    )
    db.save_workload(metric)
    return metric
