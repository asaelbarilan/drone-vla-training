"""Browser evidence and playback checks for D-110; no inference."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("reports/hover_stable_20260914/browser")
OUT.mkdir(parents=True, exist_ok=True)
checks = []
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1100})
    page.on("pageerror", lambda e: errors.append(str(e)))
    response = page.goto("http://127.0.0.1:8766/hover_stable.html", timeout=60000)
    assert response.status == 200, response.status
    page.wait_for_selector("#run option", state="attached", timeout=30000)
    count = page.locator("#run option").count()
    assert count > 0
    for i in range(count):
        page.locator("#run").select_option(str(i))
        name = page.evaluate("run.name")
        for t in (0, 8, 60):
            row = page.evaluate(
                "t=>{pause();seek(nearest(t),false);return {name:run.name,t:current().t,"
                "error:document.querySelector('#error').innerText};}",
                t,
            )
            assert not row["error"]
            checks.append(row)
            page.wait_for_function(
                "document.querySelector('#drone').complete && "
                "document.querySelector('#drone').naturalWidth>0"
            )
            page.screenshot(path=str(OUT / f"{name}_{t}.png"))
        if name.startswith("c5_hover_stable_"):
            index = page.evaluate(
                "run.decisions.findLastIndex(d=>d.role==='monitor' && d.recording)"
            )
            assert index >= 0
            page.evaluate("i=>selectDecision(i,true)", index)
            assert page.locator("#requestImages img").count() == 2
            page.screenshot(path=str(OUT / f"{name}_stop_input.png"), full_page=True)
        page.locator("#scrub").fill("0")
        page.locator("#scrub").dispatch_event("input")
        page.locator("#play").click()
        page.wait_for_function("Number(document.querySelector('#scrub').value)>0")
        page.locator("#play").click()
    assert not errors, errors
    browser.close()
(OUT / "CHECKS.json").write_text(
    json.dumps({"checks": checks, "playbacks": count, "errors": errors}, indent=2), encoding="utf-8"
)
print(f"PASS: {len(checks)} seeks, {count} playbacks")
