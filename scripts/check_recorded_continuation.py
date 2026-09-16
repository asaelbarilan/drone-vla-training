"""Inspect the continuation camera, map and terminal decision in Edge."""

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path("reports/continuation_20260916/browser")
out.mkdir(parents=True, exist_ok=True)
root = Path("runs/c5_commitment_continued_20260916_s1061")
calls = [
    json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "debug/calls").glob("*.json"))
]
policies = {
    c["observation_seq"]: c for c in calls if c["role"] == "policy" and c["status"] == "complete"
}
matched_monitors = []
for call in calls:
    if call["role"] == "monitor" and call["status"] == "complete":
        policy = policies[call["observation_seq"]]
        assert len(call["image_files"]) == 1
        assert (root / call["image_files"][0]).read_bytes() == (
            root / policy["image_files"][0]
        ).read_bytes()
        matched_monitors.append(call["id"])
(out.parent / "MONITOR_IMAGE_AUDIT.json").write_text(
    json.dumps(dict(matched=matched_monitors, count=len(matched_monitors)), indent=2),
    encoding="utf-8",
)
errors = []
rows = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1100})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8766/commitment_continuation.html")
    page.wait_for_function('typeof run !== "undefined" && run && run.frames.length > 0')
    for index in [0, 1]:
        page.locator("#run").select_option(str(index))
        page.locator("#follow").check()
        end = page.evaluate("run.frames[run.frames.length-1].t")
        for t in sorted(
            set([74, 89, 90, *[x for x in [92, 94, 96, 98, 100, 105, 110, 115] if x < end], end])
        ):
            page.evaluate("(t)=>{pause();seek(nearest(t),true)}", t)
            page.wait_for_function('document.getElementById("drone").complete')
            row = page.evaluate("({...current(),name:run.name})")
            rgb = row.pop("rgb")
            rows.append(row)
            if index == 1:
                page.screenshot(path=str(out / f"t{t}.png"))
                (out / f"rgb_t{t}.png").write_bytes(base64.b64decode(rgb.split(",")[1]))
        page.evaluate("()=>{pause();seek(nearest(85),true)}")
        page.locator("#play").click()
        page.wait_for_function("current().t>85")
        page.evaluate("pause()")
    page.evaluate(
        "()=>{pause();$('follow').checked=false;selectDecision(run.decisions.findLastIndex(d=>d.role==='monitor'),true)}"
    )
    terminal = page.evaluate(
        "(()=>{let d=run.decisions[selected];"
        "return {id:d.id,t:d.t,source_t:d.source_t,payload:d.payload}})()"
    )
    (out / "TERMINAL_MONITOR.json").write_text(json.dumps(terminal, indent=2), encoding="utf-8")
    page.screenshot(path=str(out / "terminal_monitor.png"))
    browser.close()
assert not errors, errors
(out / "CHECKS.json").write_text(
    json.dumps(dict(checks=rows, playbacks=2, errors=errors), indent=2), encoding="utf-8"
)
print(f"{len(rows)} seeks; two playbacks; no JS errors")
