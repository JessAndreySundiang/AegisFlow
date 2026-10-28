"""Prompt provenance.

Every stored draft should be traceable to the instruction set that produced it.
A prompt version is a short fingerprint of the exact system-prompt text sent to
a model; it is recorded next to each agent execution so a prompt edit shows up
in the audit trail instead of being invisible.

The fingerprint is a truncated SHA-256 prefix. It is an identifier, not a
signature: anyone who can edit the database can also write a different version.
"""

from __future__ import annotations

from .models import sha256_text

PROMPT_VERSION_LENGTH = 12


def prompt_fingerprint(system_prompt: str) -> str:
    """Return a stable 12-character fingerprint of the exact prompt text.

    Whitespace and casing are significant: any byte change yields a new version,
    so a cosmetic edit is visible rather than silently pooled with the previous
    prompt.
    """
    return sha256_text(system_prompt or "")[:PROMPT_VERSION_LENGTH]
