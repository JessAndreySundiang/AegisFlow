# Review checklist

Record **PASS**, **FAIL**, or **NOT RUN** for every item. A visual item is not PASS without a browser check or a script result.

## Foundation

- [ ] Only tokens from `design-tokens.md` are used.
- [ ] No hex colors in Python or component CSS outside the token file.
- [ ] Both `[theme.light]` and `[theme.dark]` are defined.
- [ ] Body, heading, and code fonts are set with fallbacks.
- [ ] Card radius is 12px; control radius is 8px.
- [ ] Borders use the 3:1 `border` token; decorative edges use `border-subtle`.

## Layout and responsive

- [ ] No horizontal page scroll at 360px.
- [ ] 768px, 1280px, and 1536px checked.
- [ ] Tables and code scroll inside their own containers.
- [ ] No fixed four- or seven-column layout on phones.
- [ ] Hierarchy uses SVG at ≥768px and stacked tier cards below 768px.
- [ ] Workflow strip wraps; it does not overflow.
- [ ] Approval bar stacks below 768px.
- [ ] Touch targets are at least 44px tall.

## Typography

- [ ] Body text is at least 16px.
- [ ] Body line height is at least 1.5.
- [ ] Reading width is at most 70 characters.
- [ ] Headings use Plus Jakarta Sans 600/700.
- [ ] Code, hashes, and IDs use JetBrains Mono with tabular numbers.
- [ ] No long all-caps sentences.
- [ ] Text wraps at 200% zoom.

## Color and contrast

- [ ] Text contrast is at least 4.5:1 in both themes.
- [ ] Large text and UI borders are at least 3:1 in both themes.
- [ ] Status text on badge backgrounds is at least 4.5:1.
- [ ] Green is used only for human-approved states.
- [ ] Amber is used for awaiting review and SIMULATED.
- [ ] Red is used only for rejected or failed states.
- [ ] `check_contrast.py` output is shown.

## Governance UX

- [ ] Every status has icon + text label + color.
- [ ] SIMULATED banner is visible on every screen.
- [ ] AI-finished work says “Awaiting human review” in amber.
- [ ] Approve action names the version, e.g. “Approve version 3”.
- [ ] Reject requires a confirmation step.
- [ ] Delete requires a confirmation step.
- [ ] Approval acknowledgement names the exact version and hash.
- [ ] No emoji is used as a structural icon.
- [ ] Approval, agent, graph, and database logic are unchanged.

## Interaction

- [ ] Exactly one primary button per view.
- [ ] Focus ring is visible and not removed.
- [ ] Keyboard reaches every action.
- [ ] Dialogs trap focus and close predictably.
- [ ] `prefers-reduced-motion` is respected.
- [ ] No decorative animation.
- [ ] Inputs have visible labels and helpful errors.
- [ ] Buttons are not icon-only unless the icon has an accessible label.

## Streamlit

- [ ] Only options present in Streamlit 1.66.1 are used.
- [ ] `width="stretch"` is used instead of deprecated width flags.
- [ ] CSS is cached on read and injected on every rerun.
- [ ] Selectors use stable `data-testid` or `st-key-*` classes, not emotion hashes.
- [ ] Dynamic HTML is escaped with `html.escape()`.
- [ ] `AppTest` covers the approval flow after label changes.

## Evidence

- [ ] `check_theme.py` output recorded.
- [ ] `check_contrast.py` output recorded.
- [ ] `check_responsive.py` output recorded, or NOT RUN with reason.
- [ ] `pytest tests/ -q` output recorded.
- [ ] Browser screenshots saved to `ui_checks/`, or visual check marked NOT RUN.
- [ ] Final report separates verified, unverified, and not implemented.
