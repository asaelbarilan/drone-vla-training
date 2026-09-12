"""Exercise the actual eight-scenario debugger in headless Edge."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path("reports/capability_scenarios_20260912/browser")
out.mkdir(parents=True, exist_ok=True)
checks = []
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1720, "height": 1200})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8765/capability_scenarios.html", timeout=60000)
    assert page.locator("#run option").count() == 8
    for i in range(8):
        page.locator("#run").select_option(str(i))
        name = page.evaluate("run.name")
        for t in [0, 3.1, 10, 60]:
            value = page.evaluate(
                """t=>{pause();seek(nearest(t),false);
                return {name:run.name,t:current().t,scene:current().scene,
                        error:document.querySelector('#error').innerText};}""",
                t,
            )
            assert not value["error"]
            assert page.locator("#taskStatus").is_visible()
            assert "NOT architecture performance" in page.locator("#taskStatus").inner_text()
            page.wait_for_function(
                "document.querySelector('#drone').complete && "
                "document.querySelector('#drone').naturalWidth > 0"
            )
            checks.append(value)
            if t in [0, 60] or ("closing_passage" in name and t == 3.1):
                page.locator(".views").screenshot(path=str(out / f"{name}_{t}_views.png"))
        page.locator("#scrub").fill("0")
        page.locator("#scrub").dispatch_event("input")
        page.locator("#play").click()
        page.wait_for_function("Number(document.querySelector('#scrub').value)>0")
        page.locator("#play").click()
    browser.close()
assert not errors, errors
(out / "CHECKS.json").write_text(
    json.dumps({"errors": errors, "checks": checks}, indent=2), encoding="utf-8"
)
print(f"PASS: {len(checks)} dashboard snapshots, 8 playback checks, no browser errors")
