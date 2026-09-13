"""Visual verification of the D-105 before/after flight debugger."""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("reports/aerialclaw_tools_20260913/browser")
OUT.mkdir(parents=True, exist_ok=True)
checks = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1720, "height": 1200})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8765/aerialclaw_tools.html", timeout=60000)
    assert page.locator("#run option").count() == 7
    for i in range(7):
        page.locator("#run").select_option(str(i))
        name = page.evaluate("run.name")
        for t in (0, 10, 60):
            data = page.evaluate(
                """t=>{pause();seek(nearest(t),false);return {
                run:run.name,t:current().t,error:document.querySelector('#error').innerText};}""",
                t,
            )
            assert not data["error"]
            page.wait_for_function(
                "document.querySelector('#drone').complete && document.querySelector('#drone').naturalWidth>0"
            )
            checks.append(data)
        page.screenshot(path=str(OUT / f"{name}_final.png"))
        page.locator("#scrub").fill("0")
        page.locator("#scrub").dispatch_event("input")
        page.locator("#play").click()
        page.wait_for_function("Number(document.querySelector('#scrub').value)>0")
        page.locator("#play").click()
        tool = page.evaluate("run.decisions.findIndex(d=>d.role==='perception')")
        if tool >= 0:
            page.evaluate("i=>{pause();selectDecision(i,true);}", tool)
            assert "Perception tool" in page.locator("#selection").inner_text()
            assert page.locator("#requestImages img").count() == 1
            assert page.evaluate("run.decisions[selected].recording.role") == "perception"
            assert page.evaluate(
                "run.decisions[selected].source_seq===run.decisions[selected].recording.observation_seq"
            )
            page.screenshot(path=str(OUT / f"{name}_tool.png"), full_page=True)
    assert not errors, errors
    (OUT / "CHECKS.json").write_text(
        json.dumps({"checks": checks, "playbacks": 7, "errors": errors}, indent=2), encoding="utf-8"
    )
    browser.close()
print("PASS: 21 timeline checks, 7 playbacks, exact perception images and source matches")
