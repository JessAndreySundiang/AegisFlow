"""Streamlit UI smoke and approval-flow test using AppTest (no browser)."""

from __future__ import annotations

from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from aegisflow.database import Database
from aegisflow.document_processing import document_to_state, save_and_extract
from aegisflow.models import TaskStatus
from aegisflow.skills_loader import load_skills
from aegisflow.services.workflow_service import WorkflowService
from config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = PROJECT_ROOT / "sample_data"


def _seed_review_task(tmp_path: Path):
    settings = Settings(
        mode="mock",
        data_dir=tmp_path / "data",
        skills_dir=PROJECT_ROOT / "skills",
        max_retries=1,
        max_revisions=2,
        recursion_limit=80,
    ).validate()
    settings.ensure_directories()
    db = Database(settings.app_db_path)
    skills = load_skills(settings.skills_dir)
    workflow = WorkflowService(settings, db, skills)
    task = db.create_task(
        "Please prepare a meeting report from these notes.",
        "markdown",
        True,
        manual_minutes=45.0,
    )
    data = (SAMPLES / "project_notes.txt").read_bytes()
    meta, extracted, path = save_and_extract(
        settings.upload_dir, task.id, "project_notes.txt", data, settings.max_file_mb
    )
    db.add_file(
        task.id,
        meta.filename,
        path,
        meta.extension,
        meta.size_bytes,
        meta.sha256,
        meta.pages,
        meta.status.value,
        meta.message,
        file_id=meta.file_id,
    )
    doc = document_to_state(meta, extracted)
    result = workflow.start(
        task.id,
        task.request,
        task.output_format,
        [doc],
        {meta.file_id: doc},
        manual_minutes=task.manual_minutes,
    )
    assert result.interrupted and result.status == "awaiting_human_review"
    workflow.close()
    db.close()
    return settings, task.id


def test_ui_renders_pages_and_approval_flow_finalizes(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGISFLOW_DATA_DIR", str(tmp_path / "data"))
    st.cache_resource.clear()
    settings, task_id = _seed_review_task(tmp_path)

    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=120).run()
    assert not at.exception
    assert [title.value for title in at.title] == ["Dashboard"]
    assert any("SIMULATED OUTPUT" in block.value for block in at.markdown)

    for page in ("New Task", "Workflow", "Review", "History"):
        at.session_state["page"] = page
        at.run()
        assert not at.exception, (page, [e.message for e in at.exception])

    # Open the seeded task's review gate.
    at.session_state["active_task_id"] = task_id
    at.session_state["page"] = "Review"
    at.run()
    assert not at.exception
    assert [title.value for title in at.title] == [f"Review · T-{task_id[:4].upper()}"]
    assert any(input_.label.startswith("Content hash") for input_ in at.text_input)
    assert any(area.label == "Draft" for area in at.text_area)

    # The action names the exact version. Submitting without acknowledging is refused.
    decision = next(r for r in at.radio if r.label == "Decision")
    approve_label = next(option for option in decision.options if option.startswith("Approve version"))
    decision.set_value(approve_label)
    at.run()
    assert any(button.label == approve_label for button in at.button)
    next(b for b in at.button if b.label == approve_label).click()
    at.run()
    assert any("confirm" in error.value.lower() for error in at.error)
    db = Database(settings.app_db_path)
    assert db.get_task(task_id).status == TaskStatus.AWAITING_HUMAN_REVIEW
    assert db.list_human_reviews(task_id) == []
    db.close()

    # Approve the exact version, then verify the graph finalized through the UI.
    acknowledgement = next(c for c in at.checkbox if "reviewed version" in c.label)
    acknowledgement.set_value(True)
    next(b for b in at.button if b.label == approve_label).click()
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["page"] == "Workflow"
    assert [title.value for title in at.title] == [f"Task T-{task_id[:4].upper()} · Workflow"]

    db = Database(settings.app_db_path)
    task = db.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED
    reviews = db.list_human_reviews(task_id)
    assert len(reviews) == 1
    assert reviews[0].decision.value == "approve"
    assert reviews[0].actor == "human:streamlit"
    assert any(event.event_type == "finalized" for event in db.list_audit(task_id))
    db.close()


def test_ui_rejection_requires_terminal_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGISFLOW_DATA_DIR", str(tmp_path / "data"))
    st.cache_resource.clear()
    settings, task_id = _seed_review_task(tmp_path)

    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=120).run()
    at.session_state["active_task_id"] = task_id
    at.session_state["page"] = "Review"
    at.run()
    assert not at.exception

    decision = next(r for r in at.radio if r.label == "Decision")
    reject_label = next(option for option in decision.options if option.startswith("Reject version"))
    decision.set_value(reject_label)
    at.run()
    acknowledgement = next(c for c in at.checkbox if "reviewed version" in c.label)
    acknowledgement.set_value(True)
    next(b for b in at.button if b.label.startswith("Reject version")).click()
    at.run()
    assert any("terminal" in error.value.lower() for error in at.error)

    db = Database(settings.app_db_path)
    assert db.get_task(task_id).status == TaskStatus.AWAITING_HUMAN_REVIEW
    assert db.list_human_reviews(task_id) == []
    db.close()

    confirmation = next(c for c in at.checkbox if "terminal" in c.label)
    confirmation.set_value(True)
    next(b for b in at.button if b.label.startswith("Reject version")).click()
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["page"] == "Workflow"

    db = Database(settings.app_db_path)
    assert db.get_task(task_id).status == TaskStatus.REJECTED
    reviews = db.list_human_reviews(task_id)
    assert len(reviews) == 1
    assert reviews[0].decision.value == "reject"
    assert reviews[0].actor == "human:streamlit"
    db.close()


def test_ui_revision_requires_feedback_and_creates_new_version(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGISFLOW_DATA_DIR", str(tmp_path / "data"))
    st.cache_resource.clear()
    settings, task_id = _seed_review_task(tmp_path)

    at = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=120).run()
    at.session_state["active_task_id"] = task_id
    at.session_state["page"] = "Review"
    at.run()
    assert not at.exception

    decision = next(r for r in at.radio if r.label == "Decision")
    revision_label = next(
        option for option in decision.options if option.startswith("Request a bounded revision")
    )
    decision.set_value(revision_label)
    at.run()
    acknowledgement = next(c for c in at.checkbox if "reviewed version" in c.label)
    acknowledgement.set_value(True)
    next(b for b in at.button if b.label.startswith("Request revision")).click()
    at.run()
    assert any("feedback is required" in error.value.lower() for error in at.error)

    db = Database(settings.app_db_path)
    assert db.list_human_reviews(task_id) == []
    db.close()

    feedback = next(area for area in at.text_area if area.label.startswith("Feedback"))
    feedback.set_value("Tighten the action items and cite section 2.")
    next(b for b in at.button if b.label.startswith("Request revision")).click()
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert at.session_state["page"] == "Review"

    db = Database(settings.app_db_path)
    assert db.get_task(task_id).status == TaskStatus.AWAITING_HUMAN_REVIEW
    reviews = db.list_human_reviews(task_id)
    assert len(reviews) == 1
    assert reviews[0].decision.value == "request_revision"
    assert "Tighten" in reviews[0].feedback
    assert len(db.list_output_versions(task_id)) == 2
    db.close()
