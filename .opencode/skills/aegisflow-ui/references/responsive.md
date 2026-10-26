# Responsive layout

Design mobile-first, then add width. Required test widths: **360, 768, 1280, 1536 px**. At 360 px there must be no horizontal page scroll. Tables and code may scroll inside their own container.

## Breakpoints

| Name | Width | Behavior |
|---|---:|---|
| Small | `480px` | Single column; stacked actions |
| Medium | `768px` | Two-column forms; wide hierarchy switches on |
| Large | `1024px` | Sidebar plus main content; dashboards use grids |
| Wide | `1280px` | Content capped at 1240px; extra space stays empty |

## Rules

- Use `min-width: 0` on flex and grid children to prevent overflow.
- Use `max-width: 100%` on images, SVGs, cards, and tables.
- Use `overflow-wrap: anywhere` for task IDs, hashes, and filenames.
- Do not use fixed widths larger than `100%`.
- Do not hide page overflow to fake a pass. Fix the component that overflows.
- Touch targets are at least `44px` tall.
- Keep one primary action per view. Stack secondary actions below it on phones.

## Streamlit layout

In Streamlit 1.66.1, `st.columns(..., wrap=True)` is the default and stacks at **640px or narrower**. Do not rely on that alone for a seven-step workflow: it becomes a tall stack of small labels. For critical layouts, use `.ag-strip` or a keyed container with scoped CSS. If you need one scrolling row, pass `wrap=False` deliberately and contain it. Streamlit exposes keyed elements as `st-key-<key>`; verify this before relying on it.

```css
.st-key-ag-metrics [data-testid="stHorizontalBlock"] {
  flex-wrap: wrap;
  gap: 1rem;
}
.st-key-ag-metrics [data-testid="stColumn"] {
  flex: 1 1 160px;
  min-width: 0;
}
```

Prefer native `st.metric` with a custom grid wrapper for dashboards, or the `.ag-metrics` component. Do not use four `st.columns` at 360 px.

## Workflow strip

Replace seven fixed columns with a wrapping grid:

```css
.ag-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 9rem), 1fr));
  gap: 0.5rem;
}
```

Each step is a 44px target with icon, label, and status. At 360 px the grid becomes one or two columns; it never scrolls the page.

## Hierarchy view

Render two versions and switch with one media query. At **768px and wider**, show an inline SVG with `viewBox` and `width: 100%`. Below **768px**, show a vertical stack of tier cards.

```css
.ag-hierarchy__wide { display: block; }
.ag-hierarchy__narrow { display: none; }

@media (max-width: 767.98px) {
  .ag-hierarchy__wide { display: none; }
  .ag-hierarchy__narrow { display: grid; gap: 0.75rem; }
}
```

The narrow stack shows Level 0 Authority, Level 1 Command, Level 2 Team leads, and Level 3 Specialists. Do not scale the SVG down until it is unreadable.

## Tables and code

- Wrap custom tables in `.ag-table-wrap { overflow-x: auto; max-width: 100%; }`.
- `st.dataframe` already scrolls inside its own container; keep `width="stretch"`.
- `pre` blocks scroll horizontally; inline `code` wraps.
- Keep status text visible in table cells; do not rely on color.

## Approval bar

At 768 px and wider, show the approval bar as a horizontal card. Below 768 px, stack the metadata, decision control, and actions. The primary action is full width; secondary actions follow. Reject and Delete require a confirmation step at every width.

## Verification

Run `scripts/check_responsive.py` only if Playwright is installed. It checks `scrollWidth <= innerWidth` at 360, 768, 1280, and 1536 px and saves screenshots to `ui_checks/`. If Playwright is absent, report **NOT RUN**; do not install packages without approval.

A same-origin iframe at 360, 768, 1280, and 1536 px is a supplemental browser check: media queries use the iframe viewport, so inspect `documentElement.scrollWidth`, `stMain.scrollWidth`, and the hierarchy switch inside the frame. State that this is not a real-device test.
