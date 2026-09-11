"""D-99: compare two additional development flights without new inference."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from uavlab.analysis.flight_debugger import _sources, html_document, load_run, read_json

OUT = Path("reports/depth_renderer_two_runs_20260912")
PAGE = Path("reports/debugger/depth_fix_comparison.html")
SEEDS = (1060, 1062, 1061)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names = [f"c5_depth_ray_v2_20260912_s{seed}" for seed in SEEDS]
    names.append("c5_guarded_monitor_20260911_s1061")
    baseline = read_json(Path("runs") / names[2] / "manifest.json")
    runs, summaries = [], []
    for i, name in enumerate(names):
        path = Path("runs") / name
        manifest = read_json(path / "manifest.json")
        if i < 3:
            assert manifest["architecture_config"] == baseline["architecture_config"]
            assert manifest["environment_config"] == baseline["environment_config"]
            assert manifest["seeds"] == [SEEDS[i]]
        print(f"Replaying {name} without inference", flush=True)
        run = await load_run(path)
        runs.append(run)
        assert run["model_ids"] == ["gemma4:e2b"]
        result = run["result"]
        metrics = result["metrics"]
        closest = min(run["frames"], key=lambda frame: frame["distance"])
        summary = {
            "name": name,
            "seed": manifest["seeds"][0],
            "depth_renderer": manifest["environment_config"]["params"].get(
                "depth_renderer", "legacy_corner"
            ),
            "success": result["success"],
            "termination": result["termination_reason"],
            "duration_s": result["sim_duration_s"],
            "final_distance_m": metrics["distance_to_goal_m"],
            "closest_distance_m": closest["distance"],
            "closest_time_s": closest["t"],
            "path_length_m": metrics["path_length_m"],
            "collisions": metrics["collisions"],
            "policy_calls": metrics["inference_calls_policy"],
            "monitor_calls": metrics["inference_calls_monitor"],
            "actual_models": run["model_ids"],
            "verifier_repair_rate": metrics["verifier_repair_rate"],
            "replay": run["provenance"],
        }
        summaries.append(summary)
        if i < 2:
            dest = OUT / str(SEEDS[i])
            dest.mkdir(exist_ok=True)
            for filename in ("result.json", "manifest.json"):
                (dest / filename).write_text(
                    (path / filename).read_text(encoding="utf-8"), encoding="utf-8"
                )
        print(json.dumps(summary), flush=True)
    PAGE.write_text(
        html_document({"schema": 1, "runs": runs, "sources": _sources()}), encoding="utf-8"
    )
    report = {
        "new_simulations": 2,
        "new_seeds": list(SEEDS[:2]),
        "settings_match_previous_corrected_depth_run": True,
        "cloud_calls": 0,
        "comparison_page": str(PAGE),
        "runs": summaries,
        "limitation": "Three development layouts; no matched legacy trials on the new seeds.",
    }
    (OUT / "RUN_COMPARISON.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    PAGE.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
