"""D-105: replay old failures and new repairs, with exact tool evidence."""

import asyncio
import gzip
import json
from pathlib import Path
from uavlab.analysis.flight_debugger import _sources, html_document, load_run

NAMES = (
    "c1_visual_search_strategy_20260913_s1061",
    "c1_visual_tool_search_20260913_s1061",
    "c1_coordinate_completion_20260913_s1061",
    "c1_visual_tool_refined_20260913_s1061",
    "c1_visual_tool_visible_20260913_s1061",
    "capability_screen_c1_known_goal_20260912_s1061",
    "capability_screen_c1_visible_target_20260912_s1061",
)
OUT = Path("reports/aerialclaw_tools_20260913")


async def main():
    runs, summary = [], []
    for name in NAMES:
        path = Path("runs") / name
        print("REPLAY", name, flush=True)
        run = await load_run(path)
        proof = run["provenance"]
        assert proof["max_position_error_m"] < 1e-6 and proof["missing_source_frames"] == 0
        runs.append(run)
        result = run["result"]
        summary.append(
            {
                "run": name,
                "success": result["success"],
                "reason": result["termination_reason"],
                "sim_s": result["sim_duration_s"],
                "wall_s": result["wall_duration_s"],
                "metrics": result["metrics"],
                "replay": proof,
                "calls": [
                    {
                        k: c.get(k)
                        for k in (
                            "id",
                            "role",
                            "image_count",
                            "status",
                            "observation_seq",
                            "started_t_sim_ns",
                            "completed_t_sim_ns",
                        )
                    }
                    for c in run["recordings"]
                ],
            }
        )
        if "20260913" in name:
            dest = OUT / name
            dest.mkdir(exist_ok=True)
            for filename in ("manifest.json", "result.json"):
                (dest / filename).write_bytes((path / filename).read_bytes())
            (dest / "events.jsonl.gz").write_bytes(
                gzip.compress((path / "events.jsonl").read_bytes(), mtime=0)
            )
            for file in (path / "debug/calls").glob("*.json"):
                record = json.loads(file.read_text(encoding="utf-8"))
                target = dest / "debug/calls" / file.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(file.read_bytes())
                for relative in record.get("image_files", []):
                    target = dest / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((path / relative).read_bytes())
    Path("reports/debugger/aerialclaw_tools.html").write_text(
        html_document({"schema": 1, "runs": runs, "sources": _sources()}).replace("<body>", "<body><div class=\"card\" style=\"margin:12px;padding:12px;color:#ffca76\">Development comparison: c1_visual_search_strategy_20260913_s1061 is an INVALID setup trial (old advice ran). Corrected search advice has offline tests only.</div>"), encoding="utf-8"
    )
    (OUT / "RUNS.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        "PASS: replay trajectories; new flights",
        [(r["run"], r["success"]) for r in summary[:4]],
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
