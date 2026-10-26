"""Analysis Team subgraph: Analysis Lead -> Document Analyst -> Evidence Verifier."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from config import Settings

from ..agents.document_analyst import run_document_analyst
from ..agents.evidence_verifier import run_evidence_verifier
from ..database import Database
from ..skills_loader import Skill
from ..state import TeamState
from .leads import analysis_lead, route_from_lead


def build_analysis_team(
    settings: Settings, db: Database, llm: Any, skills: dict[str, Skill]
):
    graph = StateGraph(TeamState)
    graph.add_node("analysis_lead", analysis_lead)
    graph.add_node(
        "document_analyst",
        lambda state: run_document_analyst(
            state, settings=settings, llm=llm, db=db, skills=skills
        ),
    )
    graph.add_node(
        "evidence_verifier",
        lambda state: run_evidence_verifier(
            state, settings=settings, llm=llm, db=db, skills=skills
        ),
    )
    graph.add_edge(START, "analysis_lead")
    graph.add_conditional_edges(
        "analysis_lead",
        route_from_lead,
        {
            "document_analyst": "document_analyst",
            "evidence_verifier": "evidence_verifier",
            END: END,
        },
    )
    graph.add_edge("document_analyst", "analysis_lead")
    graph.add_edge("evidence_verifier", "analysis_lead")
    return graph.compile()
