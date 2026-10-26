"""Workflow view: agent hierarchy, routing log, and task evidence."""

from __future__ import annotations

import streamlit as st

from ..metrics import build_workload_metric
from ..models import TaskStatus
from . import common, components, hierarchy, layout


def _pick_task(services):
    task = common.active_task(services.db)
    if task is not None:
        return task
    tasks = services.db.list_tasks(limit=20)
    if not tasks:
        return None
    task = tasks[0]
    st.session_state["active_task_id"] = task.id
    return task


def _details(db, task, state) -> None:
    plan = state.get("plan") or {}
    if plan:
        st.markdown(f"**Plan:** {plan.get('task_type', '—')} · {plan.get('objective', '')}")
        for item in plan.get("missing_information") or []:
            st.warning(f"Missing information: {item}")
    policy = state.get("policy_report") or {}
    review = state.get("review_result") or {}
    claims = state.get("claims") or []
    evidence = state.get("evidence") or []
    col1, col2, col3 = st.columns(3)
    col1.metric("Quality checks", "PASS" if policy.get("passed") else "FAIL / not run")
    col2.metric("Reviewer", str(review.get("decision", "not run")).upper())
    col3.metric("Claims", f"{len(claims)} · {len(evidence)} evidence")
    draft = state.get("draft") or ""
    if draft:
        with st.expander("Draft preview (review before sharing)"):
            st.text_area("Draft", draft, height=300, disabled=True, label_visibility="collapsed")
    subtasks = db.list_subtasks(task.id)
    with st.expander("Subtasks"):
        if subtasks:
            st.dataframe(
                [
                    {
                        "Title": row["title"],
                        "Agent": row["assigned_agent"],
                        "Skill": row["skill"],
                        "Status": row["status"],
                        "Depends on": ", ".join(row.get("depends_on") or []),
                    }
                    for row in subtasks
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("No subtasks were created.")
    executions = db.list_agent_executions(task.id)
    with st.expander("Execution details"):
        if executions:
            st.dataframe(
                [
                    {
                        "Agent": row["agent"],
                        "Skill": row["skill"],
                        "Status": row["status"],
                        "Retries": row["retries"],
                        "Error class": row["error_class"] or "",
                        "Simulated": bool(row["simulated"]),
                        "Started": row["started_at"],
                    }
                    for row in executions
                ],
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("No execution details are available.")
    with st.expander("Activity log"):
        events = db.list_audit(task.id)
        st.dataframe(common.audit_rows(events), width="stretch", hide_index=True)
        st.caption(
            "Secrets and PII are redacted from this log. The draft shown on the review "
            "page is source-derived and may still contain personal data."
        )


def render(services) -> None:
    db = services.db
    workflow = services.workflow
    task = _pick_task(services)
    if task is None:
        layout.page_header("Workflow", "Follow progress and see what the agents did.")
        st.info("No tasks exist yet. Create one from **New task**.")
        if st.button("Create a task", type="primary"):
            common.navigate("New Task")
        return

    state = workflow.get_state(task.id)
    interrupted = workflow.is_interrupted(task.id)
    version = state.get("draft_version") or "—"
    review = state.get("review_result") or {}
    verdict = str(review.get("decision") or "not run").replace("_", " ").title()

    layout.page_header(
        f"Task {common.display_id(task.id)} · Workflow",
        f"{common.short_text(task.request, 120)} · Version {version} · Reviewer: {verdict}",
        right=lambda: components.render_badge(task.status),
    )
    meta_col, refresh_col = st.columns([5, 1], vertical_alignment="center")
    if refresh_col.button("Refresh", key="workflow-refresh"):
        st.rerun()
    elapsed = "—" if task.elapsed_seconds is None else f"{task.elapsed_seconds:.1f} s"
    meta_col.caption(f"Last update {task.updated_at} · Elapsed {elapsed}")
    if task.escalation_reason:
        st.error(f"Reason: {task.escalation_reason}", icon=":material/block:")

    left, right = st.columns([2.15, 1], gap="large")
    with left:
        with st.container(border=True, key="ag-card-hierarchy"):
            st.markdown('<div class="ag-card-title">Agent hierarchy</div>', unsafe_allow_html=True)
            executions = db.list_agent_executions(task.id)
            hierarchy.render(executions, task, state)
    with right:
        with st.container(border=True, key="ag-card-routing"):
            st.markdown('<div class="ag-card-title">Routing log</div>', unsafe_allow_html=True)
            hierarchy.routing_log(state)

    if interrupted and task.status == TaskStatus.AWAITING_HUMAN_REVIEW:
        layout.decision_card(
            "Needs your decision",
            f"Version {version} is waiting for a human decision. The approval gate is open.",
            "Review and approve",
            lambda: common.navigate("Review"),
        )
    elif task.status in {TaskStatus.APPROVED, TaskStatus.COMPLETED}:
        if st.button("Download approved files", type="primary"):
            common.navigate("History")
    elif task.status in {TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.REJECTED}:
        if st.button("Start a new task", type="primary"):
            common.navigate("New Task")
    elif task.status == TaskStatus.AWAITING_HUMAN_REVIEW and not interrupted:
        st.warning("No checkpoint interrupt was found for this review.", icon=":material/warning:")

    if task.status == TaskStatus.COMPLETED and task.manual_minutes:
        metric = build_workload_metric(db, task, approval_outcome="approved")
        st.metric("Time reduction vs. estimate", f"{metric.time_reduction_pct}%")

    with st.expander("Task details and audit"):
        _details(db, task, state)
