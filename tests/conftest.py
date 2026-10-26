from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import Settings
from aegisflow.database import Database
from aegisflow.document_processing import document_to_state, save_and_extract
from aegisflow.skills_loader import load_skills
from aegisflow.services.workflow_service import WorkflowService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = PROJECT_ROOT / "sample_data"


@pytest.fixture
def env(tmp_path):
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
    yield SimpleNamespace(
        settings=settings,
        db=db,
        skills=skills,
        workflow=workflow,
        tmp_path=tmp_path,
    )
    workflow.close()
    db.close()


@pytest.fixture
def make_task(env):
    def _make(
        request: str = "Please prepare a meeting report from these notes.",
        files: list[tuple[str, bytes]] | None = None,
        output_format: str = "markdown",
        manual_minutes: float | None = 45.0,
    ):
        task = env.db.create_task(
            request, output_format, True, manual_minutes=manual_minutes
        )
        docs: dict[str, dict] = {}
        metas = []
        for filename, data in files or []:
            meta, extracted, path = save_and_extract(
                env.settings.upload_dir,
                task.id,
                filename,
                data,
                env.settings.max_file_mb,
            )
            env.db.add_file(
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
            docs[meta.file_id] = doc
            metas.append(meta)
        return task, list(docs.values()), docs, metas

    return _make


@pytest.fixture
def make_workflow(env):
    """Build extra workflow runners with overridden (frozen) settings."""
    created: list[WorkflowService] = []

    def _make(**overrides):
        settings = replace(env.settings, **overrides)
        workflow = WorkflowService(settings, env.db, env.skills)
        created.append(workflow)
        return workflow, settings

    yield _make
    for workflow in created:
        workflow.close()


@pytest.fixture
def sample_txt() -> bytes:
    return (SAMPLES / "project_notes.txt").read_bytes()


@pytest.fixture
def injection_txt() -> bytes:
    return (SAMPLES / "injection_notes.txt").read_bytes()


@pytest.fixture
def run_task(env):
    def _run(task, files, docs):
        return env.workflow.start(
            task.id,
            task.request,
            task.output_format,
            files,
            docs,
            manual_minutes=task.manual_minutes,
        )

    return _run
