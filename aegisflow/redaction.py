"""Best-effort secret/PII redaction for logs, audit records, and error text.

This is a mitigation, not a guarantee. Raw uploaded document text is never
written to the audit log. Regex detection can miss unusual identifiers; this
limitation is documented in the risk assessment.
"""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OPENROUTER_KEY", re.compile(r"\bsk-or-[A-Za-z0-9_-]{8,}\b")),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")),
    ("GOOGLE_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")),
    ("BEARER_TOKEN", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{10,}=*")),
    (
        "LABELED_SECRET",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"]?[^\s,'\"]{6,}"
        ),
    ),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    (
        "PHONE",
        re.compile(r"(?<!\d)(?:\+?63|0)\s?9\d{2}[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    ),
    (
        "CARD",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    ),
]


def redact_text(text: str) -> str:
    if not text:
        return ""
    redacted = str(text)
    for label, pattern in _PATTERNS:
        redacted = pattern.sub(f"[REDACTED:{label}]", redacted)
    return redacted


def sanitize_detail(detail: Any) -> str:
    """Return a bounded, redacted string suitable for an audit row."""
    if detail is None:
        return ""
    if isinstance(detail, str):
        text = detail
    elif isinstance(detail, (dict, list, tuple)):
        import json

        try:
            text = json.dumps(detail, ensure_ascii=False, default=str)
        except Exception:
            text = str(detail)
    else:
        text = str(detail)
    return redact_text(text)[:4000]


_SECRET_LABELS = {"OPENROUTER_KEY", "OPENAI_KEY", "GOOGLE_KEY", "BEARER_TOKEN", "LABELED_SECRET"}


def find_secrets(text: str) -> list[str]:
    """Return labels of secret-like patterns found in text (not the values)."""
    if not text:
        return []
    labels: list[str] = []
    for label, pattern in _PATTERNS:
        if label in _SECRET_LABELS and pattern.search(text):
            labels.append(label)
    return sorted(set(labels))


def redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): redact_mapping(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_mapping(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_mapping(v) for v in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
