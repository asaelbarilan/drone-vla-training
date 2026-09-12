"""Export actual adaptive-plan flights beside the saved corrected C5 baseline."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path

from uavlab.analysis.flight_debugger import _sources, html_document, load_run


async def main(names):
    out = Path("reports/adaptive_plan_flights_20260912")
    runs = []
    for name in names:
        print(f"Reconstructing saved controls: {name}", flush=True)
        runs.append(await load_run(Path("runs") / name))
    old_page = Path("reports/debugger/depth_fix_comparison.html").read_text(encoding="utf-8")
    start = old_page.index("const DATA = ") + len("const DATA = ")
    old, _ = json.JSONDecoder().raw_decode(old_page[start:])
    baseline = next(r for r in old["runs"] if r["name"] == "c5_depth_ray_v2_20260912_s1061")
    source_events = Path("runs") / baseline["name"] / "events.jsonl"
    assert (
        hashlib.sha256(source_events.read_bytes()).hexdigest()
        == baseline["provenance"]["events_sha256"]
    )
    runs.append(baseline)
    data = {"schema": 1, "runs": runs, "sources": _sources()}
    page = Path("reports/debugger/adaptive_plan_comparison.html")
    page.write_text(html_document(data), encoding="utf-8")
    summaries = []
    for run in runs:
        closest = min(run["frames"], key=lambda f: f["distance"])
        metrics = run["result"]["metrics"]
        summaries.append(
            {
                "run": run["name"],
                "result": run["result"],
                "closest_time_s": closest["t"],
                "closest_distance_m": closest["distance"],
                "model_ids": run["model_ids"],
                "replay": run["provenance"],
                "plan_records": sum(
                    e["payload"].get("kind") == "adaptive_visual_plan" for e in run["events"]
                ),
                "final_distance_m": metrics["distance_to_goal_m"],
            }
        )
    (out / "DASHBOARD_SUMMARY.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"Saved {page}; {len(runs)} actual flights, no inference.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args()
    asyncio.run(main(args.runs))
