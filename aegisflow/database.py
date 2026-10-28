"""SQLite application database (separate from LangGraph checkpoints)."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import (
    ALLOWED_TRANSITIONS,
    ApprovalRecord,
    AuditEvent,
    HumanDecision,
    HumanReview,
    OutputSource,
    OutputVersion,
    TaskRecord,
    TaskStatus,
    WorkloadMetric,
    sha256_text,
    utcnow_iso,
)
from .redaction import sanitize_detail

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    request TEXT NOT NULL,
    output_format TEXT NOT NULL,
    status TEXT NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 1,
    manual_minutes REAL,
    elapsed_seconds REAL,
    escalation_reason TEXT NOT NULL DEFAULT '',
    current_version_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_files (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL DEFAULT '',
    pages INTEGER,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subtasks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    assigned_agent TEXT NOT NULL,
    skill TEXT NOT NULL,
    depends_on TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 1,
    retries INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_executions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent TEXT NOT NULL,
    level INTEGER NOT NULL,
    skill TEXT NOT NULL,
    input_ref TEXT NOT NULL DEFAULT '',
    output_ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    retries INTEGER NOT NULL DEFAULT 0,
    error_class TEXT NOT NULL DEFAULT '',
    simulated INTEGER NOT NULL DEFAULT 1,
    prompt_version TEXT NOT NULL DEFAULT '',
    model_backend TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS output_versions (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(task_id, version_number)
);

CREATE TABLE IF NOT EXISTS human_reviews (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    version_id TEXT NOT NULL REFERENCES output_versions(id) ON DELETE CASCADE,
    content_hash TEXT NOT NULL,
    decision TEXT NOT NULL,
    feedback TEXT NOT NULL DEFAULT '',
    reviewer TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_refs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    output_version_id TEXT REFERENCES output_versions(id) ON DELETE CASCADE,
    claim_id TEXT NOT NULL DEFAULT '',
    claim_text TEXT NOT NULL DEFAULT '',
    file_id TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    excerpt TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    rule_id TEXT,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workload_metrics (
    task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    manual_minutes REAL,
    elapsed_seconds REAL,
    subtasks_completed INTEGER NOT NULL DEFAULT 0,
    revisions_requested INTEGER NOT NULL DEFAULT 0,
    approval_outcome TEXT NOT NULL DEFAULT '',
    quality_rating INTEGER,
    time_reduction_pct REAL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_exec_task ON agent_executions(task_id);
CREATE INDEX IF NOT EXISTS idx_versions_task ON output_versions(task_id);
CREATE INDEX IF NOT EXISTS idx_reviews_task ON human_reviews(task_id);
CREATE INDEX IF NOT EXISTS idx_reviews_version ON human_reviews(version_id);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_log(task_id);
CREATE INDEX IF NOT EXISTS idx_evidence_task ON evidence_refs(task_id);
"""

# Usage columns added after the first release. Databases created before they
# existed are upgraded by ``_ensure_execution_metrics``; the values are optional
# because providers are not required to report token counts. ``latency_ms`` is
# the whole call, retries and backoff included, for both successful and failed
# rows.
EXECUTION_METRIC_COLUMNS = {
    "prompt_version": "TEXT NOT NULL DEFAULT ''",
    "model_backend": "TEXT NOT NULL DEFAULT ''",
    "model_id": "TEXT NOT NULL DEFAULT ''",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "latency_ms": "INTEGER",
}


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(
            str(self.path), check_same_thread=False, timeout=30.0
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.initialize()

    def initialize(self) -> None:
        with self._lock, self.conn:
            self.conn.executescript(SCHEMA)
            self._ensure_review_uniqueness()
            self._ensure_execution_metrics()

    def _ensure_review_uniqueness(self) -> None:
        """Add the approval uniqueness index when existing data allows it.

        The approval layer also rejects duplicates before writing. This index is
        the database-level backstop for concurrent writers and direct SQL. If an
        older database already contains duplicate rows, the index is skipped
        instead of preventing startup.
        """
        duplicate = self.conn.execute(
            "SELECT 1 FROM human_reviews GROUP BY version_id, decision "
            "HAVING COUNT(*) > 1 LIMIT 1"
        ).fetchone()
        if duplicate is None:
            self.conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_reviews_version_decision "
                "ON human_reviews(version_id, decision)"
            )

    def _ensure_execution_metrics(self) -> None:
        """Add the usage columns to a database created before they existed.

        ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so this
        migration is explicit and idempotent. Older rows keep empty/NULL metrics
        rather than receiving an inferred value.
        """
        existing = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(agent_executions)")
        }
        for column, declaration in EXECUTION_METRIC_COLUMNS.items():
            if column not in existing:
                self.conn.execute(
                    f"ALTER TABLE agent_executions ADD COLUMN {column} {declaration}"
                )

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                self.conn.execute("BEGIN")
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                pass

    # ------------------------------------------------------------------ tasks
    def create_task(
        self,
        request: str,
        output_format: str,
        simulated: bool,
        manual_minutes: float | None = None,
        task_id: str | None = None,
        status: str = TaskStatus.PENDING.value,
    ) -> TaskRecord:
        task_id = task_id or str(uuid.uuid4())
        now = utcnow_iso()
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT INTO tasks
                   (id, request, output_format, status, simulated, manual_minutes,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    request,
                    output_format,
                    status,
                    int(simulated),
                    manual_minutes,
                    now,
                    now,
                ),
            )
        task = self.get_task(task_id)
        assert task is not None
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        row = self._fetchone("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return self._task(row) if row else None

    def list_tasks(self, limit: int = 100, status: str | None = None) -> list[TaskRecord]:
        if status:
            rows = self._fetchall(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            rows = self._fetchall(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
            )
        return [self._task(r) for r in rows]

    def transition_task(
        self,
        task_id: str,
        new_status: str | TaskStatus,
        *,
        escalation_reason: str | None = None,
        elapsed_seconds: float | None = None,
        current_version_id: str | None = None,
    ) -> TaskRecord:
        current = self.get_task(task_id)
        if current is None:
            raise KeyError(f"task not found: {task_id}")
        new_value = TaskStatus(new_status)
        old_value = TaskStatus(current.status)
        if new_value != old_value:
            allowed = ALLOWED_TRANSITIONS.get(old_value, set())
            if new_value not in allowed:
                raise ValueError(
                    f"invalid task transition: {old_value.value} -> {new_value.value}"
                )
        now = utcnow_iso()
        with self._lock, self.conn:
            self.conn.execute(
                """UPDATE tasks SET status = ?, updated_at = ?,
                   escalation_reason = COALESCE(?, escalation_reason),
                   elapsed_seconds = COALESCE(?, elapsed_seconds),
                   current_version_id = COALESCE(?, current_version_id)
                   WHERE id = ?""",
                (
                    new_value.value,
                    now,
                    sanitize_detail(escalation_reason) if escalation_reason is not None else None,
                    elapsed_seconds,
                    current_version_id,
                    task_id,
                ),
            )
        updated = self.get_task(task_id)
        assert updated is not None
        return updated

    # ------------------------------------------------------------------ files
    def add_file(
        self,
        task_id: str,
        filename: str,
        stored_path: str,
        extension: str,
        size_bytes: int,
        sha256: str,
        pages: int | None,
        status: str,
        message: str = "",
        file_id: str | None = None,
    ) -> str:
        file_id = file_id or str(uuid.uuid4())
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT INTO task_files
                   (id, task_id, filename, stored_path, extension, size_bytes, sha256,
                    pages, status, message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    file_id,
                    task_id,
                    filename,
                    stored_path,
                    extension,
                    size_bytes,
                    sha256,
                    pages,
                    status,
                    sanitize_detail(message),
                    utcnow_iso(),
                ),
            )
        return file_id

    def list_files(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT * FROM task_files WHERE task_id = ? ORDER BY created_at", (task_id,)
        )
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- subtasks
    def add_subtask(
        self,
        task_id: str,
        subtask_id: str,
        title: str,
        description: str,
        assigned_agent: str,
        skill: str,
        depends_on: list[str],
        status: str = "pending",
        required: bool = True,
    ) -> None:
        now = utcnow_iso()
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO subtasks
                   (id, task_id, title, description, assigned_agent, skill,
                    depends_on, status, required, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    subtask_id,
                    task_id,
                    title,
                    description,
                    assigned_agent,
                    skill,
                    json.dumps(depends_on),
                    status,
                    int(required),
                    now,
                    now,
                ),
            )

    def update_subtask_status(self, task_id: str, subtask_id: str, status: str) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                "UPDATE subtasks SET status = ?, updated_at = ? WHERE task_id = ? AND id = ?",
                (status, utcnow_iso(), task_id, subtask_id),
            )

    def list_subtasks(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY created_at", (task_id,)
        )
        result = []
        for row in rows:
            item = dict(row)
            item["depends_on"] = json.loads(item.get("depends_on") or "[]")
            item["required"] = bool(item["required"])
            result.append(item)
        return result

    # ------------------------------------------------------------- executions
    def add_agent_execution(
        self,
        task_id: str,
        agent: str,
        level: int,
        skill: str,
        status: str,
        retries: int = 0,
        error_class: str = "",
        simulated: bool = True,
        input_ref: str = "",
        output_ref: str = "",
        started_at: str | None = None,
        finished_at: str | None = None,
        prompt_version: str = "",
        model_backend: str = "",
        model_id: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
    ) -> str:
        execution_id = str(uuid.uuid4())
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT INTO agent_executions
                   (id, task_id, agent, level, skill, input_ref, output_ref, status,
                    retries, error_class, simulated, prompt_version, model_backend,
                    model_id, input_tokens, output_tokens, latency_ms, started_at,
                    finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    execution_id,
                    task_id,
                    agent,
                    level,
                    skill,
                    sanitize_detail(input_ref),
                    sanitize_detail(output_ref),
                    status,
                    retries,
                    error_class,
                    int(simulated),
                    prompt_version,
                    model_backend,
                    model_id,
                    input_tokens,
                    output_tokens,
                    latency_ms,
                    started_at or utcnow_iso(),
                    finished_at or utcnow_iso(),
                ),
            )
        return execution_id

    def list_agent_executions(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT * FROM agent_executions WHERE task_id = ? ORDER BY started_at",
            (task_id,),
        )
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- versions
    def add_output_version(
        self,
        task_id: str,
        content: str,
        source: str | OutputSource,
        validation_status: str = "pending",
        simulated: bool = True,
    ) -> OutputVersion:
        source_value = OutputSource(source)
        content_hash = sha256_text(content)
        with self._lock, self.conn:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) AS n FROM output_versions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            version_number = int(row["n"]) + 1
            version_id = str(uuid.uuid4())
            now = utcnow_iso()
            self.conn.execute(
                """INSERT INTO output_versions
                   (id, task_id, version_number, content, content_hash, source,
                    validation_status, simulated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    task_id,
                    version_number,
                    content,
                    content_hash,
                    source_value.value,
                    validation_status,
                    int(simulated),
                    now,
                ),
            )
            self.conn.execute(
                "UPDATE tasks SET current_version_id = ?, updated_at = ? WHERE id = ?",
                (version_id, now, task_id),
            )
        return OutputVersion(
            id=version_id,
            task_id=task_id,
            version_number=version_number,
            content=content,
            content_hash=content_hash,
            source=source_value,
            validation_status=validation_status,
            simulated=simulated,
            created_at=now,
        )

    def get_output_version(self, version_id: str) -> OutputVersion | None:
        row = self._fetchone("SELECT * FROM output_versions WHERE id = ?", (version_id,))
        return self._version(row) if row else None

    def list_output_versions(self, task_id: str) -> list[OutputVersion]:
        rows = self._fetchall(
            "SELECT * FROM output_versions WHERE task_id = ? ORDER BY version_number",
            (task_id,),
        )
        return [self._version(r) for r in rows]

    def latest_output_version(self, task_id: str) -> OutputVersion | None:
        row = self._fetchone(
            "SELECT * FROM output_versions WHERE task_id = ? ORDER BY version_number DESC LIMIT 1",
            (task_id,),
        )
        return self._version(row) if row else None

    # ------------------------------------------------------------ human review
    def add_human_review(
        self,
        task_id: str,
        version_id: str,
        content_hash: str,
        decision: str | HumanDecision,
        reviewer: str,
        actor: str,
        feedback: str = "",
    ) -> HumanReview:
        decision_value = HumanDecision(decision)
        review_id = str(uuid.uuid4())
        now = utcnow_iso()
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT INTO human_reviews
                   (id, task_id, version_id, content_hash, decision, feedback,
                    reviewer, actor, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    review_id,
                    task_id,
                    version_id,
                    content_hash,
                    decision_value.value,
                    feedback,
                    reviewer,
                    actor,
                    now,
                ),
            )
        return HumanReview(
            id=review_id,
            task_id=task_id,
            version_id=version_id,
            content_hash=content_hash,
            decision=decision_value,
            feedback=feedback,
            reviewer=reviewer,
            actor=actor,
            created_at=now,
        )

    def list_human_reviews(self, task_id: str) -> list[HumanReview]:
        rows = self._fetchall(
            "SELECT * FROM human_reviews WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        return [
            HumanReview(
                id=r["id"],
                task_id=r["task_id"],
                version_id=r["version_id"],
                content_hash=r["content_hash"],
                decision=HumanDecision(r["decision"]),
                feedback=r["feedback"],
                reviewer=r["reviewer"],
                actor=r["actor"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def latest_review_for_version(self, version_id: str) -> ApprovalRecord | None:
        row = self._fetchone(
            "SELECT * FROM human_reviews WHERE version_id = ? ORDER BY created_at DESC LIMIT 1",
            (version_id,),
        )
        if not row:
            return None
        version = self.get_output_version(version_id)
        return ApprovalRecord(
            id=row["id"],
            task_id=row["task_id"],
            version_id=row["version_id"],
            version_number=version.version_number if version else 0,
            content_hash=row["content_hash"],
            decision=HumanDecision(row["decision"]),
            feedback=row["feedback"],
            reviewer=row["reviewer"],
            actor=row["actor"],
            created_at=row["created_at"],
        )

    # ---------------------------------------------------------------- evidence
    def add_evidence(
        self,
        task_id: str,
        output_version_id: str | None,
        claim_id: str,
        claim_text: str,
        file_id: str,
        filename: str,
        location: str,
        excerpt: str,
        status: str,
        evidence_id: str | None = None,
    ) -> str:
        evidence_id = evidence_id or str(uuid.uuid4())
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT INTO evidence_refs
                   (id, task_id, output_version_id, claim_id, claim_text, file_id,
                    filename, location, excerpt, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evidence_id,
                    task_id,
                    output_version_id,
                    claim_id,
                    claim_text,
                    file_id,
                    filename,
                    location,
                    excerpt,
                    status,
                    utcnow_iso(),
                ),
            )
        return evidence_id

    def list_evidence(self, task_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT * FROM evidence_refs WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------- audit
    def add_audit(
        self,
        task_id: str,
        event_type: str,
        actor: str,
        rule_id: str | None = None,
        detail: Any = "",
    ) -> str:
        audit_id = str(uuid.uuid4())
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT INTO audit_log
                   (id, task_id, event_type, actor, rule_id, detail, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    audit_id,
                    task_id,
                    event_type,
                    actor,
                    rule_id,
                    sanitize_detail(detail),
                    utcnow_iso(),
                ),
            )
        return audit_id

    def list_audit(self, task_id: str) -> list[AuditEvent]:
        rows = self._fetchall(
            "SELECT * FROM audit_log WHERE task_id = ? ORDER BY created_at", (task_id,)
        )
        return [
            AuditEvent(
                id=r["id"],
                task_id=r["task_id"],
                event_type=r["event_type"],
                actor=r["actor"],
                rule_id=r["rule_id"],
                detail=r["detail"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # --------------------------------------------------------------- workload
    def save_workload(self, metric: WorkloadMetric) -> None:
        with self._lock, self.conn:
            self.conn.execute(
                """INSERT INTO workload_metrics
                   (task_id, manual_minutes, elapsed_seconds, subtasks_completed,
                    revisions_requested, approval_outcome, quality_rating,
                    time_reduction_pct, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                     manual_minutes=excluded.manual_minutes,
                     elapsed_seconds=excluded.elapsed_seconds,
                     subtasks_completed=excluded.subtasks_completed,
                     revisions_requested=excluded.revisions_requested,
                     approval_outcome=excluded.approval_outcome,
                     quality_rating=excluded.quality_rating,
                     time_reduction_pct=excluded.time_reduction_pct""",
                (
                    metric.task_id,
                    metric.manual_minutes,
                    metric.elapsed_seconds,
                    metric.subtasks_completed,
                    metric.revisions_requested,
                    metric.approval_outcome,
                    metric.quality_rating,
                    metric.time_reduction_pct,
                    metric.created_at,
                ),
            )

    def get_workload(self, task_id: str) -> WorkloadMetric | None:
        row = self._fetchone(
            "SELECT * FROM workload_metrics WHERE task_id = ?", (task_id,)
        )
        if not row:
            return None
        return WorkloadMetric(
            task_id=row["task_id"],
            manual_minutes=row["manual_minutes"],
            elapsed_seconds=row["elapsed_seconds"],
            subtasks_completed=row["subtasks_completed"],
            revisions_requested=row["revisions_requested"],
            approval_outcome=row["approval_outcome"],
            quality_rating=row["quality_rating"],
            time_reduction_pct=row["time_reduction_pct"],
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------ stats
    def counts_by_status(self) -> dict[str, int]:
        rows = self._fetchall(
            "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status ORDER BY status"
        )
        return {r["status"]: int(r["n"]) for r in rows}

    def pending_approval_tasks(self, limit: int = 20) -> list[TaskRecord]:
        return self.list_tasks(limit=limit, status=TaskStatus.AWAITING_HUMAN_REVIEW.value)

    # ----------------------------------------------------------------- delete
    def delete_task(self, task_id: str) -> list[str]:
        """Delete a task and return stored file paths so the caller can unlink them."""
        files = self.list_files(task_id)
        paths = [f["stored_path"] for f in files if f.get("stored_path")]
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return paths

    # ----------------------------------------------------------------- helpers
    def _fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.conn.execute(sql, params).fetchall())

    @staticmethod
    def _task(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=row["id"],
            request=row["request"],
            output_format=row["output_format"],
            status=TaskStatus(row["status"]),
            simulated=bool(row["simulated"]),
            manual_minutes=row["manual_minutes"],
            elapsed_seconds=row["elapsed_seconds"],
            escalation_reason=row["escalation_reason"],
            current_version_id=row["current_version_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _version(row: sqlite3.Row) -> OutputVersion:
        return OutputVersion(
            id=row["id"],
            task_id=row["task_id"],
            version_number=int(row["version_number"]),
            content=row["content"],
            content_hash=row["content_hash"],
            source=OutputSource(row["source"]),
            validation_status=row["validation_status"],
            simulated=bool(row["simulated"]),
            created_at=row["created_at"],
        )
