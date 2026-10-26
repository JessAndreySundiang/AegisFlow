"""History: browse tasks, inspect decisions, export approved files, and delete."""

from __future__ import annotations

import html
import math

import streamlit as st

from ..approvals import ApprovalError
from ..document_processing import delete_task_files
from ..metrics import save_workload_metric
from ..models import TaskStatus
from ..services.export_service import export_markdown, export_txt, suggested_filename
from . import common, components, layout

OUTCOMES = ["approved", "rejected", "revision_requested", "unknown"]


def _version_number(db, task) -> int | None:
    versions = db.list_output_versions(task.id)
    return max((item.version_number for item in versions), default=None)


def _decision_text(task, version: int | None) -> str:
    if task.status in {TaskStatus.APPROVED, TaskStatus.COMPLETED}:
        return f"Approved v{version}" if version else "Approved"
    if task.status == TaskStatus.REJECTED:
        return f"Rejected v{version}" if version else "Rejected"
    if task.status == TaskStatus.AWAITING_HUMAN_REVIEW:
        return f"Pending v{version}" if version else "Pending"
    if task.status == TaskStatus.BLOCKED:
        return "Blocked"
    if task.status == TaskStatus.FAILED:
        return "Failed"
    return "—"


def _request_delete(task_id: str) -> None:
    st.session_state["delete_task_id"] = task_id


def _open_review(task_id: str) -> None:
    st.session_state["active_task_id"] = task_id
    st.session_state["page"] = "Review"


def _export_button(services, task, version: int | None) -> None:
    if task.status not in {TaskStatus.APPROVED, TaskStatus.COMPLETED}:
        if task.status in {TaskStatus.REJECTED, TaskStatus.BLOCKED, TaskStatus.FAILED}:
            st.button(
                "Delete",
                key=f"delete_{task.id}",
                on_click=_request_delete,
                args=(task.id,),
                width="stretch",
            )
        elif task.status == TaskStatus.AWAITING_HUMAN_REVIEW:
            st.button(
                "Review",
                key=f"review_{task.id}",
                on_click=_open_review,
                args=(task.id,),
                width="stretch",
            )
        else:
            st.caption("—")
        return
    current = services.db.get_output_version(task.current_version_id) if task.current_version_id else None
    if current is None:
        st.caption("No file")
        return
    try:
        if task.output_format == "markdown":
            data = export_markdown(services.db, task.id, current.id)
            label, suffix, mime = "Export .md", "md", "text/markdown"
        else:
            data = export_txt(services.db, task.id, current.id)
            label, suffix, mime = "Export .txt", "txt", "text/plain"
    except ApprovalError:
        st.caption("Export blocked")
        return
    st.download_button(
        label,
        data=data,
        file_name=suggested_filename(task, current, suffix),
        mime=mime,
        key=f"export_{task.id}",
        width="stretch",
    )


def _table(services, tasks) -> None:
    widths = [0.8, 1.8, 1.9, 1.1, 0.8, 1.4]
    with st.container(key="ag-history-head"):
        cols = st.columns(widths, gap="small")
        for col, label in zip(cols, ("Task", "Request", "Status", "Decision", "AI time", "Actions"), strict=True):
            col.markdown(label)
    for task in tasks:
        version = _version_number(services.db, task)
        with st.container(key=f"ag-history-row-{task.id}"):
            cols = st.columns(widths, gap="small", vertical_alignment="center")
            cols[0].markdown(
                f'<span class="ag-table__id">{html.escape(common.display_id(task.id))}</span>',
                unsafe_allow_html=True,
            )
            cols[1].markdown(
                f"<span>{html.escape(common.short_text(task.request, 80))}</span>",
                unsafe_allow_html=True,
            )
            with cols[2]:
                components.render_badge(task.status)
            cols[3].markdown(
                f'<span class="ag-table__muted">{html.escape(_decision_text(task, version))}</span>',
                unsafe_allow_html=True,
            )
            cols[4].markdown(
                f'<span class="ag-table__muted">{html.escape(common.format_minutes(task.elapsed_seconds))}</span>',
                unsafe_allow_html=True,
            )
            with cols[5]:
                _export_button(services, task, version)


def _render_workload(services, task) -> None:
    metric = services.db.get_workload(task.id)
    if metric is not None:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Manual estimate", f"{metric.manual_minutes or 0:g} min")
        col2.metric("Elapsed", "—" if metric.elapsed_seconds is None else f"{metric.elapsed_seconds:.1f} s")
        col3.metric("Time reduction", "—" if metric.time_reduction_pct is None else f"{metric.time_reduction_pct}%")
        col4.metric("Quality rating", metric.quality_rating or "—")
        st.caption("Time reduction compares elapsed time with your estimate. It is not a quality score.")
        return
    with st.form("workload_form"):
        outcome = st.selectbox(
            "Approval outcome",
            OUTCOMES,
            index=OUTCOMES.index("approved") if task.status == TaskStatus.COMPLETED else 0,
        )
        rating = st.slider("Your quality rating (not model-generated)", 1, 5, 4)
        submitted = st.form_submit_button("Save time estimate")
    if submitted:
        saved = save_workload_metric(services.db, task, approval_outcome=outcome, quality_rating=int(rating))
        st.info(
            f"Saved. Time reduction: {saved.time_reduction_pct}% "
            "(negative means slower than your estimate)."
        )
        st.rerun()


def _render_details(services, task) -> None:
    db = services.db
    st.markdown(f"**Request:** {task.request}")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption("Status")
        components.render_badge(task.status)
    col2.metric("Created", task.created_at.split("T")[0])
    col3.metric("Elapsed", "—" if task.elapsed_seconds is None else f"{task.elapsed_seconds:.1f} s")
    if task.escalation_reason:
        st.error(f"Reason: {task.escalation_reason}", icon=":material/block:")
    tabs = st.tabs(["Files", "Versions", "Decisions"])
    with tabs[0]:
        files = db.list_files(task.id)
        if files:
            st.dataframe(
                [{"File": row["filename"], "Status": row["status"], "Message": row["message"]} for row in files],
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("No files were uploaded for this task.")
    with tabs[1]:
        versions = db.list_output_versions(task.id)
        if versions:
            st.dataframe(
                [
                    {
                        "Version": version.version_number,
                        "Source": version.source.value,
                        "Simulated": version.simulated,
                        "Validation": version.validation_status,
                        "Created": version.created_at,
                    }
                    for version in versions
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("No output version was created.")
    with tabs[2]:
        reviews = db.list_human_reviews(task.id)
        if reviews:
            st.dataframe(
                [
                    {
                        "Time": review.created_at,
                        "Decision": review.decision.value,
                        "Reviewer": review.reviewer,
                        "Feedback": review.feedback,
                    }
                    for review in reviews
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("No human decision was recorded.")
    with st.expander("Activity log (technical)"):
        st.dataframe(common.audit_rows(db.list_audit(task.id)), width="stretch", hide_index=True)
    if task.status in {TaskStatus.APPROVED, TaskStatus.COMPLETED, TaskStatus.REJECTED}:
        st.subheader("Time saved")
        _render_workload(services, task)


@st.dialog("Delete task?")
def _delete_dialog(services, task) -> None:
    st.markdown(f"Permanently remove **{common.display_id(task.id)}**?")
    st.caption(common.short_text(task.request, 120))
    st.warning("This removes the task, its checkpoints, and its uploaded files.")
    confirm = st.checkbox("I understand this cannot be undone.", key=f"delete_confirm_{task.id}")
    col1, col2 = st.columns(2)
    if col1.button("Delete permanently", type="primary", disabled=not confirm, width="stretch"):
        paths = services.db.delete_task(task.id)
        removed = delete_task_files(paths)
        services.workflow.delete_thread(task.id)
        if st.session_state.get("active_task_id") == task.id:
            st.session_state["active_task_id"] = None
        st.session_state["delete_task_id"] = None
        common.set_flash(f"Deleted task and {removed} uploaded file(s).", "info")
        st.rerun()
    if col2.button("Cancel", width="stretch"):
        st.session_state["delete_task_id"] = None
        st.rerun()


def render(services) -> None:
    db = services.db
    selected = {"value": "all"}

    def filter_widget() -> None:
        selected["value"] = st.selectbox(
            "Filter by status",
            ["all"] + [status.value for status in TaskStatus],
            format_func=lambda value: "All statuses" if value == "all" else common.status_label(value),
            key="history_filter",
        )

    layout.page_header(
        "History",
        "Every decision and version is recorded. Approved exports stay available.",
        right=filter_widget,
    )
    status_filter = selected["value"]
    search = st.text_input(
        "Search tasks",
        placeholder="Task ID or request text",
        key="history_search",
    ).strip().lower()
    tasks = db.list_tasks(
        limit=100, status=None if status_filter == "all" else status_filter
    )
    if search:
        tasks = [
            task
            for task in tasks
            if search in common.display_id(task.id).lower()
            or search in (task.request or "").lower()
        ]
    total = len(tasks)
    per_page = 8
    pages = max(1, math.ceil(total / per_page))
    current = min(max(1, int(st.session_state.get("history_page", 1))), pages)
    st.session_state["history_page"] = current
    start = (current - 1) * per_page
    paged = tasks[start : start + per_page]
    with st.container(border=True, key="ag-card-history"):
        if paged:
            _table(services, paged)
        else:
            st.info("No tasks match this filter.")
    if total > per_page:
        prev_col, info_col, next_col = st.columns(
            [1, 3, 1], vertical_alignment="center"
        )
        if prev_col.button("Previous", disabled=current <= 1, width="stretch"):
            st.session_state["history_page"] = current - 1
            st.rerun()
        info_col.caption(f"Page {current} of {pages} · {total} tasks")
        if next_col.button("Next", disabled=current >= pages, width="stretch"):
            st.session_state["history_page"] = current + 1
            st.rerun()
    st.markdown(
        '<div class="ag-history-foot">Approved exports include approval details and are checked '
        "again each time. Rejected or blocked output cannot be exported.</div>",
        unsafe_allow_html=True,
    )

    if tasks:
        with st.expander("Task details and audit"):
            options = {
                f"{common.display_id(t.id)} · {common.short_text(t.request, 60)} · "
                f"{common.status_label(t.status)}": t.id
                for t in tasks
            }
            chosen = st.selectbox("Inspect a task", list(options.keys()))
            task = db.get_task(options[chosen])
            if task is not None:
                _render_details(services, task)

    delete_id = st.session_state.get("delete_task_id")
    if delete_id:
        task = db.get_task(delete_id)
        if task is None:
            st.session_state["delete_task_id"] = None
        else:
            _delete_dialog(services, task)
