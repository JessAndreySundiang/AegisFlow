#!/usr/bin/env python3
"""WCAG contrast check for theme colors and AegisFlow CSS tokens.

Usage:
    python check_contrast.py .streamlit/config.toml
    python check_contrast.py .streamlit/config.toml --css aegisflow/ui/styles.css
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

TOKEN_RE = re.compile(
    r"--ag-([a-z0-9-]+):\s*light-dark\(\s*(#[0-9A-Fa-f]{6})\s*,\s*(#[0-9A-Fa-f]{6})\s*\)"
)
STATUS = ("pending", "active", "review", "approved", "rejected", "blocked")
REQUIRED = ("text", "muted", "bg", "surface", "border", "focus", "warning", "warning-bg")

def linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    text = hex_color.lstrip("#")
    red, green, blue = (int(text[index:index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def ratio(first: str, second: str) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def pair(label: str, foreground: str | None, background: str | None, minimum: float) -> bool:
    if not foreground or not background:
        print(f"FAIL {label}: missing color")
        return False
    value = ratio(foreground, background)
    ok = value >= minimum
    print(f"{'PASS' if ok else 'FAIL'} {label}: {value:.2f} (min {minimum})")
    return ok


def css_tokens(path: Path) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    return {
        name: {"light": light, "dark": dark}
        for name, light, dark in TOKEN_RE.findall(text)
    }


def config_checks(theme: dict, mode: str) -> bool:
    section = theme.get(mode)
    if not isinstance(section, dict):
        print(f"FAIL missing [theme.{mode}]")
        return False
    ok = True
    pairs = (
        ("textColor", "backgroundColor", 4.5),
        ("textColor", "secondaryBackgroundColor", 4.5),
        ("linkColor", "backgroundColor", 4.5),
        ("borderColor", "backgroundColor", 3.0),
        ("primaryColor", "backgroundColor", 3.0),
    )
    for foreground, background, minimum in pairs:
        ok = pair(
            f"{mode} {foreground} on {background}",
            section.get(foreground),
            section.get(background),
            minimum,
        ) and ok
    return pair(f"{mode} white on primaryColor", "#FFFFFF", section.get("primaryColor"), 4.5) and ok


def token_pair(label: str, tokens: dict, foreground: str, background: str, mode: str, minimum: float) -> bool:
    if foreground not in tokens or background not in tokens:
        print(f"FAIL {label}: missing token")
        return False
    return pair(label, tokens[foreground][mode], tokens[background][mode], minimum)


def token_checks(tokens: dict[str, dict[str, str]], mode: str) -> bool:
    if not tokens:
        print("SKIP CSS tokens: none found")
        return True
    missing = [name for name in REQUIRED if name not in tokens]
    if missing:
        print(f"FAIL CSS tokens missing: {', '.join(missing)}")
        return False
    ok = True
    for background in ("bg", "surface"):
        ok = token_pair(f"{mode} CSS muted on {background}", tokens, "muted", background, mode, 4.5) and ok
        ok = token_pair(f"{mode} CSS text on {background}", tokens, "text", background, mode, 4.5) and ok
        ok = token_pair(f"{mode} CSS border on {background}", tokens, "border", background, mode, 3.0) and ok
    ok = token_pair(f"{mode} CSS warning on warning-bg", tokens, "warning", "warning-bg", mode, 4.5) and ok
    ok = token_pair(f"{mode} CSS focus on bg", tokens, "focus", "bg", mode, 3.0) and ok
    for family in STATUS:
        ok = token_pair(
            f"{mode} CSS {family} status",
            tokens,
            f"status-{family}-fg",
            f"status-{family}-bg",
            mode,
            4.5,
        ) and ok
    return ok


def find_css(config: Path, explicit: str | None) -> Path | None:
    if explicit:
        return Path(explicit)
    sibling = config.with_name("styles.css")
    if sibling.exists():
        return sibling
    app_css = Path.cwd() / "aegisflow" / "ui" / "styles.css"
    return app_css if app_css.exists() else None


def main(argv: list[str]) -> int:
    args = argv[1:]
    css_arg = None
    if "--css" in args:
        index = args.index("--css")
        css_arg = args[index + 1] if index + 1 < len(args) else None
        del args[index:index + 2]
    config_path = Path(args[0]) if args else Path(".streamlit/config.toml")
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"FAIL cannot read {config_path}: {exc}")
        return 1
    theme = data.get("theme", {})
    ok = all([config_checks(theme, mode) for mode in ("light", "dark")])
    css_path = find_css(config_path, css_arg)
    if css_path and css_path.exists():
        print(f"CSS {css_path}")
        tokens = css_tokens(css_path)
        ok = all([token_checks(tokens, mode) for mode in ("light", "dark")]) and ok
    else:
        print("SKIP CSS tokens: no styles.css found (pass --css PATH)")
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
