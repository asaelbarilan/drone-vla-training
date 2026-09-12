"""Check actual D-104 replay pages in Edge, without model calls."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("families", nargs="+", choices=("c0", "c1", "c5"))
args = parser.parse_args()
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    for family in args.families:
        out = Path("reports/capability_screen_20260912/browser") / family
        out.mkdir(parents=True, exist_ok=True)
        checks, errors = [], []
        page = browser.new_page(viewport={"width": 1720, "height": 1200})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:8765/capability_screen_{family}.html", timeout=60000)
        count = page.locator("#run option").count()
        assert count > 0
        for i in range(count):
            page.locator("#run").select_option(str(i))
            name = page.evaluate("run.name")
            for t in [0, 10, 60]:
                value = page.evaluate("""t=>{pause();seek(nearest(t),false);
                    return {name:run.name,t:current().t,scene:current().scene,
                            error:document.querySelector('#error').innerText};}""", t)
                assert not value["error"]
                assert page.locator("#taskStatus").is_visible()
                assert "NOT architecture performance" not in page.locator("#taskStatus").inner_text()
                page.wait_for_function("document.querySelector('#drone').complete && document.querySelector('#drone').naturalWidth > 0")
                checks.append(value)
                if t == 60:
                    page.screenshot(path=str(out / f"{name}_final.png"))
            page.locator("#scrub").fill("0")
            page.locator("#scrub").dispatch_event("input")
            page.locator("#play").click()
            page.wait_for_function("Number(document.querySelector('#scrub').value)>0")
            page.locator("#play").click()
        page.close()
        assert not errors, errors
        (out / "CHECKS.json").write_text(json.dumps({"errors": errors, "snapshots": len(checks), "playback_checks":count,"checks":checks},indent=2),encoding="utf-8")
        print(f"PASS {family}: {len(checks)} snapshots, {count} playback checks, no browser errors",flush=True)
    browser.close()
