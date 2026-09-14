"""Validate frozen inputs and summarize actual repetitions without inference."""

import hashlib
import json
from pathlib import Path

import numpy as np

OUT = Path("reports/hover_repeat_20260914")
freeze = json.loads((OUT / "FREEZE.json").read_text(encoding="utf-8"))
for path, digest in freeze["source_config_sha256"].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
reference = json.loads(
    Path("runs/c5_hover_level_20260913_s1061/manifest.json").read_text(encoding="utf-8")
)
rows = []
for seed in freeze["seeds"]:
    name = f"c5_hover_repeat_20260914_s{seed}"
    root = Path("runs") / name
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for key in ("architecture_config", "environment_config"):
        assert manifest[key] == reference[key], key
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    speed_excesses = []
    for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["event_type"] == "control":
            p = event["payload"]
            speed = float(np.linalg.norm([p["vx"], p["vy"], p["vz"]]))
            if speed > 2:
                speed_excesses.append({"t": event["t_sim_ns"] / 1e9, "excess_mps": speed - 2})
    m = result["metrics"]
    rows.append(
        {
            "name": name,
            "success": result["success"],
            "sim_s": result["sim_duration_s"],
            "distance_m": m["distance_to_goal_m"],
            "hover_s": m["task_hover_streak_s"],
            "collisions": m["collisions"],
            "contact": m["task_target_contact"],
            "raw_violations": m["constraint_violations"],
            "speed_excesses": speed_excesses,
        }
    )
replays = json.loads((OUT / "RUNS.json").read_text(encoding="utf-8"))
browser = json.loads((OUT / "browser/CHECKS.json").read_text(encoding="utf-8"))
sources = list(OUT.glob("*/debug/sources/*"))
for path in sources:
    assert hashlib.sha256(path.read_bytes()).hexdigest() == path.stem, path
assert not browser["errors"]
proof = {
    "source_config_hashes_unchanged": len(freeze["source_config_sha256"]),
    "resolved_configs_match_historical_success": True,
    "new_flights": rows,
    "source_snapshot_hashes": len(sources),
    "replayed_poses": sum(r["replay"]["checked_positions"] for r in replays),
    "max_position_error_m": max(r["replay"]["max_position_error_m"] for r in replays),
    "missing_source_frames": sum(r["replay"]["missing_source_frames"] for r in replays),
    "browser_seeks": len(browser["checks"]),
    "browser_playbacks": browser["playbacks"],
    "new_call_budget": json.loads((OUT / "CALL_BUDGET.json").read_text(encoding="utf-8")),
    "model": "gemma4:e2b",
    "cloud_calls": 0,
    "scope": "same geometry repetitions, not independent environment generalization",
}
(OUT / "VERIFICATION.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
print(json.dumps(proof, indent=2))
