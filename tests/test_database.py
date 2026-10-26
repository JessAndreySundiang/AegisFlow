import pytest

from aegisflow.models import TaskStatus, WorkloadMetric


def test_task_lifecycle(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    assert task.status == TaskStatus.PENDING
    env.db.transition_task(task.id, "planning")
    env.db.transition_task(task.id, "in_progress")
    env.db.transition_task(task.id, "awaiting_human_review")
    env.db.transition_task(task.id, "approved")
    env.db.transition_task(task.id, "completed")
    assert env.db.get_task(task.id).status == TaskStatus.COMPLETED


def test_invalid_transition_rejected(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    with pytest.raises(ValueError):
        env.db.transition_task(task.id, "completed")


def test_output_versions_increment_and_hash(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    v1 = env.db.add_output_version(task.id, "first", "agent")
    v2 = env.db.add_output_version(task.id, "second", "human_edit")
    assert (v1.version_number, v2.version_number) == (1, 2)
    assert v1.content_hash != v2.content_hash
    assert env.db.latest_output_version(task.id).id == v2.id


def test_delete_task_cascades(env, tmp_path):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    path = tmp_path / "f.txt"
    path.write_text("hello", encoding="utf-8")
    env.db.add_file(task.id, "f.txt", str(path), ".txt", 5, "abc", None, "ok")
    env.db.add_subtask(task.id, "s1", "t", "d", "document_analyst", "document-extraction", [])
    removed = env.db.delete_task(task.id)
    assert str(path) in removed
    assert env.db.get_task(task.id) is None
    assert env.db.list_files(task.id) == []
    assert env.db.list_subtasks(task.id) == []


def test_audit_redacts_secrets_and_pii(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    env.db.add_audit(
        task.id,
        "test",
        "system",
        "GR-04",
        "email juan.delacruz@example.com key sk-or-abcdefghijklmnop",
    )
    detail = env.db.list_audit(task.id)[0].detail
    assert "juan.delacruz@example.com" not in detail
    assert "sk-or-abcdefghijklmnop" not in detail
    assert "[REDACTED:EMAIL]" in detail


def test_workload_roundtrip(env):
    task = env.db.create_task(
        "A request with enough characters.", "markdown", True, manual_minutes=30
    )
    metric = WorkloadMetric(
        task_id=task.id,
        manual_minutes=30,
        elapsed_seconds=600,
        subtasks_completed=3,
        revisions_requested=1,
        approval_outcome="approved",
        quality_rating=4,
        time_reduction_pct=66.7,
    )
    env.db.save_workload(metric)
    loaded = env.db.get_workload(task.id)
    assert loaded.manual_minutes == 30
    assert loaded.quality_rating == 4


def test_counts(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    env.db.transition_task(task.id, "planning")
    assert env.db.counts_by_status()["planning"] == 1
