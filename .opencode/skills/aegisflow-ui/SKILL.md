---
name: aegisflow-ui
description: UI/UX design system and review workflow for building clean, responsive, accessible Streamlit and web interfaces with fixed color, font and spacing tokens, light and dark themes, and verification scripts. Use this whenever the user asks to design, build, style, theme, polish, review or fix any UI, dashboard, page layout, colors, fonts, typography, mobile or responsive behavior, dark mode or accessibility, even if they do not say "UI/UX". Includes AegisFlow patterns: status badges, agent cards, hierarchy view, approval bar.
---

# AegisFlow UI

Apply this skill to AegisFlow's Streamlit interface and to secondary HTML/CSS work. It fixes the visual system so screens match the five-page mockup and stay consistent, governed, and reviewable.

## When to use

Use for any request to design, build, style, theme, polish, review, or fix a UI, dashboard, layout, color, typography, spacing, responsiveness, dark mode, or accessibility issue.

## 5-step workflow

1. **Understand** — Identify the screen, the user's main task, and the one primary action. The five AegisFlow screens are Dashboard, New Task, Workflow, Review, History.
2. **Apply tokens** — Use only `references/design-tokens.md`. Do not invent colors, fonts, spacing, radii, or status colors. Do not add hex values to Python.
3. **Build native-first** — Prefer `.streamlit/config.toml` and native Streamlit elements. Add CSS only for what configuration cannot do, in `aegisflow/ui/styles.css`, `aegisflow/ui/app.css`, and `aegisflow/ui/mockup.css`, injected by `aegisflow/ui/theme.py`. Put reusable HTML in `components.py` and structured cards in `hierarchy.py`.
4. **Verify** — Run `scripts/check_theme.py`, `scripts/check_contrast.py`, `scripts/check_pages.py`, and `scripts/check_accessibility.py` when Playwright is installed; otherwise report the browser checks as NOT RUN.
5. **Review** — Walk `references/review-checklist.md`; report each item PASS/FAIL/not run. Do not claim visual or mobile checks that were not executed.

## Core visual system (mockup fidelity)

- **Deep ocean-navy sidebar**: `#0C1F31` base with a teal-tinted gradient (`#0C2033 → #0A1A2B → #0B2831`), never pure black; selected item uses a translucent teal wash plus a 3px teal edge.
- **Main surface**: Near-white `#F9FAFC` (`#F8FAFC`); dark mode surface `#0B1220` / `#121B2E`; subtle teal radial tint at the top-right of the canvas.
- **Bordered cards**: White `#FFFFFF` with subtle 1px border (`var(--ag-border-subtle)`), `12px` border radius, and a soft two-layer shadow.
- **Primary action**: Deep teal `#0E766D` (`#0F766E`) with white text, minimum `44px` target height.
- **Status pill rules**: Inline badge with SVG icon + text label + tinted background + border. Status is never conveyed by color alone.
- **Structured agent hierarchy**: Grouped cards from Level 0 (Authority: Governance rules, Human gate), Level 1 (Command: Planner, Orchestrator), Level 2 (Team leads: Analysis, Drafting, Assurance), down to Level 3 (Specialists: Document analyst, Evidence verifier, Report writer, Policy checker, Reviewer).
- **Two-column layouts**:
  - *Workflow*: Agent hierarchy on left (2.15x), Routing log on right (1x); collapsible expander for technical execution logs.
  - *Review*: Read-only draft and policy checks on left (2.1x); evidence list, decision form, and technical details on right (1x).
- **History table with per-row actions**:
  - Columnar layout (`Task`, `Request`, `Status`, `Decision`, `AI time`, `Actions`).
  - Approved tasks expose `Export .md` or `Export .txt`.
  - Rejected, blocked, or failed tasks expose `Delete` with an explicit confirmation dialog (`st.dialog`).
- **Strict safety and governance rules**:
  - **Green is reserved strictly for recorded human approval**. Agent "Done" and "Active" states use blue/teal (`#1D4ED8` / `#0F766E`), never green.
  - **SIMULATED mode** displays an amber banner (`#92400E` on `#FFF4E5`) on Dashboard, Workflow, and Review.
  - **Approval action** must name the exact version: e.g. `Approve version 1`.
  - Rejection and deletion require explicit confirmation checkboxes.

## Responsive and contrast requirements

- Responsive widths: 360, 768, 1280, 1536 px. No horizontal page scroll at 360 px.
- Interactive targets minimum 44 px.
- Body text at least 16 px; reading width max 70ch.
- Contrast: at least 4.5:1 for body text; at least 3:1 for large text and UI component borders; light and dark themes.

## Need X → read Y

| Need | Read |
|---|---|
| Colors, type, spacing, radius, statuses | `references/design-tokens.md` |
| Font pairing, scale, Streamlit font loading | `references/typography.md` |
| Breakpoints, stacking, tables, diagrams | `references/responsive.md` |
| Native-first Streamlit, CSS injection, components | `references/streamlit-patterns.md` |
| Contrast, focus, motion, non-color status | `references/accessibility.md` |
| Pass/fail UI review | `references/review-checklist.md` |
| Theme template | `assets/theme.config.toml` |
| CSS template | `assets/styles.css` |
| axe-core 4.10.2 (MPL-2.0, vendored) | `assets/axe.min.js` |

## Verification commands

```powershell
.\.venv\Scripts\python.exe .opencode\skills\aegisflow-ui\scripts\check_theme.py .streamlit\config.toml
.\.venv\Scripts\python.exe .opencode\skills\aegisflow-ui\scripts\check_contrast.py .streamlit\config.toml --css aegisflow\ui\styles.css
.\.venv\Scripts\python.exe .opencode\skills\aegisflow-ui\scripts\check_pages.py http://localhost:8501
.\.venv\Scripts\python.exe .opencode\skills\aegisflow-ui\scripts\check_accessibility.py http://localhost:8501
.\.venv\Scripts\python.exe -m pytest tests\ -q
```

The browser checks require Playwright (a dev dependency). If it is absent, report them as NOT RUN; do not claim they passed.
