"""Approved-output export. Export re-checks the backend approval record."""

from __future__ import annotations

from pathlib import Path

from ..approvals import ApprovalError, assert_finalizable
from ..database import Database
from ..models import OutputVersion, TaskRecord


def _metadata_block(task: TaskRecord, version: OutputVersion, approval) -> str:
    return "\n".join(
        [
            "---",
            "status: APPROVED",
            f"task_id: {task.id}",
            f"version: {version.version_number}",
            f"content_hash: {version.content_hash}",
            f"reviewer: {approval.reviewer}",
            f"approved_at: {approval.created_at}",
            f"simulated: {'true' if version.simulated else 'false'}",
            "---",
            "",
        ]
    )


def export_markdown(db: Database, task_id: str, version_id: str) -> str:
    task = db.get_task(task_id)
    version = db.get_output_version(version_id)
    if task is None or version is None:
        raise ApprovalError("Task or output version not found.")
    approval = assert_finalizable(db, task_id, version_id, version.content_hash)
    header = _metadata_block(task, version, approval)
    if version.simulated and "simulated output" not in version.content.lower():
        header += "**SIMULATED OUTPUT** — not real AI analysis.\n\n"
    return header + version.content + "\n"


def export_txt(db: Database, task_id: str, version_id: str) -> str:
    task = db.get_task(task_id)
    version = db.get_output_version(version_id)
    if task is None or version is None:
        raise ApprovalError("Task or output version not found.")
    approval = assert_finalizable(db, task_id, version_id, version.content_hash)
    lines = [
        "AEGISFLOW APPROVED OUTPUT",
        f"Task ID: {task.id}",
        f"Version: {version.version_number}",
        f"Content hash: {version.content_hash}",
        f"Reviewer: {approval.reviewer}",
        f"Approved at: {approval.created_at}",
        f"Simulated: {'yes' if version.simulated else 'no'}",
        "",
        version.content,
        "",
    ]
    return "\n".join(lines)


def suggested_filename(task: TaskRecord, version: OutputVersion, extension: str) -> str:
    stem = f"aegisflow_{task.id[:8]}_v{version.version_number}"
    return f"{stem}.{extension.lstrip('.')}"


def write_export(directory: str | Path, filename: str, content: str) -> Path:
    path = Path(directory) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
