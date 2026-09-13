"""Rebuild D-107 comparison from stored controls, without inference."""

import asyncio
import gzip
import json
from collections import Counter
from pathlib import Path

from uavlab.analysis.flight_debugger import _sources, html_document, load_run

OUT = Path("reports/targeted_contracts_20260913")
NAMES = (
    "c5_arrival_window_20260913_s1061",
    "c5_arrival_memory_20260913_s1061",
    "frozen_c5_visible_target_20260913_s1061",
    "c1_ordered_requested_20260913_s1061",
    "c1_ordered_visual_20260913_s1061",
    "frozen_c1_ordered_visit_20260913_s1061",
    "c1_inspected_search_20260913_s1061",
    "frozen_c1_turn_search_20260913_s1061",
)


async def main():
    runs = []
    rows = []
    budget = Counter()
    for name in NAMES:
        path = Path("runs") / name
        print("REPLAY", name, flush=True)
        run = await load_run(path)
        proof = run["provenance"]
        assert proof["max_position_error_m"] < 1e-7 and proof["missing_source_frames"] == 0
        runs.append(run)
        closest = min(run["frames"], key=lambda f: f["distance"])
        calls = run["recordings"]
        counts = Counter(c["status"] for c in calls)
        assert all(c["model_id"] == "gemma4:e2b" for c in calls)
        rows.append(
            dict(
                name=name,
                result=run["result"],
                replay=proof,
                closest_t=closest["t"],
                closest_m=closest["distance"],
                calls=dict(counts),
                decisions=[
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
            )
        )
        if not name.startswith("frozen_"):
            budget.update(counts)
            dest = OUT / name
            dest.mkdir(exist_ok=True)
            for f in ("manifest.json", "result.json"):
                (dest / f).write_bytes((path / f).read_bytes())
            (dest / "events.jsonl.gz").write_bytes(
                gzip.compress((path / "events.jsonl").read_bytes(), mtime=0)
            )
            for directory in ("calls", "images", "sources"):
                for p in (path / "debug" / directory).glob("*"):
                    if p.is_file():
                        target = dest / "debug" / directory / p.name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(p.read_bytes())
    page = html_document({"schema": 1, "runs": runs, "sources": _sources()})
    banner = (
        "D-107: five new development flights, all failures retained. Final C5 arrival window "
        "passes at 13.2 s. Corrected ordered C1 completes red but never switches to blue. "
        "Inspected-search C1 repeats detection without rotating. Initial ordered prompt "
        "had conflicting passive-perception advice; initial C5 memory expired before availability. "
        "One seed; these opt-in variants are not general reliability results."
    )
    page = page.replace(
        "<body>",
        "<body><div class='card' style='margin:12px;padding:16px;color:#ffca76'>"
        + banner
        + "</div>",
    )
    Path("reports/debugger/targeted_contracts.html").write_text(page, encoding="utf-8")
    (OUT / "RUNS.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (OUT / "CALL_BUDGET.json").write_text(json.dumps(dict(budget), indent=2), encoding="utf-8")
    print(
        json.dumps({"new_calls": dict(budget), "runs": [(r["name"], r["closest_m"]) for r in rows]})
    )


if __name__ == "__main__":
    asyncio.run(main())
