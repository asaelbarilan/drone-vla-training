"""Browser QA of grid/bbox inputs, diagnostic overlays and exact replies."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("reports/localization_formats_20260914/browser")
OUT.mkdir(exist_ok=True)
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1350, "height": 1100})
    page.on("pageerror", lambda e: errors.append(str(e)))
    response = page.goto("http://127.0.0.1:8766/localization_formats.html")
    assert response.status == 200
    assert page.locator("svg image").count() == 6
    page.screenshot(path=str(OUT / "comparison.png"), full_page=True)
    for case in ("visible_target", "hidden_openings", "close_wall"):
        page.locator("#" + case).screenshot(path=str(OUT / (case + ".png")))
    page.locator("#toggle").click()
    assert page.locator("body").get_attribute("class") == "hide"
    page.screenshot(path=str(OUT / "exact_inputs.png"), full_page=True)
    page.locator("#toggle").click()
    page.locator("details summary").first.click()
    assert page.locator("details").first.get_attribute("open") is not None
    assert not errors, errors
    browser.close()
(OUT / "CHECKS.json").write_text(
    json.dumps(
        dict(image_panels=6, overlay_toggle=True, prompt_expansion=True, errors=errors), indent=2
    ),
    encoding="utf-8",
)
print("PASS: six source panels, overlay toggle and prompt expansion")
