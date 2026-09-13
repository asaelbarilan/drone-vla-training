"""Browser evidence and playback checks for D-107; no inference."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("reports/targeted_contracts_20260913/browser")
OUT.mkdir(parents=True, exist_ok=True)
checks = []
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1100})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8765/targeted_contracts.html", timeout=60000)
    assert page.locator("#run option").count() == 8
    for i in range(8):
        page.locator("#run").select_option(str(i))
        name = page.evaluate("run.name")
        for t in (0, 13.2, 60):
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
        if name.startswith("c1_inspected"):
            page.evaluate(
                "()=>selectDecision(run.decisions.findIndex(d=>d.role==='perception'),true)"
            )
            assert page.locator("#requestImages img").count() == 1
            assert page.evaluate(
                "run.decisions[selected].source_seq===run.decisions[selected].recording.observation_seq"
            )
            page.screenshot(path=str(OUT / "search_exact_tool.png"), full_page=True)
        if name == "c5_arrival_memory_20260913_s1061":
            index = page.evaluate(
                "run.decisions.findIndex(d=>d.role==='monitor' && d.t>13 && d.t<14)"
            )
            assert index >= 0
            page.evaluate("i=>selectDecision(i,true)", index)
            assert page.evaluate("run.decisions[selected].source_t") == 11.95
            assert "stop rejected by live arrival recheck" in page.evaluate(
                "run.decisions[selected].payload.evidence"
            )
            page.screenshot(path=str(OUT / "onfly_arrival_decision.png"), full_page=True)
    assert not errors, errors
    browser.close()
(OUT / "CHECKS.json").write_text(
    json.dumps({"checks": checks, "playbacks": 8, "errors": errors}, indent=2), encoding="utf-8"
)
print("PASS: 24 timeline checks, eight playbacks, exact search-tool image/source")
