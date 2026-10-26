#!/usr/bin/env python3
"""Page sweep: every page at four widths, overflow check, screenshots.

Usage:
    python check_pages.py http://localhost:8501
"""

from __future__ import annotations

import sys
from pathlib import Path

WIDTHS = (360, 768, 1280, 1536)
PAGES = ("Dashboard", "New Task", "Workflow", "Review", "History")
OUTPUT = Path("ui_checks") / "pages"


def open_sidebar(page) -> None:
    for selector in (
        '[data-testid="stSidebarCollapsedControl"] button',
        '[data-testid="stSidebarCollapsedControl"]',
        'button[aria-label="Open sidebar"]',
    ):
        locator = page.locator(selector).first
        if locator.count():
            locator.evaluate("el => el.click()")
            page.wait_for_timeout(700)
            return


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else "http://localhost:8501"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP Playwright is not installed.")
        print("NOT RUN page sweep")
        return 0

    OUTPUT.mkdir(parents=True, exist_ok=True)
    ok = True
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_selector("h1", timeout=30_000)
            page.wait_for_timeout(900)
            for name in PAGES:
                if name != "Dashboard":
                    if width < 768:
                        open_sidebar(page)
                    page.get_by_role("button", name=name).first.evaluate(
                        "el => el.click()"
                    )
                    page.wait_for_timeout(1200)
                heading = page.locator("h1").first.inner_text()
                size = page.evaluate(
                    "() => ({s: document.documentElement.scrollWidth, "
                    "w: window.innerWidth})"
                )
                passed = size["s"] <= size["w"] and name.lower() in heading.lower()
                slug = name.lower().replace(" ", "_")
                shot = OUTPUT / f"{slug}_{width}.png"
                page.screenshot(path=str(shot), full_page=True)
                print(
                    f"{'PASS' if passed else 'FAIL'} page={name} width={width} "
                    f"h1={heading!r} scrollWidth={size['s']} innerWidth={size['w']}"
                )
                ok = ok and passed
            page.close()
        browser.close()
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
