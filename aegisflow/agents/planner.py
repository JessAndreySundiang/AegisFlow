"""Planner Agent: always the first LLM agent in the workflow."""

from __future__ import annotations

from typing import Any

from config import Settings

from ..agents.base import AgentFailure, call_agent, failure_result
from ..database import Database
from ..models import Plan, PlanSubtask, TaskStatus, utcnow_iso
from ..skills_loader import Skill, render_agent_skills, skill_catalog
from ..validation import ValidationError, validate_plan

SYSTEM_PROMPT = """You are the AegisFlow Planner.
Turn the user's request and file metadata into a minimal, dependency-aware plan.
You may select only these executors:
- document_analyst with skill document-extraction
- evidence_verifier with skill evidence-verification
- report_writer with skill report-writing

Rules:
1. If no readable document is supplied, return a plan with missing_information and
   no executable subtasks. Do not invent document content.
2. A summary uses document_analyst only.
3. A report, meeting brief, or action-items task uses document_analyst, then
   evidence_verifier, then report_writer.
4. An outline uses document_analyst, then report_writer.
5. Each subtask has a unique id, one agent, one matching skill, and explicit dependencies.
6. required_skills must list every skill used by a subtask.
7. Never add web research, email, shell, calendar, or external actions.
8. Return JSON only.
"""


def _task_type(request: str) -> str:
    text = request.lower()
    if "summary" in text or "summarize" in text or "summarise" in text:
        return "summary"
    if "brief" in text or "meeting" in text:
        return "meeting_brief"
    if "outline" in text:
        return "outline"
    if "action item" in text or "next steps" in text or "todo" in text:
        return "action_items"
    return "report"


def build_mock_plan(
    request: str,
    files: list[dict[str, Any]],
    output_format: str,
) -> Plan:
    readable = [f for f in files if f.get("status") == "ok"]
    task_type = _task_type(request)
    if not readable:
        messages = [
            f"{f.get('filename', 'file')}: {f.get('status')} - {f.get('message', '')}"
            for f in files
        ]
        return Plan(
            task_type=task_type,  # type: ignore[arg-type]
            objective=request.strip(),
            subtasks=[],
            required_skills=[],
            missing_information=[
                "No readable document was supplied. AegisFlow does not invent document data."
            ]
            + messages,
            clarification_questions=[
                "Please upload at least one readable PDF, TXT, or DOCX file."
            ],
            notes=["Deterministic mock planner: blocked because no readable input exists."],
        )

    if task_type == "summary":
        subtasks = [
            PlanSubtask(
                id="s1",
                title="Extract and summarize",
                description="Extract the key facts and produce a concise summary with references.",
                assigned_agent="document_analyst",
                skill="document-extraction",
            )
        ]
    elif task_type == "outline":
        subtasks = [
            PlanSubtask(
                id="s1",
                title="Extract source material",
                description="Extract facts and references from the documents.",
                assigned_agent="document_analyst",
                skill="document-extraction",
            ),
            PlanSubtask(
                id="s2",
                title="Build the outline",
                description="Organize the extracted material into the requested outline.",
                assigned_agent="report_writer",
                skill="report-writing",
                depends_on=["s1"],
            ),
        ]
    else:
        subtasks = [
            PlanSubtask(
                id="s1",
                title="Extract source findings",
                description="Extract facts, dates, names, requirements, and findings with references.",
                assigned_agent="document_analyst",
                skill="document-extraction",
            ),
            PlanSubtask(
                id="s2",
                title="Verify claims",
                description="Check every extracted claim against the source passages.",
                assigned_agent="evidence_verifier",
                skill="evidence-verification",
                depends_on=["s1"],
            ),
            PlanSubtask(
                id="s3",
                title="Write the deliverable",
                description="Write the requested document using only verified claims and clear gaps.",
                assigned_agent="report_writer",
                skill="report-writing",
                depends_on=["s2"],
            ),
        ]

    required_skills = []
    for subtask in subtasks:
        if subtask.skill not in required_skills:
            required_skills.append(subtask.skill)

    return Plan(
        task_type=task_type,  # type: ignore[arg-type]
        objective=request.strip(),
        subtasks=subtasks,
        required_skills=required_skills,
        missing_information=[],
        clarification_questions=[],
        notes=[
            "Deterministic mock plan. It chooses executors from the request type and "
            "does not call a remote model.",
            f"Output format requested: {output_format}.",
        ],
    )


def run_planner(
    state: dict[str, Any],
    *,
    settings: Settings,
    llm: Any,
    db: Database,
    skills: dict[str, Skill],
) -> dict[str, Any]:
    task_id = state["task_id"]
    request = state["request"]
    output_format = state.get("output_format", "markdown")
    files = state.get("files", [])
    readable = [f for f in files if f.get("status") == "ok"]

    payload = {
        "request": request,
        "output_format": output_format,
        "files": [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "pages": f.get("pages"),
                "message": f.get("message", ""),
            }
            for f in files
        ],
        "skill_catalog": skill_catalog(skills),
    }
    system_prompt = SYSTEM_PROMPT + "\n\n" + render_agent_skills("planner", skills)

    def validator(plan: Plan) -> None:
        errors = validate_plan(plan, skills, files)
        if errors:
            raise ValidationError("; ".join(errors))

    try:
        plan, retries = call_agent(
            agent="planner",
            schema=Plan,
            system_prompt=system_prompt,
            payload=payload,
            mock_builder=lambda: build_mock_plan(request, files, output_format),
            settings=settings,
            llm=llm,
            db=db,
            task_id=task_id,
            level=1,
            skill="task-planning",
            input_ref=f"files={len(files)}; readable={len(readable)}",
            validator=validator,
        )
    except AgentFailure as failure:
        db.add_audit(task_id, "planner_failed", "agent:planner", "GR-07", str(failure))
        db.transition_task(task_id, TaskStatus.FAILED, escalation_reason=str(failure))
        return {
            "status": TaskStatus.FAILED.value,
            "escalation_reason": str(failure),
            "agent_results": [
                failure_result(
                    agent="planner",
                    level=1,
                    skill="task-planning",
                    failure=failure,
                    simulated=settings.simulated,
                )
            ],
            "errors": [
                {
                    "agent": "planner",
                    "error_class": failure.error_class,
                    "message": str(failure),
                }
            ],
            "audit_events": [
                {
                    "event_type": "planner_failed",
                    "actor": "agent:planner",
                    "rule_id": "GR-07",
                    "detail": str(failure),
                }
            ],
            "updated_at": utcnow_iso(),
        }

    plan_dict = plan.model_dump(mode="json")
    subtask_status = {
        subtask.id: "pending"
        for subtask in plan.subtasks
    }
    for subtask in plan.subtasks:
        db.add_subtask(
            task_id=task_id,
            subtask_id=subtask.id,
            title=subtask.title,
            description=subtask.description,
            assigned_agent=subtask.assigned_agent,
            skill=subtask.skill,
            depends_on=subtask.depends_on,
            status="pending",
            required=subtask.required,
        )

    if plan.missing_information:
        reason = " ".join(plan.missing_information)
        db.add_audit(task_id, "plan_blocked", "agent:planner", "GR-02", reason)
        db.transition_task(task_id, TaskStatus.BLOCKED, escalation_reason=reason)
        return {
            "plan": plan_dict,
            "subtask_status": subtask_status,
            "status": TaskStatus.BLOCKED.value,
            "blocked_reason": reason,
            "phase": "blocked",
            "agent_results": [
                {
                    "agent": "planner",
                    "level": 1,
                    "skill": "task-planning",
                    "status": "completed",
                    "summary": "Plan blocked: missing information.",
                    "output": {"missing_information": plan.missing_information},
                    "claims": [],
                    "evidence": [],
                    "missing_information": plan.missing_information,
                    "uncertainty": [],
                    "error_class": "",
                    "retries": retries,
                    "simulated": settings.simulated,
                    "started_at": utcnow_iso(),
                    "finished_at": utcnow_iso(),
                }
            ],
            "audit_events": [
                {
                    "event_type": "plan_blocked",
                    "actor": "agent:planner",
                    "rule_id": "GR-02",
                    "detail": reason,
                }
            ],
            "updated_at": utcnow_iso(),
        }

    db.add_audit(
        task_id,
        "plan_created",
        "agent:planner",
        None,
        f"task_type={plan.task_type}; subtasks={len(plan.subtasks)}; retries={retries}",
    )
    db.transition_task(task_id, TaskStatus.IN_PROGRESS)
    return {
        "plan": plan_dict,
        "subtask_status": subtask_status,
        "status": TaskStatus.IN_PROGRESS.value,
        "phase": "analysis",
        "agent_results": [
            {
                "agent": "planner",
                "level": 1,
                "skill": "task-planning",
                "status": "completed",
                "summary": f"Planned {len(plan.subtasks)} subtask(s) for {plan.task_type}.",
                "output": plan_dict,
                "claims": [],
                "evidence": [],
                "missing_information": [],
                "uncertainty": [],
                "error_class": "",
                "retries": retries,
                "simulated": settings.simulated,
                "started_at": utcnow_iso(),
                "finished_at": utcnow_iso(),
            }
        ],
        "audit_events": [
            {
                "event_type": "plan_created",
                "actor": "agent:planner",
                "rule_id": None,
                "detail": f"task_type={plan.task_type}; subtasks={len(plan.subtasks)}",
            }
        ],
        "updated_at": utcnow_iso(),
    }
