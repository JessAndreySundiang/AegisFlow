import pytest
from pydantic import ValidationError

from aegisflow.models import (
    Claim,
    ClaimStatus,
    Plan,
    PlanSubtask,
    TaskStatus,
    sha256_text,
)


def _subtask(id_, agent="document_analyst", skill="document-extraction", deps=None):
    return PlanSubtask(
        id=id_,
        title="t",
        description="d",
        assigned_agent=agent,
        skill=skill,
        depends_on=deps or [],
    )


def test_plan_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        Plan(
            task_type="summary",
            objective="x",
            subtasks=[_subtask("s1"), _subtask("s1")],
            required_skills=["document-extraction"],
        )


def test_plan_rejects_unknown_dependency():
    with pytest.raises(ValidationError):
        Plan(
            task_type="summary",
            objective="x",
            subtasks=[_subtask("s1", deps=["s9"])],
            required_skills=["document-extraction"],
        )


def test_plan_rejects_self_dependency():
    with pytest.raises(ValidationError):
        Plan(
            task_type="summary",
            objective="x",
            subtasks=[_subtask("s1", deps=["s1"])],
            required_skills=["document-extraction"],
        )


def test_blocked_plan_cannot_have_subtasks():
    with pytest.raises(ValidationError):
        Plan(
            task_type="summary",
            objective="x",
            subtasks=[_subtask("s1")],
            required_skills=["document-extraction"],
            missing_information=["no file"],
        )


def test_claim_requires_text():
    with pytest.raises(ValidationError):
        Claim(id="S1", text="   ")


def test_hash_is_stable():
    assert sha256_text("abc") == sha256_text("abc")
    assert sha256_text("abc") != sha256_text("abcd")


def test_task_status_enum_values():
    assert TaskStatus.AWAITING_HUMAN_REVIEW.value == "awaiting_human_review"
    assert TaskStatus.REVISION_REQUESTED.value == "revision_requested"
    assert ClaimStatus.SUPPORTED.value == "supported"
