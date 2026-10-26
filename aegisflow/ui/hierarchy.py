"""Agent hierarchy and routing log in the mockup's structured card layout."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from . import components

_GROUPS = (
    ("Level 0", "Authority", (("governance_rules", "Governance rules"), ("human_gate", "Human approval gate"))),
    ("Level 1", "Command", (("planner", "Planner"), ("orchestrator", "Orchestrator"))),
    ("Level 2", "Team leads", (("analysis_lead", "Analysis lead"), ("drafting_lead", "Drafting lead"), ("assurance_lead", "Assurance lead"))),
    ("Level 3", "Specialists", (("document_analyst", "Document analyst"), ("evidence_verifier", "Evidence verifier"), ("report_writer", "Report writer"), ("policy_checker", "Policy checker"), ("reviewer", "Reviewer"))),
)

_ACTIVE = {"planning", "in_progress", "revision_requested", "awaiting_human_review"}
_DONE = {"awaiting_human_review", "approved", "completed", "rejected", "blocked", "failed"}


def _badge(text: str, icon_value: str, tone: str) -> str:
    return components.badge(icon_value, text=text, tone=tone)


def _agent_badge(key: str, executions: dict[str, str], task, state: dict[str, Any]) -> str:
    task_status = getattr(task.status, "value", task.status)
    if key == "governance_rules":
        return _badge("Active", "in_progress", "active")
    if key == "human_gate":
        if task_status in {"approved", "completed"}:
            return _badge("Approved", "completed", "approved")
        if task_status == "rejected":
            return _badge("Rejected", "rejected", "rejected")
        if task_status == "awaiting_human_review":
            return _badge("Awaiting review", "awaiting_human_review", "review")
        return _badge("Not reached", "pending", "pending")
    if key == "planner":
        done = bool(state.get("plan") or state.get("subtask_status"))
        return _badge("Done", "completed", "active") if done else _badge("Pending", "pending", "pending")
    if key == "orchestrator":
        if task_status in _DONE:
            return _badge("Done", "completed", "active")
        if task_status in _ACTIVE:
            return _badge("Running", "in_progress", "active")
        return _badge("Pending", "pending", "pending")
    if key in {"analysis_lead", "drafting_lead", "assurance_lead"}:
        team = {
            "analysis_lead": ("document_analyst", "evidence_verifier"),
            "drafting_lead": ("report_writer",),
            "assurance_lead": ("policy_checker", "reviewer"),
        }[key]
        values = [executions.get(name, "") for name in team]
        if any(value == "failed" for value in values):
            return _badge("Failed", "failed", "rejected")
        if task_status in _DONE and any(values):
            return _badge("Done", "completed", "active")
        if task_status in _ACTIVE:
            return _badge("Running", "in_progress", "active")
        return _badge("Pending", "pending", "pending")
    if key == "reviewer" and state.get("review_result"):
        return _badge("Done", "completed", "active")
    if key == "policy_checker" and state.get("policy_report"):
        return _badge("Done", "completed", "active")
    value = executions.get(key, "")
    if value == "completed":
        return _badge("Done", "completed", "active")
    if value == "failed":
        return _badge("Failed", "failed", "rejected")
    if value == "running":
        return _badge("Running", "in_progress", "active")
    return _badge("Pending", "pending", "pending")


def render(executions: list[dict[str, Any]], task, state: dict[str, Any]) -> None:
    statuses = {row.get("agent", ""): row.get("status", "") for row in executions}
    rows = []
    for level, label, agents in _GROUPS:
        cards = "".join(
            f'<div class="ag-hier-card"><div class="ag-hier-card__name">{html.escape(name)}</div>'
            f"{_agent_badge(key, statuses, task, state)}</div>"
            for key, name in agents
        )
        rows.append(
            f'<div class="ag-hier-row"><div class="ag-hier-level">{level}'
            f"<span>{label}</span></div>"
            f'<div class="ag-hier-cards">{cards}</div></div>'
        )
    st.markdown(f'<div class="ag-hierarchy">{"".join(rows)}</div>', unsafe_allow_html=True)


def routing_log(state: dict[str, Any]) -> None:
    log = list(state.get("routing_log") or [])[-6:]
    if not log:
        st.markdown('<div class="ag-note">No routing decisions recorded yet.</div>', unsafe_allow_html=True)
        return
    items = []
    for index, item in enumerate(log, start=1):
        from_node = str(item.get("from_node", "system")).replace("_", " ").title()
        to_node = str(item.get("to_node", "next")).replace("_", " ").title()
        reason = html.escape(str(item.get("reason", "")))
        items.append(
            f'<div class="ag-routing__item"><div class="ag-routing__step">{index:02d}</div>'
            f'<div class="ag-routing__body"><strong>{html.escape(from_node)} → {html.escape(to_node)}</strong>'
            f"<br>{reason}</div></div>"
        )
    st.markdown(f'<div class="ag-routing">{"".join(items)}</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="ag-note" style="margin-top:.75rem">Failures escalate: worker → lead → Orchestrator → you.</div>',
        unsafe_allow_html=True,
    )
