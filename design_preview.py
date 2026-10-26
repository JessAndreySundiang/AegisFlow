"""AegisFlow design preview. No workflow logic is connected."""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
CSS_PATH = ROOT / ".opencode" / "skills" / "aegisflow-ui" / "assets" / "styles.css"

st.set_page_config(page_title="AegisFlow UI preview", layout="wide")

if not CSS_PATH.exists():
    st.error(f"Missing design tokens: {CSS_PATH}")
    st.stop()

PREVIEW_CSS = """
.preview-swatches { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: .75rem; }
.preview-swatch { display: grid; gap: .4rem; color: var(--ag-muted); font-size: .8125rem; }
.preview-swatch__chip { height: 2.75rem; border: 1px solid var(--ag-border-subtle); border-radius: 8px; }
.preview-swatch__chip--bg { background: var(--ag-bg); }
.preview-swatch__chip--surface { background: var(--ag-surface); }
.preview-swatch__chip--secondary { background: var(--ag-secondary); }
.preview-swatch__chip--text { background: var(--ag-text); }
.preview-swatch__chip--muted { background: var(--ag-muted); }
.preview-swatch__chip--primary { background: var(--ag-primary); }
.preview-swatch__chip--accent { background: var(--ag-accent); }
.preview-swatch__chip--border { background: var(--ag-border); }
.preview-swatch__chip--warning { background: var(--ag-warning); }
.preview-swatch__chip--success { background: var(--ag-success); }
.preview-swatch__chip--danger { background: var(--ag-danger); }
.preview-type { border: 1px solid var(--ag-border-subtle); border-radius: 12px; background: var(--ag-surface); overflow: hidden; }
.preview-type__row { display: grid; grid-template-columns: 6rem 1fr; gap: 1rem; align-items: baseline; padding: .75rem 1rem; }
.preview-type__row + .preview-type__row { border-top: 1px solid var(--ag-border-subtle); }
.preview-type__label { color: var(--ag-muted); font-size: .75rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.preview-type__h1 { font-family: var(--ag-font-heading); font-size: 2rem; font-weight: 700; line-height: 1.2; }
.preview-type__h2 { font-family: var(--ag-font-heading); font-size: 1.5rem; font-weight: 700; line-height: 1.25; }
.preview-type__h3 { font-family: var(--ag-font-heading); font-size: 1.25rem; font-weight: 600; line-height: 1.3; }
.preview-type__body { font-size: 1rem; line-height: 1.5; }
.preview-type__small { font-size: .875rem; line-height: 1.5; }
.preview-type__caption { color: var(--ag-muted); font-size: .8125rem; line-height: 1.5; }
.preview-type__code { font-family: var(--ag-font-code); font-size: .875rem; }
.preview-statuses { display: flex; flex-wrap: wrap; gap: .75rem; }
.st-key-ag-approval-bar { padding: 1rem; border: 1px solid var(--ag-border); border-radius: 12px; background: var(--ag-surface); }
.preview-approval__meta { color: var(--ag-muted); font-size: .875rem; margin-bottom: .75rem; }
.preview-section { margin: 1.5rem 0 .5rem; }
@media (max-width: 479.98px) { .preview-type__row { grid-template-columns: 1fr; gap: .25rem; } }
"""

st.markdown(f"<style>{CSS_PATH.read_text(encoding='utf-8')}{PREVIEW_CSS}</style>", unsafe_allow_html=True)

ICONS = {
    "pending": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 8v4l2.5 1.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    "active": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="12" r="1.8" fill="currentColor"/><circle cx="12" cy="12" r="1.8" fill="currentColor"/><circle cx="18" cy="12" r="1.8" fill="currentColor"/></svg>',
    "review": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6S2.5 12 2.5 12Z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
    "approved": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4.2 4.2L19 6.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "rejected": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
    "blocked": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2.8 20h18.4L12 3Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 9v5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17.2" r=".9" fill="currentColor"/></svg>',
}


def badge(status: str, label: str, icon_name: str) -> str:
    return f'<span class="ag-badge ag-status-{status}">{ICONS[icon_name]}<span>{html.escape(label)}</span></span>'


def agent_card() -> str:
    return f"""
<div class="ag-agent-card ag-agent-card--lead">
  <div style="display:flex; gap:.75rem; align-items:flex-start; justify-content:space-between; flex-wrap:wrap;">
    <div><div class="ag-eyebrow">Level 2 · Team lead</div>
      <h3 style="margin:.25rem 0 .125rem;">Research Lead</h3>
      <div class="ag-agent-card__meta">Deterministic routing · 3 executors selected</div>
    </div>{badge("active", "In progress", "active")}
  </div>
  <p class="ag-prose" style="margin:.75rem 0 0;">Selects the minimum executor set for the request and records why each agent was included.</p>
</div>"""


def hierarchy() -> str:
    return """
<div class="ag-hierarchy__wide">
<svg viewBox="0 0 920 380" role="img" aria-labelledby="hier-title">
  <title id="hier-title">AegisFlow agent hierarchy from authority to specialists</title>
  <style>
    .h-box { fill: var(--ag-surface); stroke: var(--ag-border); stroke-width: 1.5; }
    .h-lead { fill: var(--ag-secondary); }
    .h-text { fill: var(--ag-text); font-family: var(--ag-font-body); font-size: 14px; font-weight: 600; }
    .h-sub { fill: var(--ag-muted); font-family: var(--ag-font-body); font-size: 12px; }
    .h-line { stroke: var(--ag-border); stroke-width: 1.5; fill: none; }
  </style>
  <path class="h-line" d="M460 64V104M460 160V184H180V208M460 184V208M460 184H740V208M180 264V288H122V312M180 288H348V312M460 264V300H572V312M740 264V288H798V312"/>
  <rect class="h-box" x="320" y="8" width="280" height="56" rx="10"/><text class="h-text" x="460" y="31" text-anchor="middle">Root Orchestrator</text><text class="h-sub" x="460" y="49" text-anchor="middle">Level 0 · Authority</text>
  <rect class="h-box" x="320" y="104" width="280" height="56" rx="10"/><text class="h-text" x="460" y="127" text-anchor="middle">Planner</text><text class="h-sub" x="460" y="145" text-anchor="middle">Level 1 · Command</text>
  <rect class="h-box h-lead" x="60" y="208" width="240" height="56" rx="10"/><text class="h-text" x="180" y="231" text-anchor="middle">Research Lead</text><text class="h-sub" x="180" y="249" text-anchor="middle">Level 2 · Team lead</text>
  <rect class="h-box h-lead" x="340" y="208" width="240" height="56" rx="10"/><text class="h-text" x="460" y="231" text-anchor="middle">Writing Lead</text><text class="h-sub" x="460" y="249" text-anchor="middle">Level 2 · Team lead</text>
  <rect class="h-box h-lead" x="620" y="208" width="240" height="56" rx="10"/><text class="h-text" x="740" y="231" text-anchor="middle">Governance Lead</text><text class="h-sub" x="740" y="249" text-anchor="middle">Level 2 · Team lead</text>
  <rect class="h-box" x="20" y="312" width="205" height="48" rx="10"/><text class="h-text" x="122" y="333" text-anchor="middle">Extractor</text><text class="h-sub" x="122" y="350" text-anchor="middle">Level 3 · Specialist</text>
  <rect class="h-box" x="245" y="312" width="205" height="48" rx="10"/><text class="h-text" x="347" y="333" text-anchor="middle">Validator</text><text class="h-sub" x="347" y="350" text-anchor="middle">Level 3 · Specialist</text>
  <rect class="h-box" x="470" y="312" width="205" height="48" rx="10"/><text class="h-text" x="572" y="333" text-anchor="middle">Composer</text><text class="h-sub" x="572" y="350" text-anchor="middle">Level 3 · Specialist</text>
  <rect class="h-box" x="695" y="312" width="205" height="48" rx="10"/><text class="h-text" x="797" y="333" text-anchor="middle">Auditor</text><text class="h-sub" x="797" y="350" text-anchor="middle">Level 3 · Specialist</text>
</svg></div>
<div class="ag-hierarchy__narrow">
  <div class="ag-tier"><div class="ag-tier__label">Level 0 · Authority</div><strong>Root Orchestrator</strong></div>
  <div class="ag-tier"><div class="ag-tier__label">Level 1 · Command</div><strong>Planner</strong></div>
  <div class="ag-tier"><div class="ag-tier__label">Level 2 · Team leads</div><strong>Research Lead</strong> · <strong>Writing Lead</strong> · <strong>Governance Lead</strong></div>
  <div class="ag-tier"><div class="ag-tier__label">Level 3 · Specialists</div><strong>Extractor</strong> · <strong>Validator</strong> · <strong>Composer</strong> · <strong>Auditor</strong></div>
</div>"""


st.markdown('<div class="ag-page-header"><div class="ag-eyebrow">Design system preview</div><h1>AegisFlow UI</h1><p>Tokens, type, status semantics, agent cards, approval gate, and hierarchy. Preview only — no governance logic is connected.</p></div>', unsafe_allow_html=True)
st.markdown(f'<div class="ag-simulated" role="status" aria-live="polite">{ICONS["blocked"]}<div><strong>SIMULATED MODE</strong><br><span>No external provider is called. Outputs are scripted for demonstration.</span></div></div>', unsafe_allow_html=True)
st.caption("Use the app menu to switch Light or Dark. Tokens follow Streamlit's active color-scheme.")

st.subheader("Palette")
swatches = [("Background", "bg"), ("Surface", "surface"), ("Secondary", "secondary"), ("Text", "text"), ("Muted", "muted"), ("Primary", "primary"), ("Accent", "accent"), ("Border", "border"), ("Warning", "warning"), ("Success", "success"), ("Danger", "danger")]
st.markdown('<div class="preview-swatches">' + "".join(f'<div class="preview-swatch"><span class="preview-swatch__chip preview-swatch__chip--{key}" aria-hidden="true"></span><span>{label}</span></div>' for label, key in swatches) + "</div>", unsafe_allow_html=True)

st.subheader("Type scale")
rows = [("H1", "Governed document review", "h1"), ("H2", "Human approval gate", "h2"), ("H3", "Agent hierarchy", "h3"), ("Body", "The review stays open until a human records a decision.", "body"), ("Small", "Level 2 · Team lead · deterministic routing", "small"), ("Caption", "SIMULATED outputs are not provider-verified.", "caption"), ("Code", "sha256:7f3a…c19e", "code")]
st.markdown('<div class="preview-type">' + "".join(f'<div class="preview-type__row"><span class="preview-type__label">{label}</span><span class="preview-type__{key}">{html.escape(text)}</span></div>' for label, text, key in rows) + "</div>", unsafe_allow_html=True)

st.subheader("Status badges")
st.caption("Every status uses an icon and a label. Green is reserved for human approval.")
statuses = [("pending", "Pending", "pending"), ("active", "In progress", "active"), ("review", "Awaiting human review", "review"), ("approved", "Approved", "approved"), ("rejected", "Rejected", "rejected"), ("blocked", "Blocked", "blocked")]
st.markdown('<div class="preview-statuses">' + "".join(badge(*item) for item in statuses) + "</div>", unsafe_allow_html=True)

st.subheader("Agent card")
st.markdown(agent_card(), unsafe_allow_html=True)

st.subheader("Agent hierarchy")
st.caption("The wide SVG is replaced by stacked level cards below 768 px.")
st.markdown(hierarchy(), unsafe_allow_html=True)

st.subheader("Approval gate")
st.markdown('<div class="preview-approval__meta">Version 3 · Content hash <code>7f3a…c19e</code> · SIMULATED output<br>Approve names the exact version. Reject and Delete require confirmation.</div>', unsafe_allow_html=True)
with st.container(key="ag-approval-bar"):
    st.markdown('<div class="preview-approval__meta">Human decision required. The review cannot finalize without it.</div>', unsafe_allow_html=True)
    with st.container(horizontal=True, wrap=True, gap="small"):
        st.button("Approve version 3", type="primary", icon=":material/check_circle:")
        st.button("Reject", icon=":material/cancel:")
        st.button("Request revision", type="tertiary", icon=":material/edit:")

st.caption("Preview only. Approval, agent, and workflow logic are unchanged.")
