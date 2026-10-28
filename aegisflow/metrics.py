"""Workload and groundedness metrics. No metric is invented."""

from __future__ import annotations

import re
from dataclasses import dataclass
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


# ------------------------------------------------------------------ readability
# Presentation heuristic only. It never feeds a governance decision.

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_CITATION = re.compile(r"\[(?:S\d+|UNVERIFIED[^\]]*)\]", re.IGNORECASE)
_MARKUP = re.compile(r"[*_#>|]+")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_SENTENCE_END = re.compile(r"[.!?]+")
_VOWELS = frozenset("aeiouy")

# Flesch bands are a presentation convention chosen for a busy-manager reader,
# not the original 0-100 score-range vocabulary.
READABILITY_BANDS: tuple[tuple[float, str], ...] = (
    (60.0, "plain"),
    (50.0, "fairly difficult"),
    (30.0, "difficult"),
    (0.0, "very difficult"),
)


@dataclass(frozen=True)
class Readability:
    """A local readability estimate. Never an LLM judgement."""

    flesch: float
    label: str
    words: int
    sentences: int

    @property
    def score(self) -> int:
        return int(round(self.flesch))


def _syllables(word: str) -> int:
    """Count vowel groups, with a silent-``e`` adjustment.

    Deliberately simple: the result is an approximation and is labelled as one
    wherever it is shown.
    """
    lowered = word.lower()
    count = 0
    previous_vowel = False
    for character in lowered:
        is_vowel = character in _VOWELS
        if is_vowel and not previous_vowel:
            count += 1
        previous_vowel = is_vowel
    if lowered.endswith("e") and not lowered.endswith(("le", "ee")) and count > 1:
        count -= 1
    return max(1, count)


def plain_text(draft: str) -> str:
    """Strip Markdown furniture and citation markers before counting words."""
    text = _FENCE.sub(" ", draft or "")
    text = _INLINE_CODE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _CITATION.sub(" ", text)
    return _MARKUP.sub(" ", text)


def readability(draft: str) -> Readability | None:
    """Estimate Flesch reading ease with a local syllable heuristic.

    Deterministic and offline: the same text always yields the same number. The
    score describes the draft only — it says nothing about whether the content
    is accurate, complete, or approved.
    """
    text = plain_text(draft)
    words = _WORD.findall(text)
    if not words:
        return None
    sentences = max(1, len(_SENTENCE_END.findall(text)))
    syllables = sum(_syllables(word) for word in words)
    score = (
        206.835
        - (1.015 * (len(words) / sentences))
        - (84.6 * (syllables / len(words)))
    )
    score = max(0.0, min(121.0, score))
    label = next(name for threshold, name in READABILITY_BANDS if score >= threshold)
    return Readability(
        flesch=round(score, 1),
        label=label,
        words=len(words),
        sentences=sentences,
    )
