"""Replay completed D-104 episodes and publish per-architecture flight pages."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
from uavlab.analysis.flight_debugger import _sources, html_document, load_run

OUT = Path("reports/capability_screen_20260912")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("families", nargs="+", choices=("c0", "c1", "c5"))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for family in args.families:
        runs, summaries = [], []
        for path in sorted(Path("runs").glob(f"capability_screen_{family}_*_20260912_s1061")):
            if not (path / "result.json").exists():
                continue
            print(f"REPLAY {path.name}", flush=True)
            run = await load_run(path)
            result = run["result"]
            metrics = result["metrics"]
            runs.append(run)
            summaries.append({"run": path.name, "success": result["success"],
                "termination": result["termination_reason"], "detail": result["termination_detail"],
                "sim_s": result["sim_duration_s"], "wall_s": result["wall_duration_s"],
                "model_ids": run["model_ids"], "replay": run["provenance"],
                "metrics": metrics})
        if not runs:
            raise RuntimeError(f"No completed runs for {family}")
        page = Path(f"reports/debugger/capability_screen_{family}.html")
        page.write_text(html_document({"schema": 1, "runs": runs, "sources": _sources()}), encoding="utf-8")
        (OUT / f"{family.upper()}_SUMMARY.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
        print(f"EXPORTED {family}: {sum(r['success'] for r in summaries)}/{len(summaries)} successes; {page}", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
