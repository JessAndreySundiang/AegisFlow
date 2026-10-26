"""Render a stored Markdown draft as a readable document.

The stored string is never modified: the review page, export, and approval
hash all keep using the exact bytes. This module only changes presentation.
"""

from __future__ import annotations

import html
import re

import streamlit as st

from . import components

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*)$")
_CITE_RE = re.compile(r"\[(S\d+)\]")
_REQUEST_RE = re.compile(r"^\*\*Request:\*\*\s*(.*)$")
_SOURCE_RE = re.compile(r"^\*\*Source:\*\*\s*(.*)$")


def parse_draft(draft: str) -> tuple[str, str, list[tuple[str, str]]]:
    """Return (title, meta, [(section title, section body)])."""
    lines = draft.splitlines()
    title = ""
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            start = index + 1
            break
    body = "\n".join(lines[start:])
    matches = list(_SECTION_RE.finditer(body))
    meta = body[: matches[0].start()].strip() if matches else ""
    sections: list[tuple[str, str]] = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(body)
        sections.append((match.group(1).strip(), body[match.end() : end].strip()))
    return title, meta, sections


def _cite(text: str) -> str:
    """Escape untrusted text, then turn [S1] markers into styled chips."""
    escaped = html.escape(text)
    return _CITE_RE.sub(r'<span class="ag-cite">\1</span>', escaped)


def _items(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _ITEM_RE.match(stripped)
        items.append(match.group(1).strip() if match else stripped)
    return items


def _section(title: str) -> None:
    st.markdown(f'<h3 class="ag-draft__h">{html.escape(title)}</h3>', unsafe_allow_html=True)


def _list(items: list[str], css_class: str) -> None:
    if not items:
        st.markdown('<p class="ag-draft__meta">None recorded.</p>', unsafe_allow_html=True)
        return
    body = "".join(f"<li>{_cite(item)}</li>" for item in items)
    st.markdown(f'<ul class="{css_class}">{body}</ul>', unsafe_allow_html=True)


def render_draft(
    draft: str, *, simulated: bool | None = None, show_raw: bool = True
) -> None:
    title, meta, sections = parse_draft(draft)
    is_simulated = bool(simulated) or "SIMULATED OUTPUT" in draft
    badge = (
        components.badge("blocked", text="SIMULATED OUTPUT", tone="review")
        if is_simulated
        else components.badge("completed", text="Recorded draft", tone="approved")
    )
    st.markdown(
        f'<div class="ag-draft__head"><h2 class="ag-draft__title">'
        f"{html.escape(title or 'Draft')}</h2>{badge}</div>",
        unsafe_allow_html=True,
    )

    request = next(
        (match.group(1) for line in meta.splitlines() if (match := _REQUEST_RE.match(line))),
        "",
    )
    if request:
        st.markdown(
            f'<p class="ag-draft__meta">Request: {html.escape(request)}</p>',
            unsafe_allow_html=True,
        )
    source = next(
        (match.group(1) for line in meta.splitlines() if (match := _SOURCE_RE.match(line))),
        "",
    )
    if source:
        st.markdown(
            f'<p class="ag-draft__meta">Source: {html.escape(source)}</p>',
            unsafe_allow_html=True,
        )
    for line in meta.splitlines():
        if line.startswith(">"):
            st.markdown(
                f'<p class="ag-draft__meta">{html.escape(line.lstrip("> ").strip())}</p>',
                unsafe_allow_html=True,
            )

    for name, content in sections:
        lowered = name.lower()
        if "summary" in lowered:
            _section(name)
            paragraphs = [part.strip() for part in content.split("\n\n") if part.strip()]
            for paragraph in paragraphs or ["No summary was recorded."]:
                st.markdown(
                    f'<p class="ag-draft__lead">{_cite(paragraph)}</p>',
                    unsafe_allow_html=True,
                )
        elif "finding" in lowered:
            _section(name)
            _list(_items(content), "ag-draft__findings")
        elif "attention" in lowered:
            _section(name)
            _list(_items(content), "ag-draft__attention")
        elif "source" in lowered:
            _section(name)
            _list(_items(content), "ag-draft__sources")
        elif "limitation" in lowered or "unverified" in lowered:
            _section(name)
            _list(_items(content), "ag-draft__limits")
        else:
            _section(name)
            st.markdown(content)

    if show_raw:
        with st.expander("Raw Markdown (exact stored text)"):
            st.code(draft, language="markdown")
            st.caption("Approval binds to the hash of this exact text.")
