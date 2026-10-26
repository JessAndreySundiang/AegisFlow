#!/usr/bin/env python3
"""Check AegisFlow theme completeness.

Usage:
    python check_theme.py .streamlit/config.toml
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

MODES = ("light", "dark")
CORE = (
    "primaryColor",
    "backgroundColor",
    "secondaryBackgroundColor",
    "textColor",
    "borderColor",
)
FONTS = ("font", "headingFont", "codeFont")
GENERIC = ("sans-serif", "serif", "monospace", "system-ui", "ui-monospace")


def fail(message: str) -> bool:
    print(f"FAIL {message}")
    return False


def passed(message: str) -> bool:
    print(f"PASS {message}")
    return True


def effective(theme: dict, key: str):
    if key in theme:
        return theme[key]
    for mode in MODES:
        section = theme.get(mode)
        if isinstance(section, dict) and key in section:
            return section[key]
    return None


def check_font(theme: dict, key: str) -> bool:
    value = effective(theme, key)
    if not isinstance(value, str) or not value.strip():
        return fail(f"missing [theme].{key}")
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) < 2:
        return fail(f"[theme].{key} has no comma-separated fallback")
    if not any(any(generic in part.lower() for generic in GENERIC) for part in parts[1:]):
        return fail(f"[theme].{key} has no generic fallback")
    return passed(f"[theme].{key} has a fallback stack")


def as_px(value) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        try:
            if text.endswith("px"):
                return float(text[:-2])
            if text.endswith("rem"):
                return float(text[:-3]) * 16
        except ValueError:
            return None
    return None


def check(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return fail(f"cannot read {path}: {exc}")

    theme = data.get("theme")
    if not isinstance(theme, dict):
        return fail("missing [theme]")

    ok = True
    for mode in MODES:
        section = theme.get(mode)
        if not isinstance(section, dict):
            ok = fail(f"missing [theme.{mode}]")
            continue
        for key in CORE:
            if key not in section:
                ok = fail(f"missing [theme.{mode}].{key}")
            else:
                passed(f"[theme.{mode}].{key}")

    for key in FONTS:
        ok = check_font(theme, key) and ok

    base_radius = effective(theme, "baseRadius")
    button_radius = effective(theme, "buttonRadius")
    if not base_radius:
        ok = fail("missing [theme].baseRadius")
    else:
        passed(f"[theme].baseRadius = {base_radius}")
    if not button_radius:
        ok = fail("missing [theme].buttonRadius")
    else:
        passed(f"[theme].buttonRadius = {button_radius}")

    size = as_px(effective(theme, "baseFontSize"))
    if size is None or size < 16:
        ok = fail(f"baseFontSize must be >= 16px, got {effective(theme, 'baseFontSize')!r}")
    else:
        passed(f"baseFontSize = {size:g}px")

    return ok


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path(".streamlit/config.toml")
    ok = check(path)
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
