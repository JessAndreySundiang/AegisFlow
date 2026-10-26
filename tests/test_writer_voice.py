"""Voice and page-awareness of the mock report writer."""

from __future__ import annotations

import re

from aegisflow.agents.report_writer import build_mock_draft

BANNED = (
    "finding(s)",
    "deliverable",
    "supplied document",
    "in conclusion",
    "it is important to note",
    "as an ai",
    "the document states",
)

PDF_CLAIMS = [
    {
        "id": "S1",
        "text": "Board Brief Revenue for the third quarter was PHP 4.2 million.",
        "status": "supported",
        "source_ref": "board_brief.pdf — page 1",
    },
    {
        "id": "S2",
        "text": "The board approved the 2027 plan on 9 October 2026.",
        "status": "supported",
        "source_ref": "board_brief.pdf — page 1",
    },
    {
        "id": "S3",
        "text": "Prepared by: Finance Office",
        "status": "supported",
        "source_ref": "board_brief.pdf — page 1",
    },
]


def _summary(draft: str) -> str:
    return draft.split("## Summary", 1)[1].split("##", 1)[0].strip()


def test_pdf_draft_reads_like_a_brief():
    draft = build_mock_draft(
        "Please prepare a meeting brief from this PDF.",
        "markdown",
        {"task_type": "meeting_brief"},
        PDF_CLAIMS,
        True,
    ).draft
    lowered = draft.lower()
    for phrase in BANNED:
        assert phrase not in lowered, phrase

    assert "**Source:** board_brief.pdf · 1 page" in draft

    summary = _summary(draft)
    assert "finding" not in summary.lower()
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", summary) if part.strip()]
    assert 2 <= len(sentences) <= 4
    assert all(len(sentence.split()) <= 30 for sentence in sentences)
    assert "[S1]" in summary and "4.2 million" in summary
    assert "approved the 2027 plan" in summary
    assert "What needs attention" in draft
    assert "[UNVERIFIED" not in draft


def test_unverified_draft_stays_honest_and_omits_attention():
    claims = [
        {
            "id": "S1",
            "text": "Prepared by: Finance Office",
            "status": "unverified",
            "source_ref": "notes.pdf — page 1",
        }
    ]
    draft = build_mock_draft(
        "Summarise this document.", "markdown", {"task_type": "summary"}, claims, True
    ).draft
    lowered = draft.lower()
    for phrase in BANNED:
        assert phrase not in lowered, phrase

    assert "Nothing in the source could be verified." in draft
    assert "finding" not in _summary(draft).lower()
    assert "What needs attention" not in draft
    assert "[UNVERIFIED: unverified]" in draft
