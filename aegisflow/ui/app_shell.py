"""Application shell: services, sidebar navigation, and page dispatch."""

from __future__ import annotations

import streamlit as st

from . import (
    common,
    dashboard,
    history_page,
    review_page,
    task_creation,
    theme,
    workflow_view,
)
from .services import get_services

RENDERERS = {
    "Dashboard": dashboard.render,
    "New Task": task_creation.render,
    "Workflow": workflow_view.render,
    "Review": review_page.render,
    "History": history_page.render,
}


def main() -> None:
    theme.inject_theme()
    common.init_state()
    services = get_services()
    common.render_sidebar(services)
    common.render_flash()

    page = st.session_state.get("page", "Dashboard")
    if page not in RENDERERS:
        page = "Dashboard"
        st.session_state["page"] = page
    if page in {"Dashboard", "Workflow", "Review"}:
        common.render_simulated_banner(services.settings)
    RENDERERS[page](services)
