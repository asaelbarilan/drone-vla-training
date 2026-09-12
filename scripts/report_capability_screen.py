"""Replay completed D-104 episodes and publish per-architecture flight pages."""
from __future__ import annotations
import argparse
import asyncio
import json
import html
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

    families = {}
    for family in ("c0", "c1", "c5"):
        summary = OUT / f"{family.upper()}_SUMMARY.json"
        if summary.exists():
            families[family] = json.loads(summary.read_text(encoding="utf-8"))
    notes = [
        "Development screen: one seed (1061), one run per cell, maximum 60 simulated seconds; no tuning or statistical ranking.",
        "C0 has privileged final-goal coordinates. Its current policy does not implement ordered objectives or distance-band tracking.",
        "C1 retains its text-only sensor/skill protocol; these scenes supply no semantic detections. It cannot visually identify task objects. Gemma replaces the historical GPT-OSS backend.",
        "C5 uses the existing generic current-frame OnFly monitor, calibrated camera pitch -0.10 rad, no target-color guard; this differs from the earlier guarded red-tower profile.",
        "Latency is not matched: C1 retains 8.5 s simulated policy charge; C5 retains 1 s policy / 1.2 s monitor. Actual wall times and model requests are saved.",
        "C0 inference entries are zero-token simulator events. C1 and C5 use local gemma4:e2b only. No cloud calls or held-out seeds.",
    ]
    report = ["# D-104 capability screen", "", *["- " + n for n in notes], "", "| Scenario | C0 | C1 | C5 |", "|---|---|---|---|"]
    rows = []
    from uavlab.adapters.gym.capability_env import SCENARIOS
    for scenario in SCENARIOS:
        row, md = ["<td>" + html.escape(scenario) + "</td>"], [scenario]
        for family in ("c0", "c1", "c5"):
            run = next((r for r in families.get(family, []) if r["run"] == f"capability_screen_{family}_{scenario}_20260912_s1061"), None)
            if run is None:
                row.append("<td>Pending</td>")
                md.append("Pending")
            else:
                status = "PASS" if run["success"] else "FAIL: " + run["termination"]
                url = f"capability_screen_{family}.html#run={run['run']}&t=0"
                row.append(f'<td><a href="{url}">{html.escape(status)}</a></td>')
                md.append(f"[{status}](http://127.0.0.1:8765/{url})")
        rows.append("<tr>" + "".join(row) + "</tr>")
        report.append("| " + " | ".join(md) + " |")
    report.extend(["", "## Evidence", "", "Per-cell manifest.json and result.json are copied here; C0/C1/C5_SUMMARY.json contain metrics and replay hashes. Original events and exact model requests/responses remain under runs/<run>/ with debug capture. Browser checks/screenshots are under browser/. No failed flight is removed or rerun."])
    (OUT / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    content = "<!doctype html><meta charset='utf-8'><title>Capability screen</title><style>body{font:17px system-ui;background:#0b1420;color:#e4ecf4;max-width:1200px;margin:40px auto;padding:20px}a{color:#60d4e0}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:14px;border-bottom:1px solid #344453}li{margin:12px 0}</style><h1>Capability screen</h1><p>Seed 1061 · September 12, 2026 · click an outcome to inspect its flight</p><table><tr><th>Scenario</th><th>C0 / SUPER</th><th>C1 / AerialClaw</th><th>C5 / OnFly</th></tr>" + "".join(rows) + "</table><h2>How to read these results</h2><ul>" + "".join("<li>" + html.escape(n) + "</li>" for n in notes) + "</ul>"
    Path("reports/debugger/capability_screen.html").write_text(content, encoding="utf-8")

if __name__ == "__main__":
    asyncio.run(main())
