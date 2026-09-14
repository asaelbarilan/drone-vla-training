"""Visual QA for the paired saved-frame report; no inference."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("reports/passage_choice_20260914/browser")
OUT.mkdir(exist_ok=True)
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1350, "height": 1150})
    page.on("pageerror", lambda e: errors.append(str(e)))
    response = page.goto("http://127.0.0.1:8766/passage_choice.html")
    assert response.status == 200
    page.wait_for_function(
        "document.querySelectorAll('canvas').length===6 && "
        "[...document.querySelectorAll('canvas')].every("
        "c=>c.getContext('2d').getImageData(0,0,1,1).data[3]>0)"
    )
    assert page.locator("section.panel").count() == 3
    page.screenshot(path=str(OUT / "paired.png"), full_page=True)
    for index, name in enumerate(("visible_target", "hidden_openings", "close_wall")):
        page.locator("section.panel").nth(index).screenshot(path=str(OUT / (name + ".png")))
    page.locator("#toggle").click()
    assert page.evaluate("overlays") is False
    page.screenshot(path=str(OUT / "unmodified_inputs.png"), full_page=True)
    page.locator("#toggle").click()
    assert page.evaluate("overlays") is True
    page.locator("details summary").first.click()
    assert page.locator("details").first.get_attribute("open") is not None
    assert not errors, errors
    browser.close()
(OUT / "CHECKS.json").write_text(
    json.dumps(
        dict(paired_images=6, rows=3, overlay_toggle=True, exact_prompt_expand=True, errors=errors),
        indent=2,
    ),
    encoding="utf-8",
)
print("PASS: six image panels, overlay toggle, exact prompt/reply expansion")
