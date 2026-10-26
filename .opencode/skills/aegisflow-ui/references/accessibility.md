# Accessibility

Target WCAG 2.2 AA. Accessibility is part of the design, not a final pass.

## Contrast

| Content | Minimum |
|---|---:|
| Body text on background | 4.5:1 |
| Large text (≥24px, or ≥18.66px bold) | 3.0:1 |
| UI borders, focus rings, icons | 3.0:1 |
| Disabled text | 3.0:1, and clearly marked disabled |

Check both light and dark themes. The measured AegisFlow values are in `design-tokens.md`; the lowest status text is 5.78:1 in light and 8.70:1 in dark.

Do not use green for anything except a recorded human approval. Do not use red for SIMULATED mode; use amber.

## Focus and keyboard

- Every interactive element is reachable by keyboard.
- `:focus-visible` shows a 2px solid ring with a 2px offset.
- Do not remove outlines or replace them with color alone.
- Dialogs trap focus and return it to the trigger on close.
- Tab order follows the visual order.
- The approval action is reachable without a mouse.

```css
:focus-visible {
  outline: 2px solid var(--ag-focus);
  outline-offset: 2px;
}
```

## Status and color

Status is always **icon + text label + color**. Color-blind users must still understand the state. Use distinct icon shapes, not only hue. A green badge must say “Approved”; an amber badge must say “Awaiting human review”.

Do not put status color on a table cell without a text label. In dataframes, keep the label in the cell and use a separate badge above the table when color is useful.

## Forms

- Every input has a visible label.
- Help text explains hashes, versions, and approval consequences.
- Errors identify the field and the fix.
- Required fields are marked in text, not only with color.
- The approval acknowledgement is a checkbox with a clear sentence.
- Reject and Delete require confirmation; rejection is terminal and must say so.

## Motion

- No decorative animation.
- Respect `prefers-reduced-motion`.
- Do not auto-play media.
- Progress indicators may animate only while work is running.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

## Zoom and text spacing

- Support 200% browser zoom without clipping or horizontal page scroll.
- Do not set fixed heights on text containers.
- Allow text to wrap; use `overflow-wrap: anywhere` for IDs and hashes.
- Keep touch targets at least 44px tall.
- Body text at least 16px with line height 1.5.

## Banners and live regions

The SIMULATED banner is persistent and must be visible on every screen. Use `role="status"` and `aria-live="polite"` for changes that appear after an action. Do not make every status badge a live region; that creates noise for screen-reader users.

## Themes

Test both `[theme.light]` and `[theme.dark]` with the Streamlit theme switcher, plus the system setting. `light-dark()` follows the `color-scheme` that Streamlit sets on `[data-testid="stApp"]`; do not hard-code a theme class.

## Evidence

- `scripts/check_contrast.py` prints PASS/FAIL for both themes.
- `scripts/check_theme.py` confirms both themes and font fallbacks.
- `scripts/check_responsive.py` checks widths and saves screenshots if Playwright is installed.
- State explicitly which checks were not run. Never claim a visual pass without evidence.
