"""D-106: publish frozen comparison and preserve evidence without inference."""

from __future__ import annotations

import asyncio
import gzip
import html
import json
from collections import Counter
from pathlib import Path

from run_frozen_capability import OUT, cells, snapshot

from uavlab.analysis.flight_debugger import _sources, html_document, load_run


async def main():
    freeze = json.loads((OUT / "FREEZE.json").read_text(encoding="utf-8"))
    assert snapshot() == freeze["hashes"], "Frozen source/config changed"
    rows = []
    totals = Counter()
    for family in ("c0", "c1", "c5"):
        runs = []
        for cell in cells():
            if cell["family"] != family:
                continue
            path = Path("runs") / cell["name"]
            if not (path / "result.json").exists():
                continue
            print("REPLAY", path.name, flush=True)
            run = await load_run(path)
            proof = run["provenance"]
            assert proof["max_position_error_m"] < 1e-6 and proof["missing_source_frames"] == 0
            runs.append(run)
            result = run["result"]
            frames = run["frames"]
            nearest = min(frames, key=lambda f: f["distance"])
            calls = run["recordings"]
            complete = [c for c in calls if c.get("status") == "complete"]
            real = [c for c in complete if c.get("output_tokens", 0) > 0]
            if family != "c0":
                assert all(c["model_id"] == "gemma4:e2b" for c in calls)
            counts = dict(
                completed_real=len(real),
                cancelled=sum(c.get("status") == "cancelled" for c in calls),
                completed_by_role=dict(Counter(c["role"] for c in real)),
                image_calls=sum(c.get("image_count", 0) > 0 for c in real),
            )
            totals.update({k: v for k, v in counts.items() if isinstance(v, int)})
            row = {
                **cell,
                "success": result["success"],
                "termination": result["termination_reason"],
                "sim_s": result["sim_duration_s"],
                "wall_s": result["wall_duration_s"],
                "metrics": result["metrics"],
                "closest_t": nearest["t"],
                "closest_m": nearest["distance"],
                "calls": counts,
                "replay": proof,
                "decisions": [
                    {
                        k: c.get(k)
                        for k in (
                            "id",
                            "role",
                            "status",
                            "image_count",
                            "observation_seq",
                            "started_t_sim_ns",
                            "completed_t_sim_ns",
                            "response",
                        )
                    }
                    for c in calls
                ],
            }
            rows.append(row)
            dest = OUT / path.name
            dest.mkdir(exist_ok=True)
            for filename in ("manifest.json", "result.json"):
                (dest / filename).write_bytes((path / filename).read_bytes())
            (dest / "events.jsonl.gz").write_bytes(
                gzip.compress((path / "events.jsonl").read_bytes(), mtime=0)
            )
            # Preserve exact requests and input images, not just response summaries.
            for subdir in ("calls", "images", "sources"):
                for source in (path / "debug" / subdir).glob("*"):
                    if source.is_file():
                        target = dest / "debug" / subdir / source.name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(source.read_bytes())
        if runs:
            banner = "Frozen development comparison: one seed; C0 uses goal truth; latency differs. C1 visual tools cover visible_target and turn_search only."
            page = html_document({"schema": 1, "runs": runs, "sources": _sources()})
            page = page.replace(
                "<body>", "<body><p style='padding:16px;color:#ffd187'>" + banner + "</p>"
            )
            Path(f"reports/debugger/frozen_capability_{family}.html").write_text(
                page, encoding="utf-8"
            )
    (OUT / "SUMMARY.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (OUT / "CALL_BUDGET.json").write_text(json.dumps(dict(totals), indent=2), encoding="utf-8")
    notes = [
        "24 fixed cells, development seed 1061, maximum 60 simulated seconds; no adaptive changes or retries.",
        "C0 is a privileged final-goal baseline, not an autonomous visual searcher.",
        "C1 uses the requested visual tool only for visible target/search. Five other visual-task cells remain text-only and integration-limited.",
        "C1 policy costs 8.5 simulated seconds; C5 policy 1 second. Perception/monitor cost 1.2 seconds. This is not a matched-latency ranking.",
        "Search diagnosis: target appears during rotation but was absent in the sole post-scan detection image; inherited full-turn gate rejects another scan.",
        "Click each result for the actual camera, flight, decisions and exact model input. Timeout alone is not a root-cause diagnosis.",
    ]
    table = []
    md = [
        "# D-106 frozen capability comparison",
        "",
        "See FINDINGS.md and SEARCH_INSPECTED.md for diagnosis.",
        "",
        *["- " + n for n in notes],
        "",
        "| Scenario | C0 | C1 | C5 |",
        "|---|---|---|---|",
    ]
    from uavlab.adapters.gym.capability_env import SCENARIOS

    for scenario in SCENARIOS:
        tr = ["<td>" + scenario + "</td>"]
        mr = [scenario]
        for family in ("c0", "c1", "c5"):
            row = next(
                (r for r in rows if r["family"] == family and r["scenario"] == scenario), None
            )
            if row is None:
                tr.append("<td>Pending</td>")
                mr.append("Pending")
                continue
            label = ("PASS" if row["success"] else "FAIL: " + row["termination"]) + (
                " — missing visual integration" if row["integration_limited"] else ""
            )
            url = f"frozen_capability_{family}.html#run={row['name']}&t=0"
            tr.append(
                f'<td><a href="{url}">{html.escape(label)}</a><small>closest {row["closest_m"]:.2f} m · {row["sim_s"]:.1f} s</small></td>'
            )
            mr.append(f"[{label}](http://127.0.0.1:8765/{url})")
        table.append("<tr>" + "".join(tr) + "</tr>")
        md.append("| " + " | ".join(mr) + " |")
    (OUT / "REPORT.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    content = (
        "<!doctype html><meta charset='utf-8'><title>Frozen capability comparison</title><style>body{font:17px system-ui;background:#0b1420;color:#e4ecf4;max-width:1250px;margin:40px auto;padding:20px}a{color:#60d4e0}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:14px;border-bottom:1px solid #344453}li{margin:12px 0}small{display:block;color:#9db4c9;margin-top:7px}</style><h1>Frozen capability comparison</h1><p>September 13, 2026 · seed 1061 · three architecture families / eight tasks</p><table><tr><th>Scenario</th><th>C0 / privileged SUPER</th><th>C1 / AerialClaw</th><th>C5 / OnFly</th></tr>"
        + "".join(table)
        + "</table><ul>"
        + "".join("<li>" + html.escape(n) + "</li>" for n in notes)
        + "</ul><p><a href='frozen_search.html#run=frozen_c1_turn_search_20260913_s1061&t=10'>Inspect the search target during rotation at 10 s</a></p>"
    )
    Path("reports/debugger/frozen_capability.html").write_text(content, encoding="utf-8")
    print(
        json.dumps(
            {
                "cells": len(rows),
                "successes": dict(Counter(r["family"] for r in rows if r["success"])),
                "budget": dict(totals),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
