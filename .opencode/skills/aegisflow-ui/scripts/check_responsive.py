#!/usr/bin/env python3
"""Optional responsive check for AegisFlow.

Usage:
    python check_responsive.py http://localhost:8501
"""

from __future__ import annotations

import sys
from pathlib import Path

WIDTHS = (360, 768, 1280, 1536)
OUTPUT = Path("ui_checks")


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else "http://localhost:8501"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP Playwright is not installed.")
        print("NOT RUN responsive widths:", ", ".join(str(width) for width in WIDTHS))
        print("Install only with approval: pip install playwright && playwright install chromium")
        return 0

    OUTPUT.mkdir(exist_ok=True)
    ok = True
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 900})
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_selector("h1", timeout=30_000)
                page.wait_for_timeout(500)
                size = page.evaluate(
                    """() => ({
                        scrollWidth: document.documentElement.scrollWidth,
                        bodyWidth: document.body.scrollWidth,
                        innerWidth: window.innerWidth
                    })"""
                )
                passed = size["scrollWidth"] <= size["innerWidth"]
                ok = ok and passed
                print(
                    f"{'PASS' if passed else 'FAIL'} width={width} "
                    f"scrollWidth={size['scrollWidth']} "
                    f"bodyWidth={size['bodyWidth']} "
                    f"innerWidth={size['innerWidth']}"
                )
                screenshot = OUTPUT / f"width_{width}.png"
                page.screenshot(path=str(screenshot), full_page=True)
                print(f"SHOT {screenshot}")
            except Exception as exc:  # noqa: BLE001 - report the real browser error
                ok = False
                print(f"FAIL width={width}: {exc}")
            finally:
                page.close()
        browser.close()
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
