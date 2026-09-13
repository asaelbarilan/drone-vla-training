"""Inspect task progress and source-linked evidence in the frozen dashboard."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("reports/frozen_capability_20260913/browser")
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1100})
    evidence = []
    for family in ("c0", "c1", "c5"):
        page.goto(f"http://127.0.0.1:8765/frozen_capability_{family}.html", timeout=60000)
        for index in range(page.locator("#run option").count()):
            page.locator("#run").select_option(str(index))
            data = page.evaluate("""()=>{
                const f=run.frames.reduce((a,b)=>a.distance<b.distance?a:b);
                pause();seek(nearest(f.t),false);
                const task=run.frames.find(x=>x.scene?.task_status?.task_complete);
                const violation=run.frames.find(x=>x.scene?.task_status?.constraint_violations>0);
                const red=run.frames.find(x=>x.scene?.task_status?.subgoals_completed>0);
                return {name:run.name,closest_t:f.t,closest_m:f.distance,
                    task_first_satisfied_t:task?.t??null,first_violation_t:violation?.t??null,
                    first_subgoal_t:red?.t??null,
                    min_z:Math.min(...run.frames.map(x=>x.position[2])),
                    max_z:Math.max(...run.frames.map(x=>x.position[2])),
                    max_radius:Math.max(...run.frames.map(x=>Math.hypot(x.position[0],x.position[1])))};
            }""")
            page.wait_for_function(
                "document.querySelector('#drone').complete && "
                "document.querySelector('#drone').naturalWidth>0"
            )
            page.screenshot(path=str(OUT / f"{data['name']}_closest.png"))
            evidence.append(data)
            if family == "c1":
                tool = page.evaluate("run.decisions.findIndex(d=>d.role==='perception')")
                if tool >= 0:
                    page.evaluate("i=>selectDecision(i,true)", tool)
                    assert page.locator("#requestImages img").count() == 1
                    assert page.evaluate(
                        "run.decisions[selected].source_seq === "
                        "run.decisions[selected].recording.observation_seq"
                    )
                    page.screenshot(path=str(OUT / f"{data['name']}_tool.png"), full_page=True)
    (OUT / "INSPECTION.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    page.goto("http://127.0.0.1:8765/frozen_capability.html")
    assert page.locator("table tr").count() == 9
    assert page.locator("table a").count() == 24
    page.screenshot(path=str(OUT / "comparison.png"), full_page=True)
    browser.close()
print(
    "PASS: 24 closest approaches, task transition diagnostics, exact C1 tool images, matrix links"
)
