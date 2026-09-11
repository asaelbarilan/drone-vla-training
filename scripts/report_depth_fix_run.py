"""D-98: export the completed single-run comparison with no inference."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from uavlab.analysis.flight_debugger import (
    _sources,
    html_document,
    load_run,
    read_events,
    read_json,
)


async def main():
    out = Path("reports/depth_renderer_fix_20260912")
    names = ["c5_depth_ray_v2_20260912_s1061", "c5_guarded_monitor_20260911_s1061"]
    runs = []
    for name in names:
        print(f"Replaying {name} without inference", flush=True)
        runs.append(await load_run(Path("runs") / name))
    new, old = runs
    page = Path("reports/debugger/depth_fix_comparison.html")
    page.write_text(
        html_document({"schema": 1, "runs": runs, "sources": _sources()}), encoding="utf-8"
    )
    summaries = []
    for run in runs:
        metrics = run["result"]["metrics"]
        events = read_events(Path(run["path"]) / "events.jsonl")
        summaries.append(
            {
                "name": run["name"],
                "success": run["result"]["success"],
                "termination": run["result"]["termination_reason"],
                "duration_s": run["result"]["sim_duration_s"],
                "final_distance_m": metrics["distance_to_goal_m"],
                "closest_distance_m": min(f["distance"] for f in run["frames"]),
                "path_length_m": metrics["path_length_m"],
                "collisions": metrics["collisions"],
                "policy_calls": metrics["inference_calls_policy"],
                "monitor_calls": metrics["inference_calls_monitor"],
                "actual_models": run["model_ids"],
                "verifier_repair_rate": metrics["verifier_repair_rate"],
                "replay": run["provenance"],
                "policy_points": [
                    {
                        "t_s": e["t_sim_ns"] / 1e9,
                        "u": e["payload"]["provenance"].get("model_u"),
                        "v": e["payload"]["provenance"].get("model_v"),
                        "sampled_depth_m": e["payload"]["provenance"].get("sampled_depth_m"),
                    }
                    for e in events
                    if e["event_type"] == "decision_proposed"
                ],
            }
        )
    new_points, old_points = summaries[0]["policy_points"], summaries[1]["policy_points"]
    first_pixel_change = next(
        (
            {"new": a, "old": b}
            for a, b in zip(new_points, old_points, strict=False)
            if (a["u"], a["v"]) != (b["u"], b["v"])
        ),
        None,
    )
    first_pose_change = next(
        (
            a["t"]
            for a, b in zip(new["frames"], old["frames"], strict=False)
            if any(abs(x - y) > 1e-8 for x, y in zip(a["position"], b["position"], strict=True))
        ),
        None,
    )
    summary = {
        "runs": summaries,
        "first_different_recorded_model_point": first_pixel_change,
        "first_pose_divergence_s": first_pose_change,
        "new_simulations": 1,
        "cloud_calls": 0,
        "comparison_page": str(page),
    }
    (out / "RUN_COMPARISON.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "result.json").write_text(json.dumps(new["result"], indent=2), encoding="utf-8")
    manifest = read_json(Path(new["path"]) / "manifest.json")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for s in summaries:
        print(
            json.dumps({k: v for k, v in s.items() if k not in ("policy_points", "replay")}),
            flush=True,
        )
    print(
        json.dumps(
            {
                "first_different_model_point": first_pixel_change,
                "first_pose_divergence_s": first_pose_change,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
