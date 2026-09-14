"""Browser evidence and playback checks for D-109; no inference."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("reports/hover_repeat_20260914/browser")
OUT.mkdir(parents=True, exist_ok=True)
checks = []
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1100})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8765/hover_repeat.html", timeout=60000)
    count = page.locator("#run option").count()
    assert count > 0
    for i in range(count):
        page.locator("#run").select_option(str(i))
        name = page.evaluate("run.name")
        for t in (0, 8, 60):
            row = page.evaluate(
                "t=>{pause();seek(nearest(t),false);return {name:run.name,t:current().t,error:document.querySelector('#error').innerText};}",
                t,
            )
            assert not row["error"]
            checks.append(row)
            page.wait_for_function(
                "document.querySelector('#drone').complete && document.querySelector('#drone').naturalWidth>0"
            )
            page.screenshot(path=str(OUT / f"{name}_{t}.png"))
        page.locator("#scrub").fill("0")
        page.locator("#scrub").dispatch_event("input")
        page.locator("#play").click()
        page.wait_for_function("Number(document.querySelector('#scrub').value)>0")
        page.locator("#play").click()
    page.locator("#run").select_option("2")
    for t in (11.2, 15.2, 18.95, 20, 22):
        page.evaluate("t=>{pause();seek(nearest(t),false);}", t)
        page.wait_for_function(
            "document.querySelector('#drone').complete && document.querySelector('#drone').naturalWidth>0"
        )
        page.screenshot(path=str(OUT / f"departure_{t}.png"))
    index = page.evaluate(
        "run.decisions.findIndex(d=>d.role==='policy' && d.recording?.id==='call-000030')"
    )
    assert index >= 0
    page.evaluate("i=>selectDecision(i,true)", index)
    assert page.locator("#requestImages img").count() == 1
    assert page.evaluate("run.decisions[selected].recording.observation_seq") == 380
    page.screenshot(path=str(OUT / "departure_exact_input.png"), full_page=True)
    assert not errors, errors
    browser.close()
(OUT / "CHECKS.json").write_text(
    json.dumps(
        {
            "checks": checks,
            "playbacks": count,
            "errors": errors,
            "departure_snapshots": 5,
            "exact_departure_input": "call-000030, obs 380",
        },
        indent=2,
    ),
    encoding="utf-8",
)
print(f"PASS: {len(checks)} seeks, {count} playbacks")
