"""AegisFlow Streamlit entry point.

Run:
    .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="AegisFlow",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="auto",
)

from aegisflow.ui.app_shell import main  # noqa: E402  (must follow set_page_config)

main()
