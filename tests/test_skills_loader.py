from pathlib import Path

import pytest

from aegisflow.skills_loader import (
    SkillError,
    agent_skill_names,
    load_skill,
    load_skills,
    render_agent_skills,
    skill_catalog,
    validate_plan_skills,
)

SKILLS = Path(__file__).resolve().parents[1] / "skills"


def test_loads_six_skills():
    skills = load_skills(SKILLS)
    assert len(skills) == 6
    assert set(skills) == {
        "task-planning",
        "document-extraction",
        "evidence-verification",
        "report-writing",
        "quality-review",
        "untrusted-content-handling",
    }


def test_agent_skill_mapping():
    skills = load_skills(SKILLS)
    assert "document-extraction" in agent_skill_names("document_analyst", skills)
    assert "untrusted-content-handling" in agent_skill_names("report_writer", skills)
    rendered = render_agent_skills("document_analyst", skills)
    assert "Document Extraction" in rendered
    assert "Untrusted Content Handling" in rendered


def test_catalog_and_unknown_skill():
    skills = load_skills(SKILLS)
    assert "task-planning" in skill_catalog(skills)
    assert validate_plan_skills(["not-a-skill"], skills) == ["not-a-skill"]


def test_missing_body_section_rejected(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text(
        "---\nname: x\ndescription: d\nowner_agent: planner\ninputs: [a]\noutputs: [b]\n---\n# X\n## Purpose\nx\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillError):
        load_skill(path)


def test_missing_frontmatter_rejected(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("# no frontmatter", encoding="utf-8")
    with pytest.raises(SkillError):
        load_skill(path)
