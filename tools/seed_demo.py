"""Seed one reviewed task for browser checks or a local demo.

Usage:
    python tools/seed_demo.py --data-dir .ci-data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ruff: noqa: E402  (project imports follow the sys.path bootstrap)

from aegisflow.database import Database
from aegisflow.document_processing import document_to_state, save_and_extract
from aegisflow.services.workflow_service import WorkflowService
from aegisflow.skills_loader import load_skills
from config import PROJECT_ROOT, Settings


def seed(data_dir: Path) -> str:
    settings = Settings(
        mode="mock", data_dir=data_dir, skills_dir=PROJECT_ROOT / "skills"
    ).validate()
    settings.ensure_directories()
    db = Database(settings.app_db_path)
    workflow = WorkflowService(settings, db, load_skills(settings.skills_dir))
    try:
        existing = db.list_tasks(limit=1)
        if existing:
            print(f"data already seeded: {existing[0].id}")
            return existing[0].id
        sample = PROJECT_ROOT / "sample_data" / "project_notes.txt"
        task = db.create_task(
            "Please prepare a meeting report from these notes.",
            "markdown",
            True,
            manual_minutes=45.0,
        )
        meta, extracted, stored = save_and_extract(
            settings.upload_dir,
            task.id,
            sample.name,
            sample.read_bytes(),
            settings.max_file_mb,
        )
        db.add_file(
            task.id,
            meta.filename,
            stored,
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
            manual_minutes=45.0,
        )
        if not result.interrupted:
            raise RuntimeError(f"workflow did not pause for review: {result.status}")
        print(f"seeded task={task.id} status={result.status}")
        return task.id
    finally:
        workflow.close()
        db.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=".ci-data")
    args = parser.parse_args(argv[1:])
    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir
    seed(data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
