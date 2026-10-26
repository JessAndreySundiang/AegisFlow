"""Validation helpers for requests, plans, agent results, and routing."""

from __future__ import annotations

from typing import Any, Iterable

from .models import (
    AgentResult,
    AgentStatus,
    ErrorClass,
    Plan,
    PlanSubtask,
)
from .skills_loader import Skill, validate_plan_skills

AGENT_SKILL_PAIRS = {
    "document_analyst": "document-extraction",
    "evidence_verifier": "evidence-verification",
    "report_writer": "report-writing",
}
KNOWN_AGENTS = set(AGENT_SKILL_PAIRS)
OUTPUT_FORMATS = {"markdown", "txt"}


class ValidationError(ValueError):
    """A plan, request, result, or routing choice is invalid."""


def validate_request(
    request: str, output_format: str, files: list[dict[str, Any]] | None = None
) -> list[str]:
    errors: list[str] = []
    if not request or len(request.strip()) < 8:
        errors.append("Request must contain at least 8 characters.")
    if output_format not in OUTPUT_FORMATS:
        errors.append(f"Unsupported output format: {output_format}")
    files = files or []
    if files and not any(f.get("status") == "ok" for f in files):
        errors.append("No readable file was supplied.")
    return errors


def _topological_order(plan: Plan) -> list[PlanSubtask]:
    by_id = {subtask.id: subtask for subtask in plan.subtasks}
    ordered: list[PlanSubtask] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise ValidationError(f"Dependency cycle detected at subtask {node_id}")
        visiting.add(node_id)
        node = by_id[node_id]
        for dep in node.depends_on:
            if dep not in by_id:
                raise ValidationError(f"Subtask {node_id} depends on unknown {dep}")
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)
        ordered.append(node)

    for subtask_id in by_id:
        visit(subtask_id)
    return ordered


def validate_plan(
    plan: Plan | dict[str, Any],
    skills: dict[str, Skill],
    files: list[dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        plan_obj = plan if isinstance(plan, Plan) else Plan.model_validate(plan)
    except Exception as exc:
        return [f"Plan schema validation failed: {exc}"]

    if not plan_obj.objective.strip():
        errors.append("Plan objective is empty.")

    unknown_skills = validate_plan_skills(plan_obj.required_skills, skills)
    if unknown_skills:
        errors.append(f"Plan references unknown skills: {unknown_skills}")

    declared_skills = set(plan_obj.required_skills)
    for subtask in plan_obj.subtasks:
        if subtask.assigned_agent not in KNOWN_AGENTS:
            errors.append(f"Unknown agent: {subtask.assigned_agent}")
            continue
        expected = AGENT_SKILL_PAIRS[subtask.assigned_agent]
        if subtask.skill != expected:
            errors.append(
                f"Subtask {subtask.id}: agent {subtask.assigned_agent} must use "
                f"skill {expected}, got {subtask.skill}"
            )
        if subtask.skill not in declared_skills:
            errors.append(
                f"Subtask {subtask.id}: skill {subtask.skill} is missing from required_skills"
            )

    if plan_obj.subtasks:
        try:
            ordered = _topological_order(plan_obj)
        except ValidationError as exc:
            errors.append(str(exc))
            ordered = []
        completed: set[str] = set()
        for subtask in ordered:
            missing = [dep for dep in subtask.depends_on if dep not in completed]
            if missing:
                errors.append(
                    f"Subtask {subtask.id} has unmet dependencies: {missing}"
                )
            completed.add(subtask.id)

    readable_files = [f for f in (files or []) if f.get("status") == "ok"]
    if not readable_files and plan_obj.subtasks:
        if any(t.assigned_agent == "document_analyst" for t in plan_obj.subtasks):
            errors.append("A document-analysis subtask exists but no readable file was provided.")

    if plan_obj.missing_information and plan_obj.subtasks:
        errors.append("A blocked plan (missing information) must not contain executable subtasks.")

    if not plan_obj.missing_information and not plan_obj.subtasks:
        errors.append("A non-blocked plan must contain at least one subtask.")

    return errors


def ordered_subtasks(plan: Plan | dict[str, Any]) -> list[PlanSubtask]:
    plan_obj = plan if isinstance(plan, Plan) else Plan.model_validate(plan)
    return _topological_order(plan_obj)


def select_agents(plan: Plan | dict[str, Any]) -> list[str]:
    """Return unique executors in dependency order (no assurance agents)."""
    seen: list[str] = []
    for subtask in ordered_subtasks(plan):
        if subtask.assigned_agent not in seen:
            seen.append(subtask.assigned_agent)
    return seen


def select_skills(plan: Plan | dict[str, Any]) -> list[str]:
    skills: list[str] = []
    for subtask in ordered_subtasks(plan):
        if subtask.skill not in skills:
            skills.append(subtask.skill)
    return skills


def subtasks_for_agent(plan: Plan | dict[str, Any], agent: str) -> list[PlanSubtask]:
    return [s for s in ordered_subtasks(plan) if s.assigned_agent == agent]


def validate_agent_result(
    result: AgentResult | dict[str, Any], expected_agent: str
) -> list[str]:
    errors: list[str] = []
    try:
        result_obj = (
            result if isinstance(result, AgentResult) else AgentResult.model_validate(result)
        )
    except Exception as exc:
        return [f"Agent result schema validation failed: {exc}"]
    if result_obj.agent != expected_agent:
        errors.append(
            f"Agent result is from {result_obj.agent}, expected {expected_agent}"
        )
    if result_obj.status == AgentStatus.COMPLETED:
        if not result_obj.summary and not result_obj.output:
            errors.append("Completed agent returned no summary or output.")
    if result_obj.status == AgentStatus.FAILED and not result_obj.error_class:
        errors.append("Failed agent did not classify its error.")
    if result_obj.missing_information and result_obj.status == AgentStatus.COMPLETED:
        # Missing information may be reported while still completing an analysis;
        # the team lead decides whether the result is usable.
        pass
    return errors


def validate_routing_choice(choice: str, whitelist: Iterable[str]) -> str:
    allowed = set(whitelist)
    if choice not in allowed:
        raise ValidationError(
            f"Routing choice {choice!r} is not in the whitelist {sorted(allowed)}"
        )
    return choice


def classify_error(exc: BaseException) -> ErrorClass:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message or "rate" in message or "429" in message:
        return ErrorClass.TRANSIENT
    if "json" in name or "validation" in name or "parse" in name:
        return ErrorClass.MALFORMED_OUTPUT
    if "missing" in message or "not found" in message or "empty" in message:
        return ErrorClass.MISSING_INPUT
    if "approval" in message or "policy" in message:
        return ErrorClass.POLICY_VIOLATION
    if "key" in message or "config" in message or "credential" in message:
        return ErrorClass.CONFIGURATION
    return ErrorClass.UNKNOWN


def plan_needs_team(plan: Plan | dict[str, Any], team: str) -> bool:
    plan_obj = plan if isinstance(plan, Plan) else Plan.model_validate(plan)
    agents = {s.assigned_agent for s in plan_obj.subtasks}
    if team == "analysis":
        return bool(agents & {"document_analyst", "evidence_verifier"})
    if team == "drafting":
        return "report_writer" in agents
    return True
