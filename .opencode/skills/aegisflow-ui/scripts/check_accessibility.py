#!/usr/bin/env python3
"""axe-core WCAG 2.1 A/AA audit for every page in light and dark mode.

Usage:
    python check_accessibility.py http://localhost:8501
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PAGES = ("Dashboard", "New Task", "Workflow", "Review", "History")
AXE = Path(__file__).resolve().parents[1] / "assets" / "axe.min.js"
OUTPUT = Path("ui_checks") / "axe"
BLOCKING = {"critical", "serious"}
SCRIPT = """
async () => {
  const result = await axe.run(document, {
    runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']},
    resultTypes: ['violations'],
  });
  return result.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.length,
    samples: violation.nodes.slice(0, 3).map((node) => ({
      target: node.target,
      html: (node.html || '').slice(0, 140),
      summary: (node.failureSummary || '').slice(0, 300),
      data: (node.any && node.any[0] && node.any[0].data) || null,
    })),
  }));
}
"""


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


def click_nav(page, name: str) -> None:
    """Click a sidebar navigation button by name, ignoring in-page actions."""
    nav = page.locator(
        '[data-testid="stSidebar"] [data-testid="stButton"] button'
    ).filter(has_text=name).first
    nav.evaluate("el => el.click()")
    page.wait_for_timeout(1200)


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else "http://localhost:8501"
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP Playwright is not installed.")
        print("NOT RUN accessibility audit")
        return 0
    if not AXE.exists():
        print(f"FAIL missing axe-core at {AXE}")
        return 1

    OUTPUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for scheme in ("light", "dark"):
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.emulate_media(color_scheme=scheme)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_selector("h1", timeout=30_000)
            page.wait_for_timeout(900)
            page.add_script_tag(path=str(AXE))
            for name in PAGES:
                if name != "Dashboard":
                    click_nav(page, name)
                violations = page.evaluate(SCRIPT)
                blocking = [v for v in violations if v["impact"] in BLOCKING]
                failed += len(blocking)
                report = OUTPUT / f"{name.lower().replace(' ', '_')}_{scheme}.json"
                report.write_text(json.dumps(violations, indent=2), encoding="utf-8")
                detail = ", ".join(f"{v['id']} ({v['impact']}, {v['nodes']})" for v in blocking)
                print(
                    f"{'PASS' if not blocking else 'FAIL'} page={name} scheme={scheme} "
                    f"violations={len(violations)} blocking={len(blocking)}"
                    + (f" :: {detail}" if detail else "")
                )
                for violation in blocking:
                    for sample in violation["samples"]:
                        print(f"  target={sample['target']} summary={sample['summary'][:160]}")
            page.close()
        browser.close()
    print("RESULT", "PASS" if failed == 0 else "FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
