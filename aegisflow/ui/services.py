"""Cached application services shared by all Streamlit pages."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from config import Settings
from ..database import Database
from ..services.workflow_service import WorkflowService
from ..skills_loader import load_skills


@dataclass
class Services:
    settings: Settings
    db: Database
    workflow: WorkflowService


@st.cache_resource(show_spinner="Starting AegisFlow...")
def get_services() -> Services:
    """Build one process-wide stack (DB, skills, graph, checkpointer)."""
    settings = Settings.from_env()
    settings.ensure_directories()
    db = Database(settings.app_db_path)
    skills = load_skills(settings.skills_dir)
    workflow = WorkflowService(settings, db, skills)
    return Services(settings=settings, db=db, workflow=workflow)
