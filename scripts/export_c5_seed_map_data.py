"""Export compact, replay-audited C5 seed trajectories for end-map figures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from export_end_map_data import _scene, _trajectory


def _episode(run_dir: Path, analysis_dir: Path) -> tuple[int, dict, dict]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    seed = int(result["seed"])
    analysis = json.loads(
        (analysis_dir / f"c5_s{seed}_retained_analysis.json").read_text(encoding="utf-8")
    )
    end = [
        round(float(result["status"]["position"]["x"]), 3),
        round(float(result["status"]["position"]["y"]), 3),
    ]
    path = _trajectory(run_dir / "events.jsonl", stride=10)
    if not path or path[-1] != end:
        path.append(end)
    metrics = result["metrics"]
    return seed, _scene(manifest, seed), {
        "seed": seed,
        "run": run_dir.name,
        "success": bool(result["success"]),
        "termination": result["termination_reason"],
        "end": end,
        "path": path,
        "flightTime": round(float(metrics["flight_time_s"]), 3),
        "pathLength": round(float(metrics["path_length_m"]), 3),
        "finalDistance": round(float(metrics["distance_to_goal_m"]), 3),
        "closestDistance": round(float(analysis["closest_approach"]["distance_to_goal_m"]), 3),
        "visibleDecisionFrames": int(analysis["visible_decision_frames"]),
        "decisionFrames": int(analysis["decision_frames"]),
        "firstVisibleS": (
            None if analysis["first_visible"] is None else analysis["first_visible"]["t_sim_s"]
        ),
        "lastVisibleS": (
            None if analysis["last_visible"] is None else analysis["last_visible"]["t_sim_s"]
        ),
        "monitorAccuracy": round(float(analysis["monitor_visibility_accuracy"]), 4),
        "monitorLabels": analysis["monitor_labels"],
        "recoveries": int(metrics["recovery_triggers"]),
        "collisions": int(metrics["collisions"]),
        "inferenceErrors": int(metrics["inference_errors"]),
        "policyParseErrors": int(metrics["onfly_decision_parse_errors"]),
        "monitorParseErrors": int(metrics["onfly_monitor_parse_errors"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        default=Path("reports/paper_implementation"),
    )
    args = parser.parse_args()

    scenes: dict[int, dict] = {}
    episodes = []
    for run_dir in args.run_dirs:
        seed, scene, episode = _episode(run_dir.resolve(), args.analysis_dir.resolve())
        scenes[seed] = scene
        episodes.append(episode)
    episodes.sort(key=lambda item: item["seed"])
    print(json.dumps({"scenes": scenes, "episodes": episodes}, separators=(",", ":")))


if __name__ == "__main__":
    main()
