"""D-115 saved flight replay, model identity, source audit and evidence archive."""

import asyncio
import gzip
import json
import shutil
from collections import Counter
from pathlib import Path

from audit_clutter_stable import audit

from uavlab.analysis.flight_debugger import _sources, html_document, load_run

OUT = Path("reports/qwen4_validation_20260915")
NAME = "c5_clutter_qwen4_20260915_s1061"
BASE = "c5_clutter_stable_20260914_s1061"


async def main():
    root = Path("runs") / NAME
    freeze = json.loads((OUT / "FLIGHT_FREEZE.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["architecture_config"] == freeze["architecture"]
    assert manifest["environment_config"] == freeze["environment"]
    old = json.loads((Path("runs") / BASE / "manifest.json").read_text(encoding="utf-8"))
    assert old["environment_config"] == manifest["environment_config"]
    runs = [await load_run(Path("runs") / name) for name in [BASE, NAME]]
    for run in runs:
        assert run["provenance"]["max_position_error_m"] < 1e-7
        assert run["provenance"]["missing_source_frames"] == 0
    Path("reports/debugger/qwen4_clutter.html").write_text(
        html_document(dict(schema=1, runs=runs, sources=_sources())), encoding="utf-8"
    )
    proof = await audit(NAME)
    events = [
        json.loads(x) for x in (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    calls = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((root / "debug/calls").glob("*.json"))
    ]
    assert all(c["model_id"] == "qwen3-vl:4b" for c in calls)
    inference = [e["payload"] for e in events if e["event_type"] == "inference_call"]
    assert all(
        c["model_id"] == "qwen3-vl:4b" and c["response_channel"] == "thinking" for c in inference
    )
    proof["calls"] = dict(Counter(c["status"] for c in calls))
    proof["calls_by_role"] = dict(Counter(c["role"] for c in calls if c["status"] == "complete"))
    proof["inference_events"] = len(inference)
    proof["model_identity_verified"] = True
    proof["planner_results"] = dict(
        Counter(
            str(e["payload"]["feasible"]) + ": " + e["payload"]["reason"]
            for e in events
            if e["event_type"] == "plan"
        )
    )
    proof["monitor_labels"] = dict(
        Counter(e["payload"]["label"] for e in events if e["event_type"] == "monitor")
    )
    proof["replay_comparison"] = [
        dict(
            name=r["name"],
            closest=min(f["distance"] for f in r["frames"]),
            closest_t=min(r["frames"], key=lambda f: f["distance"])["t"],
            provenance=r["provenance"],
        )
        for r in runs
    ]
    (OUT / "FLIGHT_AUDIT.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    dest = OUT / "flight"
    dest.mkdir(exist_ok=True)
    for file in ["manifest.json", "result.json"]:
        (dest / file).write_bytes((root / file).read_bytes())
    (dest / "events.jsonl.gz").write_bytes(
        gzip.compress((root / "events.jsonl").read_bytes(), mtime=0)
    )
    shutil.copytree(root / "debug", dest / "debug", dirs_exist_ok=True)
    print(json.dumps({k: v for k, v in proof.items() if k != "selected_decisions"}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
