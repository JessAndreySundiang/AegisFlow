"""Dashboard: status counts, recent tasks, workload, and the review queue."""

from __future__ import annotations

import streamlit as st

from ..models import TaskStatus
from . import common, components, layout


def _open_task(task_id: str, page: str = "Workflow") -> None:
    st.session_state["active_task_id"] = task_id
    common.navigate(page)


def _new_task() -> None:
    common.navigate("New Task")


def _version(db, task) -> str:
    versions = db.list_output_versions(task.id)
    return f"v{max(item.version_number for item in versions)}" if versions else "—"


def _review_meta(services, task) -> tuple[str, str]:
    try:
        state = services.workflow.get_state(task.id)
    except Exception:
        state = {}
    version = state.get("draft_version") or "—"
    review = state.get("review_result") or {}
    verdict = str(review.get("decision") or "pending").replace("_", " ").title()
    issues = len(review.get("issues") or [])
    meta = (
        f"{common.display_id(task.id)} · {common.short_text(task.request, 55)} · "
        f"Version {version} · Reviewer: {verdict}"
    )
    if issues:
        meta += f" with {issues} issue(s)"
    return f"Needs your decision", meta


def render(services) -> None:
    db = services.db
    counts = db.counts_by_status()
    total = sum(counts.values())
    awaiting = counts.get(TaskStatus.AWAITING_HUMAN_REVIEW.value, 0)
    completed = counts.get(TaskStatus.COMPLETED.value, 0)
    active = sum(
        counts.get(status.value, 0)
        for status in (
            TaskStatus.PENDING,
            TaskStatus.PLANNING,
            TaskStatus.IN_PROGRESS,
            TaskStatus.REVISION_REQUESTED,
        )
    )
    tasks = db.list_tasks(limit=5)

    layout.page_header(
        "Dashboard",
        "AI does the repetitive work. You approve every final output.",
        right=lambda: st.button("New task", type="primary", on_click=_new_task),
    )
    layout.metric_grid(
        [
            ("Total tasks", total, None),
            ("Active", active, None),
            ("Awaiting your review", awaiting, "warning"),
            ("Completed", completed, None),
        ]
    )

    recent, side = st.columns([2.35, 1], gap="large")
    with recent:
        with st.container(border=True, key="ag-card-recent"):
            st.markdown('<div class="ag-card-title">Recent tasks</div>', unsafe_allow_html=True)
            if tasks:
                layout.task_table(
                    [
                        {
                            "id": common.display_id(task.id),
                            "request": common.short_text(task.request, 70),
                            "status": components.badge(task.status),
                            "version": _version(db, task),
                        }
                        for task in tasks
                    ]
                )
            else:
                st.info("No tasks yet. Create one to run the governed workflow.")
    with side:
        with st.container(border=True, key="ag-card-workload"):
            st.markdown('<div class="ag-card-title">Workload evaluation</div>', unsafe_allow_html=True)
            st.markdown(
                '<div class="ag-note">Estimates and measurements are labelled separately.</div>',
                unsafe_allow_html=True,
            )
            latest = next(
                (
                    task
                    for task in tasks
                    if task.manual_minutes is not None or task.elapsed_seconds is not None
                ),
                None,
            )
            manual = f"{latest.manual_minutes:g} min" if latest and latest.manual_minutes is not None else "—"
            ai_time = common.format_minutes(latest.elapsed_seconds) if latest else "—"
            st.markdown(
                f'<div class="ag-stat-label">Manual time (your estimate)</div>'
                f'<div class="ag-stat-value">{manual}</div>'
                f'<div class="ag-stat-label">AI-assisted time (measured)</div>'
                f'<div class="ag-stat-value">{ai_time}</div>'
                '<div class="ag-note">Measures time only, not quality.</div>',
                unsafe_allow_html=True,
            )

    pending = db.pending_approval_tasks(limit=1)
    if pending:
        task = pending[0]
        title, meta = _review_meta(services, task)
        layout.decision_card(
            title,
            meta,
            "Open review",
            lambda: _open_task(task.id, "Review"),
        )
