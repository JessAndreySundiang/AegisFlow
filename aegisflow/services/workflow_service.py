"""Streamlit-friendly workflow runner around the compiled LangGraph."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, Interrupt

from config import Settings
from ..database import Database
from ..graph.root import build_root_graph
from ..models import TaskStatus
from ..redaction import sanitize_detail
from ..skills_loader import Skill
from ..state import initial_state
from .llm_service import build_llm_service


@dataclass
class RunResult:
    events: list[dict[str, Any]] = field(default_factory=list)
    interrupted: bool = False
    interrupt_payload: dict[str, Any] | None = None
    status: str = ""
    next_nodes: tuple[str, ...] = ()

    @property
    def finished(self) -> bool:
        return not self.interrupted


def _summarize_update(update: Any) -> dict[str, Any]:
    if not isinstance(update, dict):
        return {"type": type(update).__name__}
    summary: dict[str, Any] = {}
    for key in (
        "status",
        "phase",
        "draft_version",
        "current_version_id",
        "current_content_hash",
        "escalation_reason",
        "blocked_reason",
        "next_action",
    ):
        if key in update and update[key] is not None:
            summary[key] = update[key]
    if "team_status" in update:
        summary["team_status"] = update["team_status"]
    if "routing_log" in update and update["routing_log"]:
        summary["routing"] = update["routing_log"][-1]
    if "agent_results" in update:
        summary["agents"] = [
            {
                "agent": item.get("agent"),
                "status": item.get("status"),
                "summary": str(item.get("summary", ""))[:200],
            }
            for item in update["agent_results"]
        ]
    if "errors" in update and update["errors"]:
        summary["errors"] = [
            {"agent": e.get("agent"), "error_class": e.get("error_class")}
            for e in update["errors"]
        ]
    return summary


class WorkflowService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        skills: dict[str, Skill],
        *,
        checkpointer: Any | None = None,
        llm: Any | None = None,
    ):
        self.settings = settings
        self.db = db
        self.skills = skills
        self._lock = threading.RLock()
        self._owns_connection = False
        if checkpointer is None:
            settings.ensure_directories()
            self._conn = sqlite3.connect(
                str(settings.checkpoint_db_path),
                check_same_thread=False,
                timeout=30.0,
            )
            checkpointer = SqliteSaver(self._conn)
            checkpointer.setup()
            self._owns_connection = True
        self.checkpointer = checkpointer
        self.llm = llm or build_llm_service(settings)
        self.graph = build_root_graph(settings, db, self.llm, skills, checkpointer)

    def _config(self, task_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": task_id},
            "recursion_limit": self.settings.recursion_limit,
        }

    def _consume(self, iterator) -> RunResult:
        events: list[dict[str, Any]] = []
        interrupt_payload: dict[str, Any] | None = None
        for chunk in iterator:
            if not isinstance(chunk, dict):
                events.append({"node": "event", "update": _summarize_update(chunk)})
                continue
            if "__interrupt__" in chunk:
                interrupts = chunk["__interrupt__"]
                if isinstance(interrupts, (list, tuple)) and interrupts:
                    value = interrupts[0]
                    if isinstance(value, Interrupt):
                        interrupt_payload = value.value if isinstance(value.value, dict) else {"value": value.value}
                    elif isinstance(value, dict):
                        interrupt_payload = value
                events.append({"node": "__interrupt__", "update": {"interrupted": True}})
                continue
            for node, update in chunk.items():
                events.append({"node": node, "update": _summarize_update(update)})
                if isinstance(update, dict):
                    for event in update.get("audit_events", []) or []:
                        events.append(
                            {
                                "node": "audit",
                                "update": {
                                    "event_type": event.get("event_type"),
                                    "rule_id": event.get("rule_id"),
                                    "detail": sanitize_detail(event.get("detail", "")),
                                },
                            }
                        )
        snapshot = None
        return RunResult(
            events=events,
            interrupted=interrupt_payload is not None,
            interrupt_payload=interrupt_payload,
            status="",
            next_nodes=(),
        )

    def start(
        self,
        task_id: str,
        request: str,
        output_format: str,
        files: list[dict[str, Any]],
        documents: dict[str, dict[str, Any]],
        manual_minutes: float | None = None,
    ) -> RunResult:
        state = initial_state(
            task_id=task_id,
            request=request,
            output_format=output_format,
            files=files,
            documents=documents,
            simulated=self.settings.simulated,
            max_revisions=self.settings.max_revisions,
            manual_minutes=manual_minutes,
        )
        with self._lock:
            result = self._consume(
                self.graph.stream(
                    state, self._config(task_id), stream_mode="updates"
                )
            )
        return self._with_snapshot(task_id, result)

    def resume(self, task_id: str, decision: dict[str, Any]) -> RunResult:
        with self._lock:
            result = self._consume(
                self.graph.stream(
                    Command(resume=decision),
                    self._config(task_id),
                    stream_mode="updates",
                )
            )
        return self._with_snapshot(task_id, result)

    def _with_snapshot(self, task_id: str, result: RunResult) -> RunResult:
        try:
            snapshot = self.graph.get_state(self._config(task_id))
            result.status = str((snapshot.values or {}).get("status", ""))
            result.next_nodes = tuple(snapshot.next or ())
        except Exception:
            pass
        if not result.status:
            task = self.db.get_task(task_id)
            result.status = task.status.value if task else ""
        return result

    def get_state(self, task_id: str) -> dict[str, Any]:
        try:
            snapshot = self.graph.get_state(self._config(task_id))
            return dict(snapshot.values or {})
        except Exception:
            return {}

    def is_interrupted(self, task_id: str) -> bool:
        try:
            snapshot = self.graph.get_state(self._config(task_id))
            return bool(snapshot.next)
        except Exception:
            return False

    def delete_thread(self, task_id: str) -> None:
        with self._lock:
            try:
                self.checkpointer.delete_thread(task_id)
            except Exception:
                pass

    def close(self) -> None:
        if self._owns_connection:
            try:
                self._conn.close()
            except Exception:
                pass
