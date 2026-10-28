"""Prompt provenance and readability: deterministic, offline, and honest."""

from __future__ import annotations

from aegisflow.metrics import readability
from aegisflow.prompts import PROMPT_VERSION_LENGTH, prompt_fingerprint


def test_prompt_fingerprint_is_stable_and_short():
    prompt = "You are a planner. Return a minimal plan."

    first = prompt_fingerprint(prompt)

    assert first == prompt_fingerprint(prompt)
    assert len(first) == PROMPT_VERSION_LENGTH
    assert all(character in "0123456789abcdef" for character in first)


def test_prompt_fingerprint_changes_on_any_edit():
    base = "Plan carefully."

    assert prompt_fingerprint(base) != prompt_fingerprint("Plan quickly.")
    # A whitespace-only edit is still a different prompt, not a silent no-op.
    assert prompt_fingerprint(base) != prompt_fingerprint(base + " ")
    assert prompt_fingerprint(base) != prompt_fingerprint(base.upper())


def test_prompt_fingerprint_handles_empty_prompt():
    assert prompt_fingerprint("") == prompt_fingerprint(None)
    assert len(prompt_fingerprint("")) == PROMPT_VERSION_LENGTH


def test_readability_is_none_without_words():
    assert readability("") is None
    assert readability(None) is None
    assert readability("---\n[S1]\n**\n") is None


def test_readability_is_deterministic():
    draft = "# Report\n\nThe team shipped the release on Friday. It passed every check."

    assert readability(draft) == readability(draft)


def test_readability_ignores_markdown_and_citation_markers():
    plain = readability("The team shipped the release on Friday.")
    decorated = readability("**The** team _shipped_ the release on Friday. [S1] [S2]")

    assert plain is not None and decorated is not None
    assert decorated.words == plain.words


def test_readability_counts_heading_text_as_prose():
    result = readability("## Report")

    assert result is not None
    assert result.words == 1


def test_readability_prefers_short_sentences():
    simple = readability("The cat sat. The dog ran. The sun was warm.")
    dense = readability(
        "Notwithstanding the aforementioned considerations, the comprehensive "
        "implementation necessitates further elaboration regarding multifaceted "
        "operational contingencies."
    )

    assert simple is not None and dense is not None
    assert simple.flesch > dense.flesch
    assert simple.label == "plain"


def test_readability_score_is_bounded_and_rounded():
    result = readability("Go.")

    assert result is not None
    assert 0.0 <= result.flesch <= 121.0
    assert result.score == int(round(result.flesch))
