# Streamlit patterns

Use this order: **configuration → native elements → scoped CSS → custom HTML**. Custom HTML is the last resort, not the first.

## Verified in Streamlit 1.66.1

| Feature | Status | Use |
|---|---|---|
| `[theme.light]` / `[theme.dark]` | Available | Both themes, user-switchable |
| `font`, `headingFont`, `codeFont` | Available | Google-hosted or fontFaces |
| `baseRadius`, `buttonRadius` | Available | 12px cards, 8px controls |
| `borderColor`, `showWidgetBorder` | Available | 3:1 interactive borders |
| `st.badge` | Available | Simple native labels |
| `st.html` | Available | Trusted HTML fragments |
| `st.dialog` | Available | Reject/Delete confirmation |
| `st.segmented_control` | Available | Decision selection |
| `width="stretch"` | Available | Buttons, dataframes, containers |
| `st.container(key=...)` | Available | Scoped CSS via `st-key-<key>` |

Check the installed version before using a new option or argument. Do not copy API names from older examples.

## Theme first

Put both themes in `.streamlit/config.toml`. A single `[theme]` locks the app to one mode; separate `[theme.light]` and `[theme.dark]` enable switching. Set fonts once in `[theme]`; `fontFaces` must also live in `[theme]`.

Use `primaryColor` for native primary buttons. In dark mode use `#0F766E`, not bright `#2DD4BF`: native buttons render white text, and white on bright teal fails contrast. Keep `#2DD4BF` for `linkColor`, focus, and accents.

## CSS injection

Cache the file read, but inject the style block on every rerun. Streamlit reruns the whole script, so a “once per session” flag would remove the CSS on the next interaction.

```python
from functools import lru_cache
import streamlit as st

@lru_cache(maxsize=1)
def _css() -> str:
    return Path(__file__).with_name("styles.css").read_text(encoding="utf-8")

def inject_theme() -> None:
    st.markdown(f"<style>{_css()}</style>", unsafe_allow_html=True)
```

Call `inject_theme()` once in the app shell. Do not inject the same block from every page.

## Theme-aware CSS

Streamlit 1.66.1 sets `color-scheme: light` or `dark` on `[data-testid="stApp"]` when the user switches themes. Use CSS `light-dark()` scoped to that element. Do not target generated emotion class names such as `st-emotion-cache-13k62yr`; they change with theme and version.

```css
[data-testid="stApp"] {
  --ag-bg: light-dark(#F8FAFC, #0B1220);
  --ag-text: light-dark(#0F172A, #E6EDF7);
}
```

`light-dark()` was verified in the installed browser against both Streamlit theme settings. Keep a light fallback for older browsers.

## Components

| Component | Approach |
|---|---|
| Status badge | Native `st.badge` where possible; custom HTML for token colors and SVG icons |
| Agent card | Custom HTML with escaped text; border-left for role, no shadow |
| SIMULATED banner | `role="status"`; amber tokens; visible on every screen |
| Approval bar | Native buttons in a keyed container; primary action names the version |
| Hierarchy view | Inline SVG at ≥768px; stacked tier cards below 768px |
| Metrics | `st.metric` in a wrapping grid, or custom `.ag-metric` cards |

## HTML safety

- Escape every dynamic value with `html.escape()` before inserting it into `st.markdown(..., unsafe_allow_html=True)`.
- Never put task text, filenames, reviewer names, or hashes into raw HTML unescaped.
- Do not add scripts, event handlers, or remote assets.
- Prefer `st.html` for static markup; use `st.markdown` when a `<style>` block is required.

## Buttons and forms

- Use `type="primary"` for exactly one action per view.
- Use `icon=":material/check_circle:"`, not emoji, for button icons.
- Name the approval action: `Approve version 3`.
- Reject and Delete need a second confirmation step, not just a red button.
- Keep approval logic intact: persist the decision, then resume the workflow.

## Testing

`AppTest` does not load CSS or browser fonts. Use it for behavior and labels, then run a browser or Playwright check for layout and contrast. Report **NOT RUN** when a visual check was not executed.
