"""Assurance Team subgraph: Assurance Lead -> Policy Checker -> Reviewer."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from config import Settings

from ..agents.reviewer import run_reviewer
from ..database import Database
from ..governance.policy_checks import run_policy_checks
from ..models import AgentStatus, PolicyReport, utcnow_iso
from ..skills_loader import Skill
from ..state import TeamState
from .leads import assurance_lead, route_from_lead


def build_assurance_team(
    settings: Settings, db: Database, llm: Any, skills: dict[str, Skill]
):
    def policy_checker_node(state: dict[str, Any]) -> dict[str, Any]:
        documents = (state.get("documents") or {}).values()
        source_text = "\n".join(doc.get("text", "") for doc in documents)
        simulated = bool(state.get("simulated", settings.simulated))
        report: PolicyReport = run_policy_checks(
            draft=state.get("draft", ""),
            plan=state.get("plan"),
            claims=state.get("claims", []),
            source_text=source_text,
            simulated=simulated,
        )
        db.add_agent_execution(
            task_id=state["task_id"],
            agent="policy_checker",
            level=3,
            skill="quality-review",
            status=AgentStatus.COMPLETED.value,
            retries=0,
            simulated=simulated,
            input_ref=f"draft_chars={len(state.get('draft', ''))}",
            output_ref=f"passed={report.passed}; findings={len(report.findings)}",
        )
        db.add_audit(
            state["task_id"],
            "policy_check_completed",
            "system:policy_checker",
            "GR-02",
            f"passed={report.passed}; high={report.high_severity_count}; "
            f"checks={len(report.checks_run)}",
        )
        return {
            "policy_report": report.model_dump(mode="json"),
            "agent_results": list(state.get("agent_results") or [])
            + [
                {
                    "agent": "policy_checker",
                    "level": 3,
                    "skill": "quality-review",
                    "status": AgentStatus.COMPLETED.value,
                    "summary": (
                        "Policy checks passed."
                        if report.passed
                        else f"Policy checks failed with {report.high_severity_count} high finding(s)."
                    ),
                    "output": report.model_dump(mode="json"),
                    "claims": [],
                    "evidence": [],
                    "missing_information": [],
                    "uncertainty": [],
                    "error_class": "",
                    "retries": 0,
                    "simulated": False,
                    "started_at": utcnow_iso(),
                    "finished_at": utcnow_iso(),
                }
            ],
            "routing_log": list(state.get("routing_log") or [])
            + [
                {
                    "from_node": "policy_checker",
                    "to_node": "assurance_lead",
                    "reason": "Deterministic policy checks completed.",
                    "rule": "GR-02",
                    "depth": 3,
                }
            ],
            "updated_at": utcnow_iso(),
        }

    graph = StateGraph(TeamState)
    graph.add_node("assurance_lead", assurance_lead)
    graph.add_node("policy_checker", policy_checker_node)
    graph.add_node(
        "reviewer",
        lambda state: run_reviewer(
            state, settings=settings, llm=llm, db=db, skills=skills
        ),
    )
    graph.add_edge(START, "assurance_lead")
    graph.add_conditional_edges(
        "assurance_lead",
        route_from_lead,
        {
            "policy_checker": "policy_checker",
            "reviewer": "reviewer",
            END: END,
        },
    )
    graph.add_edge("policy_checker", "assurance_lead")
    graph.add_edge("reviewer", "assurance_lead")
    return graph.compile()
