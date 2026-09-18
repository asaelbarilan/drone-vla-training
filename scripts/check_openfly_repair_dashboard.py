"""Verify all 72 repaired cases and four model outputs in the live debugger."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_repair_20260918"
DATA = json.loads((ROOT / "reports/vla_dataset_review_20260916/openfly_repair.json").read_text())
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8771/openfly_repair.html")
    page.wait_for_function("document.querySelectorAll('#case option').length===72")
    assert page.locator("#scores tr").count() == 5
    assert page.locator("#controls tr").count() == 5
    for i, c in enumerate(DATA["cases"]):
        page.select_option("#case", str(i))
        shown = json.loads(page.locator("#provenance").text_content())
        assert shown["id"] == c["row"]["id"]
        page.wait_for_function(
            "Array.from(document.querySelectorAll('#images img'))"
            ".every(i=>i.complete&&i.naturalWidth>0)"
        )
        assert page.locator("#images img").count() == 3
        assert page.locator("#outputs pre").all_text_contents() == [
            x["raw"] for x in c["outputs"].values()
        ]
    page.select_option("#case", "12")
    page.screenshot(path=str(OUT / "dashboard_preview.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors
    browser.close()
(OUT / "browser_audit.json").write_text(
    json.dumps(
        dict(
            status="pass",
            cases=72,
            raw_outputs=288,
            model_rows=4,
            source_images_per_case=3,
            mobile_overflow=False,
            page_errors=errors,
        ),
        indent=2,
    )
)
print("72 cases, 288 raw outputs, desktop/mobile and image checks passed")
