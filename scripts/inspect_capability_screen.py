"""Read closest-approach evidence from exported flight timelines; no inference."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
out = Path("reports/capability_screen_20260912")
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width":1720,"height":1200})
    page.goto("http://127.0.0.1:8765/capability_screen_c5.html", timeout=60000)
    evidence=[]
    for i in range(page.locator("#run option").count()):
        page.locator("#run").select_option(str(i))
        data=page.evaluate("""()=>{
            const f=run.frames.reduce((a,b)=>a.distance<b.distance?a:b);
            pause();seek(nearest(f.t),false);
            return {run:run.name,closest_t:f.t,closest_distance:f.distance,
                    position:f.position,final_distance:run.frames.at(-1).distance,
                    stop_calls:run.result.metrics.monitor_stop_calls};
        }""")
        if "visible_target" in data["run"]:
            page.wait_for_function("document.querySelector('#drone').complete && document.querySelector('#drone').naturalWidth > 0")
            page.screenshot(path=str(out/"browser/c5/visible_target_closest.png"))
        evidence.append(data)
    (out/"C5_CLOSEST_APPROACH.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
    browser.close()
