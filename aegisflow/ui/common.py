"""Shared presentation helpers: navigation, banners, tables, and app version."""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from functools import lru_cache
from typing import Any

import streamlit as st

from config import PROJECT_ROOT, Settings

from ..models import TaskRecord, TaskStatus
from . import components

PAGES = ("Dashboard", "New Task", "Workflow", "Review", "History")
PAGE_LABELS = {"New Task": "New task"}

FLASH_LEVELS = {"success": "success", "warning": "warning", "error": "error", "info": "info"}


def init_state() -> None:
    st.session_state.setdefault("page", "Dashboard")
    st.session_state.setdefault("active_task_id", None)
    st.session_state.setdefault("reviewer_name", "Local Reviewer")
    st.session_state.setdefault("flash", None)


def set_flash(message: str, level: str = "success") -> None:
    st.session_state["flash"] = {"message": message, "level": FLASH_LEVELS.get(level, "info")}


def display_id(task_id: str | None) -> str:
    return f"T-{task_id[:4].upper()}" if task_id else "—"


def short_hash(value: str | None) -> str:
    return f"sha256 {value[:4]}…{value[-4:]}" if value else "sha256 —"


def format_minutes(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    return f"{max(1, round(seconds / 60))} min"


def render_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    renderer = getattr(st, flash.get("level", "info"), st.info)
    renderer(flash.get("message", ""))


def navigate(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


def status_label(status: str | TaskStatus) -> str:
    return components.status_label(status)


@lru_cache(maxsize=1)
def app_version() -> str:
    """Read the version from pyproject so the sidebar cannot drift."""
    try:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
            return str(tomllib.load(handle)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.6.0"


def active_task(db) -> TaskRecord | None:
    task_id = st.session_state.get("active_task_id")
    return db.get_task(task_id) if task_id else None


def short_text(text: str, limit: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_simulated_banner(settings: Settings) -> None:
    if settings.simulated:
        st.markdown(
            '<div class="ag-simulated" role="status">'
            "<strong>SIMULATED OUTPUT</strong> · Demo data from mock mode, not real AI analysis. "
            "No document leaves this machine.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info(
            f"**REAL MODE** — {settings.provider} / {settings.model}. "
            "Uploaded document text may be sent to the configured provider.",
            icon=":material/dns:",
        )
    if settings.fallback_reason:
        st.info(f"Provider fallback: {settings.fallback_reason}")


def _go_to(page: str) -> None:
    st.session_state["page"] = page


def render_sidebar(services) -> None:
    settings = services.settings
    with st.sidebar:
        st.markdown('<div class="ag-brand">AegisFlow</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="ag-flow-hint">Create → run → approve → export</div>',
            unsafe_allow_html=True,
        )
        page = st.session_state.get("page", "Dashboard")
        if page not in PAGES:
            page = "Dashboard"
            st.session_state["page"] = page
        awaiting = services.db.counts_by_status().get("awaiting_human_review", 0)
        for item in PAGES:
            label = PAGE_LABELS.get(item, item)
            if item == "Review" and awaiting:
                label = f"{label} · {awaiting}"
            st.button(
                label,
                key=f"nav_{item}",
                type="primary" if item == page else "secondary",
                on_click=_go_to,
                args=(item,),
                width="stretch",
            )
        mode = "Mock mode" if settings.simulated else "Real mode"
        st.markdown(
            f'<div class="ag-sidebar-footer"><span class="ag-mode-dot"></span>'
            f"{mode} · v{app_version()}</div>",
            unsafe_allow_html=True,
        )


def audit_rows(events: Iterable[Any]) -> list[dict[str, Any]]:
    return [
        {
            "Time": event.created_at,
            "Event": event.event_type,
            "Actor": event.actor,
            "Rule": event.rule_id or "",
            "Detail": event.detail,
        }
        for event in events
    ]
