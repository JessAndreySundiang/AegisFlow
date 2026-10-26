# Design tokens

AegisFlow feels calm, trustworthy, and governed. Use navy neutrals with one teal accent, flat surfaces, thin borders, and no heavy shadows. These values are the only source of color, spacing, radius, and status meaning.

## Core palette

| Token | Light | Dark | Use |
|---|---|---|---|
| `bg` | `#F8FAFC` | `#0B1220` | App background |
| `surface` | `#FFFFFF` | `#121B2E` | Cards, panels, inputs |
| `secondary` | `#EEF2F7` | `#121B2E` | Sidebar, table headers |
| `text` | `#0F172A` | `#E6EDF7` | Body and headings |
| `muted` | `#475569` | `#9FB0C8` | Captions, metadata |
| `primary` | `#0F766E` | `#0F766E` | Native primary buttons |
| `on-primary` | `#FFFFFF` | `#FFFFFF` | Text on primary |
| `accent` | `#0F766E` | `#2DD4BF` | Links, focus, highlights |
| `border` | `#7C8EA8` | `#586E93` | Interactive borders, 3:1 |
| `border-subtle` | `#D5DCE6` | `#26324A` | Decorative card edges |
| `focus` | `#0F766E` | `#2DD4BF` | Focus ring |
| `warning` | `#92400E` | `#FCD34D` | SIMULATED and review notices |
| `warning-bg` | `#FFF4E5` | `#2A2113` | Warning banner background |
| `success` | `#166534` | `#86EFAC` | Human approved only |
| `danger` | `#991B1B` | `#FCA5A5` | Rejected or failed only |
| `info` | `#1D4ED8` | `#93C5FD` | In progress |
| `violet` | `#5B21B6` | `#C4B5FD` | Blocked or revision |

Green is reserved for a recorded human approval. Never use green as a general CTA, success decoration, or brand accent.

## Status tokens

Every status shows an icon, a text label, and color. Never rely on color alone.

| Status | Label | Icon (Material) | Light fg / bg / border | Dark fg / bg / border |
|---|---|---|---|---|
| `pending` | Pending | `circle` | `#334155` / `#EEF2F7` / `#7C8EA8` | `#C7D2E3` / `#1A2438` / `#9FB0C8` |
| `planning` | Planning | `route` | `#1D4ED8` / `#E8EEFF` / `#2563EB` | `#93C5FD` / `#12233F` / `#60A5FA` |
| `in_progress` | In progress | `progress_activity` | `#1D4ED8` / `#E8EEFF` / `#2563EB` | `#93C5FD` / `#12233F` / `#60A5FA` |
| `awaiting_human_review` | Awaiting human review | `hourglass_top` | `#92400E` / `#FFF4E5` / `#B45309` | `#FCD34D` / `#2A2113` / `#FBBF24` |
| `approved` | Approved | `check_circle` | `#166534` / `#E8F5EC` / `#15803D` | `#86EFAC` / `#12291B` / `#4ADE80` |
| `rejected` | Rejected | `cancel` | `#991B1B` / `#FDECEC` / `#B91C1C` | `#FCA5A5` / `#2A1517` / `#F87171` |
| `failed` | Failed / escalated | `report` | `#991B1B` / `#FDECEC` / `#B91C1C` | `#FCA5A5` / `#2A1517` / `#F87171` |
| `blocked` | Blocked | `error` | `#5B21B6` / `#F1EBFF` / `#6D28D9` | `#C4B5FD` / `#211A38` / `#A78BFA` |
| `revision_requested` | Revision requested | `edit_note` | `#5B21B6` / `#F1EBFF` / `#6D28D9` | `#C4B5FD` / `#211A38` / `#A78BFA` |
| `completed` | Completed | `task_alt` | `#166534` / `#E8F5EC` / `#15803D` | `#86EFAC` / `#12291B` / `#4ADE80` |

## Spacing and radius

| Token | Value |
|---|---|
| Space 1 | `4px` |
| Space 2 | `8px` |
| Space 3 | `12px` |
| Space 4 | `16px` |
| Space 6 | `24px` |
| Space 8 | `32px` |
| Space 12 | `48px` |
| Card radius | `12px` |
| Control radius | `8px` |
| Pill radius | `999px` |
| Touch target | `44px` minimum |
| Content width | `1240px` maximum |
| Reading width | `70ch` maximum |

## Contrast evidence

Measured with WCAG relative luminance:

| Pair | Light | Dark |
|---|---:|---:|
| Text on background | 17.06 | 15.89 |
| Muted text on background | 7.24 | 8.49 |
| Accent on background | 5.23 | 10.06 |
| Border on background | 3.19 | 3.63 |
| White on primary button | 5.47 | 5.47 |
| Lowest status text on badge | 5.78 | 8.70 |
| Warning text on banner | 6.52 | 10.99 |

## Rules

- Use `border` for interactive outlines and `border-subtle` for decorative card edges.
- Do not add hex values to Python; put colors in the token file and CSS variables.
- Do not use emoji as structural icons. Use Material Symbols or inline SVG.
- Do not use shadows for hierarchy; use spacing, borders, and type weight.
- Keep the page background flat; reserve tinted backgrounds for status and warnings.
