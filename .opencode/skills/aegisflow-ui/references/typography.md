# Typography

Use one calm pairing: **Plus Jakarta Sans** for headings, **Inter** for body and controls, and **JetBrains Mono** for code, hashes, IDs, and evidence. The fallback stack keeps the app usable offline.

## Roles

| Role | Family | Weight | Size | Line height |
|---|---|---|---|---|
| H1 | Plus Jakarta Sans | 700 | `2rem` / 32px | 1.2 |
| H2 | Plus Jakarta Sans | 600 | `1.5rem` / 24px | 1.25 |
| H3 | Plus Jakarta Sans | 600 | `1.25rem` / 20px | 1.3 |
| Body | Inter | 400 | `1rem` / 16px | 1.5 |
| Small | Inter | 400–500 | `0.875rem` / 14px | 1.5 |
| Caption | Inter | 500 | `0.8125rem` / 13px | 1.4 |
| Code/hash | JetBrains Mono | 400–500 | `0.875rem` / 14px | 1.5 |

Use `clamp()` for H1/H2 in custom CSS, for example `clamp(1.75rem, 4vw, 2rem)`. Do not go below 16px for body copy.

## Streamlit configuration: Google-hosted fonts

This is the primary path used by `assets/theme.config.toml`. It requires internet access in the browser; the fallback stack is used if the font request fails.

```toml
[theme]
baseFontSize = 16
baseFontWeight = 400
font = "Inter:https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
headingFont = "Plus Jakarta Sans:https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700&display=swap, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
codeFont = "JetBrains Mono:https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap, ui-monospace, SFMono-Regular, Consolas, monospace"
codeFontSize = "0.875rem"
headingFontSizes = ["2rem", "1.5rem", "1.25rem", "1.125rem", "1rem", "0.875rem"]
headingFontWeights = [700, 600, 600, 600, 600, 600]
```

The documented Streamlit form is `<font name>:<url>`, followed by fallback families in the same comma-separated string. In Streamlit 1.66.1 the Google-hosted request loads correctly, but the computed CSS family resolves to `"Inter", "Source Sans", sans-serif`; the explicit fallback list is not preserved by Streamlit's resolver. `styles.css` therefore sets the full fallback stack on `[data-testid="stApp"]` and on headings/code. Font URLs are read from the browser, so a demo without internet still renders with that stack.

## Offline option: self-hosted fonts

Use this only when the demo machine may be offline. Place font files in `static/`, enable static serving, and declare each face under `[theme]`. `fontFaces` must not be placed under `[theme.light]` or `[theme.dark]`.

```toml
[server]
enableStaticServing = true

[theme]
font = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
headingFont = "Plus Jakarta Sans, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
codeFont = "JetBrains Mono, ui-monospace, SFMono-Regular, Consolas, monospace"

[[theme.fontFaces]]
family = "Inter"
url = "app/static/Inter-Regular.woff2"
weight = "400"
style = "normal"

[[theme.fontFaces]]
family = "Inter"
url = "app/static/Inter-SemiBold.woff2"
weight = "600"
style = "normal"
```

The self-hosted path is documented but **not tested** in this project because no font files were downloaded. Do not claim it works until the files are present and the app is visually checked.

## Rules

- Body copy is at least `1rem` (16px), line height at least `1.5`.
- Keep paragraphs at or below `70ch`; use `.ag-prose` or a constrained container.
- Use `600` for emphasis and headings; avoid faux-bold and weights below `400` for body text.
- Use `font-variant-numeric: tabular-nums` for metrics, hashes, and tables.
- Do not use all-caps for sentences; reserve uppercase for short eyebrow labels with `letter-spacing: 0.04em`.
- Do not use more than three font families.
- Never set a fixed height on a text container; allow text to wrap at 200% zoom.

## Verification

The configured font stack is parsed by `check_theme.py`. In Phase 2, a probe app verified `document.fonts.check()` is true for Inter, Plus Jakarta Sans, and JetBrains Mono, and that light/dark backgrounds switch between `#F8FAFC` and `#0B1220`. If a browser cannot reach Google Fonts, report the fallback, not a pass.
