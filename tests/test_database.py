import sqlite3
from dataclasses import replace

import pytest
from pydantic import BaseModel

from aegisflow.agents.base import AgentFailure, call_agent
from aegisflow.database import EXECUTION_METRIC_COLUMNS, Database
from aegisflow.models import TaskStatus, WorkloadMetric
from aegisflow.prompts import prompt_fingerprint
from aegisflow.services.llm_service import LLMError, TransientProviderError


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


def test_agent_execution_records_usage(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    env.db.add_agent_execution(
        task.id,
        "planner",
        2,
        "task-planning",
        "completed",
        prompt_version="abc123abc123",
        model_backend="openrouter",
        model_id="test/model",
        input_tokens=120,
        output_tokens=40,
        latency_ms=845,
    )
    row = env.db.list_agent_executions(task.id)[0]
    assert row["prompt_version"] == "abc123abc123"
    assert (row["model_backend"], row["model_id"]) == ("openrouter", "test/model")
    assert (row["input_tokens"], row["output_tokens"], row["latency_ms"]) == (120, 40, 845)


def test_agent_execution_usage_defaults_to_null(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    env.db.add_agent_execution(
        task.id, "policy_checker", 3, "quality-review", "completed"
    )
    row = env.db.list_agent_executions(task.id)[0]
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None
    assert row["latency_ms"] is None
    assert row["model_backend"] == ""


def test_existing_database_gains_usage_columns(tmp_path):
    """A database created before the usage columns existed is upgraded in place."""
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE agent_executions (
               id TEXT PRIMARY KEY,
               task_id TEXT NOT NULL,
               agent TEXT NOT NULL,
               level INTEGER NOT NULL,
               skill TEXT NOT NULL,
               input_ref TEXT NOT NULL DEFAULT '',
               output_ref TEXT NOT NULL DEFAULT '',
               status TEXT NOT NULL,
               retries INTEGER NOT NULL DEFAULT 0,
               error_class TEXT NOT NULL DEFAULT '',
               simulated INTEGER NOT NULL DEFAULT 1,
               started_at TEXT NOT NULL,
               finished_at TEXT NOT NULL
           )"""
    )
    conn.commit()
    conn.close()

    db = Database(path)
    try:
        columns = {
            row["name"] for row in db.conn.execute("PRAGMA table_info(agent_executions)")
        }
        assert set(EXECUTION_METRIC_COLUMNS) <= columns
    finally:
        db.close()


class _Answer(BaseModel):
    text: str


class _FakeLLM:
    def __init__(self, usage=None):
        self.last_usage = usage

    def structured(self, **_kwargs):
        return _Answer(text="ok")


def _run_agent(env, task_id, llm, settings=None):
    return call_agent(
        agent="planner",
        schema=_Answer,
        system_prompt="system",
        payload={"task": "x"},
        mock_builder=lambda: {},
        settings=settings or env.settings,
        llm=llm,
        db=env.db,
        task_id=task_id,
        level=2,
        skill="task-planning",
        input_ref="request",
    )


def test_call_agent_records_model_and_usage(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    llm = _FakeLLM({"input_tokens": 90, "output_tokens": 12, "total_tokens": 102})

    result, retries = _run_agent(env, task.id, llm)

    row = env.db.list_agent_executions(task.id)[0]
    assert result.text == "ok"
    assert retries == 0
    assert row["model_backend"] == "mock"
    assert row["model_id"] == ""
    assert row["prompt_version"] == prompt_fingerprint("system")
    assert row["input_tokens"] == 90
    assert row["output_tokens"] == 12
    assert row["latency_ms"] is not None
    assert row["latency_ms"] >= 0


def test_call_agent_leaves_usage_null_when_unreported(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)

    _run_agent(env, task.id, _FakeLLM(None))

    row = env.db.list_agent_executions(task.id)[0]
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None


def test_call_agent_names_the_real_backend(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    settings = replace(env.settings, mode="real", provider="openai", model="test-model")

    _run_agent(env, task.id, _FakeLLM(None), settings=settings)

    row = env.db.list_agent_executions(task.id)[0]
    assert row["model_backend"] == "openai"
    assert row["model_id"] == "test-model"


class _Clock:
    """Deterministic ``perf_counter``: each call returns the next value."""

    def __init__(self, *values: float):
        self._values = list(values)
        self._index = 0

    def perf_counter(self) -> float:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return value


class _FlakyLLM:
    """Fails transiently a fixed number of times, then answers."""

    def __init__(self, failures: int):
        self.remaining = failures
        self.last_usage = None
        self.calls = 0

    def structured(self, **_kwargs):
        self.calls += 1
        if self.remaining:
            self.remaining -= 1
            raise TransientProviderError("Simulated provider timeout.")
        return _Answer(text="ok")


def test_latency_covers_the_whole_call_not_just_the_last_attempt(env, monkeypatch):
    """A retried call must report the full duration, not the final attempt."""
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    llm = _FlakyLLM(failures=1)
    monkeypatch.setattr("aegisflow.agents.base.time", _Clock(100.0, 102.5))

    result, retries = _run_agent(
        env, task.id, llm, settings=replace(env.settings, max_retries=1)
    )

    row = env.db.list_agent_executions(task.id)[0]
    assert result.text == "ok"
    assert retries == 1
    assert llm.calls == 2
    assert row["latency_ms"] == 2500


def test_failed_call_reports_the_same_whole_call_latency(env, monkeypatch):
    """Success and failure rows must be measured on the same clock span."""
    task = env.db.create_task("A request with enough characters.", "markdown", True)
    llm = _FlakyLLM(failures=99)
    monkeypatch.setattr("aegisflow.agents.base.time", _Clock(10.0, 17.0))

    with pytest.raises(AgentFailure):
        _run_agent(env, task.id, llm, settings=replace(env.settings, max_retries=1))

    row = env.db.list_agent_executions(task.id)[0]
    assert llm.calls == 2
    assert row["status"] == "failed"
    assert row["latency_ms"] == 7000


_ATTEMPTS = [
    {"provider": "openrouter", "model": "a", "error": "LLMError", "transient": False},
    {
        "provider": "openrouter",
        "model": "b",
        "error": "TransientProviderError",
        "transient": True,
    },
    {"provider": "gemini", "model": "c", "error": "LLMError", "transient": False},
]


class _FallbackLLM:
    """Answers, but reports earlier candidates it never got past."""

    def __init__(self, attempts):
        self.last_attempts = attempts
        self.active_provider = "openrouter"
        self.active_model = "d"
        self.last_usage = None

    def structured(self, **_kwargs):
        return _Answer(text="ok")


class _ExhaustedLLM:
    """Every candidate failed, so nothing answered."""

    def __init__(self, attempts):
        self.last_attempts = attempts
        self.active_provider = ""
        self.active_model = ""
        self.last_usage = None

    def structured(self, **_kwargs):
        raise LLMError("All model candidates failed.")


def test_fallback_audit_records_every_skipped_candidate(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)

    _run_agent(env, task.id, _FallbackLLM(_ATTEMPTS))

    events = [
        event
        for event in env.db.list_audit(task.id)
        if event.event_type == "provider_fallback"
    ]
    assert len(events) == 1
    detail = events[0].detail
    assert "tried=openrouter/a (LLMError)" in detail
    assert "openrouter/b (TransientProviderError)" in detail
    assert "gemini/c (LLMError)" in detail
    assert "served_by=openrouter/d" in detail


def test_exhausted_candidates_are_recorded_when_nothing_answers(env):
    task = env.db.create_task("A request with enough characters.", "markdown", True)

    with pytest.raises(AgentFailure):
        _run_agent(env, task.id, _ExhaustedLLM(_ATTEMPTS))

    events = [
        event
        for event in env.db.list_audit(task.id)
        if event.event_type == "provider_candidates_exhausted"
    ]
    assert len(events) == 1
    detail = events[0].detail
    assert "openrouter/b (TransientProviderError)" in detail
    assert "gemini/c (LLMError)" in detail
    assert "no candidate answered" in detail
