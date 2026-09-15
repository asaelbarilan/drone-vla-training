"""Inspect the final approach from the exported replay; no inference or steering."""

import base64
import json
from itertools import pairwise
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

out = Path("reports/recovery_cycle_20260915/cycle3")
root = Path("runs/c5_target_commitment_20260915_s1061")
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1050})
    page.goto("http://127.0.0.1:8766/recovery_cycle3.html")
    page.wait_for_function('typeof run !== "undefined" && run && run.frames.length > 0')
    page.locator("#run").select_option("1")
    assert page.evaluate("run.name") == "c5_target_commitment_20260915_s1061"
    rows = []
    for t in [60, 73, 74, 75, 80, 85, 90]:
        page.evaluate("(t)=>{pause();seek(nearest(t),true)}", t)
        page.wait_for_function('document.getElementById("drone").complete')
        row = page.evaluate("({...current()})")
        rgb = row.pop("rgb")
        (out / "browser" / f"finish_rgb_{t}.png").write_bytes(base64.b64decode(rgb.split(",")[1]))
        page.screenshot(path=str(out / "browser" / f"finish_{t}.png"))
        rows.append(row)
    final_segment = page.evaluate(
        "run.frames.filter(f=>f.t>=75).map(f=>({t:f.t,distance:f.distance}))"
    )
    browser.close()
events = [json.loads(x) for x in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()]
calls = [json.loads(f.read_text(encoding="utf-8")) for f in (root / "debug/calls").glob("*.json")]
by_seq = {
    c["observation_seq"]: c for c in calls if c["role"] == "policy" and c["status"] == "complete"
}
points = []
for e in events:
    if e["event_type"] != "decision_proposed" or e["t_sim_ns"] < 75e9:
        continue
    data = e["payload"]
    if "source_observation_seq" not in data:
        continue
    prov = data["provenance"]
    call = by_seq[data["source_observation_seq"]]
    im = Image.open(root / call["image_files"][0]).convert("RGB")
    pixel = (round(float(prov["pixel_u"])), round(float(prov["pixel_v"])))
    points.append(
        dict(
            available_t=e["t_sim_ns"] / 1e9,
            effective_kind=prov["waypoint_kind"],
            pixel_rgb=im.getpixel(pixel),
            pixel=pixel,
            call=call["id"],
            original_source_t=e["t_sim_ns"] / 1e9 - data["production_latency_s"],
        )
    )
result = dict(
    frames=rows,
    final_segment=final_segment,
    policy_points=points,
    distance_increases_after_75=sum(
        b["distance"] > a["distance"] + 1e-9 for a, b in pairwise(final_segment)
    ),
    note=(
        "Evaluation distance is debugger-only truth. "
        "More time and causal architecture gain remain untested."
    ),
)
(out / "FINISH_REVIEW.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(
    json.dumps(
        dict(
            frames=[{k: r[k] for k in ["t", "distance", "position", "velocity"]} for r in rows],
            distance_increases_after_75=result["distance_increases_after_75"],
            points=[
                {k: d[k] for k in ["available_t", "effective_kind", "pixel_rgb"]} for d in points
            ],
        ),
        indent=2,
    )
)
