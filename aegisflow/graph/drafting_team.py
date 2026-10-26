"""Drafting Team subgraph: Drafting Lead -> Report Writer."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from config import Settings
from ..agents.report_writer import run_report_writer
from ..database import Database
from ..skills_loader import Skill
from ..state import TeamState
from .leads import drafting_lead, route_from_lead


def build_drafting_team(
    settings: Settings, db: Database, llm: Any, skills: dict[str, Skill]
):
    graph = StateGraph(TeamState)
    graph.add_node("drafting_lead", drafting_lead)
    graph.add_node(
        "report_writer",
        lambda state: run_report_writer(
            state, settings=settings, llm=llm, db=db, skills=skills
        ),
    )
    graph.add_edge(START, "drafting_lead")
    graph.add_conditional_edges(
        "drafting_lead",
        route_from_lead,
        {"report_writer": "report_writer", END: END},
    )
    graph.add_edge("report_writer", "drafting_lead")
    return graph.compile()
