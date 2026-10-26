"""Reusable page layout: header, metric cards, and compact task tables."""

from __future__ import annotations

import html
from collections.abc import Callable

import streamlit as st


def page_header(
    title: str,
    subtitle: str = "",
    right: Callable[[], None] | None = None,
) -> None:
    with st.container(key="ag-page-header"):
        left, right_col = st.columns([5, 2], vertical_alignment="center")
        with left:
            st.title(title)
            if subtitle:
                st.caption(subtitle)
        if right is not None:
            with right_col:
                with st.container(key="ag-header-actions"):
                    right()


def metric_grid(items: list[tuple[str, str | int, str | None]]) -> None:
    cards = []
    for label, value, tone in items:
        tone_class = f" ag-metric--{tone}" if tone else ""
        cards.append(
            f'<div class="ag-metric{tone_class}">'
            f'<div class="ag-metric__label">{html.escape(str(label))}</div>'
            f'<div class="ag-metric__value">{html.escape(str(value))}</div>'
            "</div>"
        )
    st.markdown(f'<div class="ag-metrics">{"".join(cards)}</div>', unsafe_allow_html=True)


def task_table(rows: list[dict[str, str]]) -> None:
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f'<td class="ag-table__id">{html.escape(row["id"])}</td>'
            f'<td class="ag-table__request">{html.escape(row["request"])}</td>'
            f"<td>{row['status']}</td>"
            f'<td class="ag-table__version">{html.escape(row["version"])}</td>'
            "</tr>"
        )
    st.markdown(
        '<div class="ag-table-wrap"><table class="ag-table">'
        "<thead><tr><th>Task</th><th>Request</th><th>Status</th>"
        '<th class="ag-table__version">Version</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def decision_card(
    title: str,
    meta: str,
    button_label: str,
    on_click: Callable[[], None],
) -> None:
    with st.container(border=True, key="ag-decision-card"):
        text, action = st.columns([4, 1], vertical_alignment="center")
        with text:
            st.markdown(
                f'<div class="ag-decision-card__text"><strong>{html.escape(title)}</strong>'
                f'<div class="ag-decision-card__meta">{html.escape(meta)}</div></div>',
                unsafe_allow_html=True,
            )
        with action:
            st.button(button_label, type="primary", on_click=on_click, width="stretch")
