"""Tokenized presentation components: icon+text status badges."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

STATUS_LABELS = {
    "pending": "Pending", "planning": "Planning",
    "in_progress": "In progress", "blocked": "Blocked",
    "failed": "Failed", "awaiting_human_review": "Awaiting review",
    "revision_requested": "Revision requested", "approved": "Approved",
    "rejected": "Rejected", "completed": "Completed",
}

STATUS_CLASSES = {
    "pending": "pending", "planning": "active",
    "in_progress": "active", "blocked": "blocked",
    "failed": "rejected", "awaiting_human_review": "review",
    "revision_requested": "blocked", "approved": "approved",
    "rejected": "rejected", "completed": "approved",
}

STATUS_ICONS = {
    "pending": "clock", "planning": "route",
    "in_progress": "progress", "blocked": "alert",
    "failed": "alert", "awaiting_human_review": "eye",
    "revision_requested": "edit", "approved": "check",
    "rejected": "x", "completed": "check",
}
_ICONS = {
    "clock": '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
    "route": '<circle cx="12" cy="12" r="8"/><path d="m15 9-6 6 6-2-2-4Z"/>',
    "progress": '<path d="M12 3a9 9 0 1 0 9 9"/><path d="M12 7v5l3 2"/>',
    "eye": '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "x": '<path d="m6 6 12 12M18 6 6 18"/>',
    "ban": '<circle cx="12" cy="12" r="8"/><path d="m6.5 6.5 11 11"/>',
    "alert": '<path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5"/><circle cx="12" cy="17" r=".5" fill="currentColor" stroke="none"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/>',
    "dot": '<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>',
    "circle": '<circle cx="12" cy="12" r="8"/>',
}

def _value(status: Any) -> str:
    value = getattr(status, "value", status)
    return str(value or "pending")


def icon(name: str) -> str:
    body = _ICONS.get(name, _ICONS["circle"])
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


def status_label(status: Any) -> str:
    value = _value(status)
    return STATUS_LABELS.get(value, value.replace("_", " ").title())


def badge(status: Any, text: str | None = None, tone: str | None = None) -> str:
    value = _value(status)
    label = text or status_label(value)
    css_class = tone or STATUS_CLASSES.get(value, "pending")
    icon_name = STATUS_ICONS.get(value, "circle")
    return (
        f'<span class="ag-badge ag-status-{css_class}">{icon(icon_name)}'
        f"<span>{html.escape(label)}</span></span>"
    )


def render_badge(status: Any, text: str | None = None) -> None:
    st.markdown(badge(status, text), unsafe_allow_html=True)
