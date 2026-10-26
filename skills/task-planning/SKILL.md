---
name: task-planning
description: Convert a natural-language request and file metadata into a validated, dependency-aware plan.
owner_agent: planner
inputs:
  - request
  - output_format
  - file_metadata
outputs:
  - plan
  - task_type
  - subtasks
  - required_skills
  - missing_information
  - clarification_questions
---

# Task Planning

## Purpose
Translate the user's request into the smallest correct plan. The plan decides
which specialist agents run; it must not invent work or data.

## Procedure
1. Identify the requested output: summary, report, meeting brief, outline, or action items.
2. Check whether the request requires documents. If it does and none were uploaded,
   set `missing_information` and return no executable subtasks.
3. Select only the executors needed:
   - summary: `document_analyst`
   - report or meeting brief: `document_analyst`, `evidence_verifier`, `report_writer`
   - outline: `document_analyst`, `report_writer`
   - action items: `document_analyst`, `evidence_verifier`, `report_writer`
4. Give each subtask a unique id, a title, a description, one assigned agent,
   one skill, and explicit dependencies.
5. List skills exactly as named in the skill catalog.
6. State missing information and clarification questions instead of guessing.

## Output format
Return JSON matching the `Plan` schema. Every subtask must reference a known
agent and skill. Dependencies must exist and must not form a cycle.

## Constraints
- Do not add web research, email, calendar, shell, or external actions.
- Do not plan around documents that are absent.
- Do not expand the user's scope.
- The plan is a proposal; validation code may reject it.

## Failure conditions
- Unknown agent or skill.
- Duplicate subtask id.
- Missing dependency or dependency cycle.
- Executable subtasks with no uploaded document when documents are required.

## Escalation
If the request is ambiguous or essential information is missing, return a plan
with `missing_information` and `clarification_questions`; the orchestrator will
block the task and ask the user.
