"""Inject the shared AegisFlow design tokens and app component styles."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st

_CSS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _bundle() -> str:
    """Read CSS once; inject the full style block on every Streamlit rerun."""
    base = (_CSS_DIR / "styles.css").read_text(encoding="utf-8")
    app = (_CSS_DIR / "app.css").read_text(encoding="utf-8")
    mockup = (_CSS_DIR / "mockup.css").read_text(encoding="utf-8")
    return f"{base}\n\n/* AegisFlow app components */\n{app}\n\n/* Mockup components */\n{mockup}"


def inject_theme() -> None:
    """Load tokens, typography, status badges, and responsive layout rules."""
    st.markdown(f"<style>{_bundle()}</style>", unsafe_allow_html=True)
