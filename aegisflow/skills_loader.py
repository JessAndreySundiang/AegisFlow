"""Load SKILL.md files and inject their bodies into agent prompts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_FIELDS = {"name", "description", "owner_agent", "inputs", "outputs"}
REQUIRED_BODY_SECTIONS = (
    "Purpose",
    "Procedure",
    "Output format",
    "Constraints",
    "Failure conditions",
    "Escalation",
)
SHARED_SKILL = "untrusted-content-handling"

AGENT_SKILLS: dict[str, tuple[str, ...]] = {
    "planner": ("task-planning",),
    "document_analyst": ("document-extraction", SHARED_SKILL),
    "evidence_verifier": ("evidence-verification", SHARED_SKILL),
    "report_writer": ("report-writing", SHARED_SKILL),
    "reviewer": ("quality-review", SHARED_SKILL),
}


class SkillError(ValueError):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    owner_agent: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    body: str
    path: Path


def _split_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise SkillError(f"{path}: missing YAML frontmatter")
    try:
        _, frontmatter, body = text.split("---", 2)
    except ValueError as exc:
        raise SkillError(f"{path}: malformed frontmatter") from exc
    try:
        metadata = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as exc:
        raise SkillError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SkillError(f"{path}: frontmatter must be a mapping")
    return metadata, body.strip()


def load_skill(path: str | Path) -> Skill:
    path = Path(path)
    metadata, body = _split_frontmatter(path.read_text(encoding="utf-8"), path)
    missing = REQUIRED_FIELDS - set(metadata)
    if missing:
        raise SkillError(f"{path}: missing frontmatter fields: {sorted(missing)}")
    if not body:
        raise SkillError(f"{path}: skill body is empty")

    inputs = metadata["inputs"]
    outputs = metadata["outputs"]
    if not isinstance(inputs, list) or not all(isinstance(i, str) for i in inputs):
        raise SkillError(f"{path}: inputs must be a list of strings")
    if not isinstance(outputs, list) or not all(isinstance(i, str) for i in outputs):
        raise SkillError(f"{path}: outputs must be a list of strings")

    lower_body = body.lower()
    for section in REQUIRED_BODY_SECTIONS:
        if f"## {section.lower()}" not in lower_body:
            raise SkillError(f"{path}: missing body section '## {section}'")

    return Skill(
        name=str(metadata["name"]),
        description=str(metadata["description"]),
        owner_agent=str(metadata["owner_agent"]),
        inputs=tuple(inputs),
        outputs=tuple(outputs),
        body=body,
        path=path,
    )


def load_skills(skills_dir: str | Path) -> dict[str, Skill]:
    skills_dir = Path(skills_dir)
    if not skills_dir.is_dir():
        raise SkillError(f"Skills directory not found: {skills_dir}")
    skills: dict[str, Skill] = {}
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        skill = load_skill(path)
        if skill.name in skills:
            raise SkillError(f"Duplicate skill name: {skill.name}")
        skills[skill.name] = skill
    if not skills:
        raise SkillError(f"No SKILL.md files found in {skills_dir}")
    return skills


def agent_skill_names(
    agent: str, skills: dict[str, Skill] | None = None
) -> tuple[str, ...]:
    names = AGENT_SKILLS.get(agent, ())
    if skills is not None:
        unknown = [name for name in names if name not in skills]
        if unknown:
            raise SkillError(f"Agent {agent} references missing skills: {unknown}")
    return names


def render_agent_skills(
    agent: str, skills: dict[str, Skill], shared: bool = True
) -> str:
    names = list(agent_skill_names(agent, skills))
    if not shared:
        names = [n for n in names if n != SHARED_SKILL]
    return "\n\n".join(
        f"## Loaded skill: {name}\n\n{skills[name].body}" for name in names
    )


def skill_catalog(skills: dict[str, Skill]) -> str:
    lines = []
    for skill in skills.values():
        lines.append(f"- {skill.name} (owner: {skill.owner_agent}): {skill.description}")
    return "\n".join(lines)


def validate_plan_skills(plan_skills: list[str], skills: dict[str, Skill]) -> list[str]:
    """Return unknown skill names; an empty list means the plan is valid."""
    return sorted({name for name in plan_skills if name not in skills})
