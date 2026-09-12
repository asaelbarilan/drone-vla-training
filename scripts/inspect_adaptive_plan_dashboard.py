"""Capture the actual dashboard at fixed moments; no simulation or inference."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path("reports/adaptive_plan_flights_20260912/dashboard")
out.mkdir(parents=True, exist_ok=True)
errors = []
observations = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1720, "height": 1200})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8765/adaptive_plan_comparison.html", timeout=60000)
    count = page.locator("#run option").count()
    for idx in range(count):
        page.locator("#run").select_option(str(idx))
        name = page.locator("#run option:checked").inner_text().split(" · ")[0]
        for requested in [0, 10, 20, 30, 40, 50, 70, 90]:
            info = page.evaluate(
                """t=>{
                pause();seek(nearest(t),false);
                let i=run.decisions.findLastIndex(d=>d.role==='policy'&&d.t<=current().t);
                if(i>=0)selectDecision(i,false);
                const d=i>=0?run.decisions[i]:null;
                return {requested_t:t,cursor_t:current().t,position:current().position,
                        distance:current().distance,decision:d?.id,source_t:d?.source_t,
                        available_t:d?.t,decision_state:d?.state};
            }""",
                requested,
            )
            page.wait_for_function(
                "document.querySelector('#drone').complete && "
                "document.querySelector('#drone').naturalWidth>0"
            )
            prefix = f"{name}_{requested:02d}"
            page.locator(".views").screenshot(path=str(out / (prefix + "_views.png")))
            if page.locator("#adaptivePlan").is_visible():
                page.locator("#adaptivePlan").screenshot(path=str(out / (prefix + "_plan.png")))
                info["plan_text"] = page.locator("#adaptivePlan").inner_text()
            observations.append(dict(run=name, **info))
        page.locator("#scrub").fill("0")
        page.locator("#scrub").dispatch_event("input")
        page.locator("#play").click()
        page.wait_for_function("Number(document.querySelector('#scrub').value)>40")
        page.locator("#play").click()
    browser.close()
assert not errors, errors
(out / "OBSERVATIONS.json").write_text(
    json.dumps(
        {"javascript_errors": errors, "runs": count, "observations": observations}, indent=2
    ),
    encoding="utf-8",
)
print(
    f"Captured {len(observations)} dashboard moments from {count} actual flights; "
    "playback works; no JavaScript errors."
)
