"""Export compact trajectory/scene data from a completed local-sim report."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# The visualization exporter consumes resolved JSON manifests and never parses
# YAML.  Keep the package's optional YAML loader from blocking this tiny tool in
# the dependency-light workspace runtime.
sys.modules.setdefault("yaml", types.ModuleType("yaml"))

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import MissionSpec


def _scene(manifest: dict, seed: int) -> dict:
    config = manifest["environment_config"]
    params = dict(config["params"])
    mission = MissionSpec(
        mission_id=f"map-seed-{seed}",
        instruction=config["instruction"],
        task_family=config["task_family"],
        success=params.pop("success"),
        constraints=params.pop("constraints"),
        allowed_skills=tuple(params.pop("allowed_skills", ())),
    )
    env = DeterministicEnv(**params)
    asyncio.run(env.reset(mission, seed))
    return {
        "goal": np.round(env.goal[:2], 4).tolist(),
        "goalRadius": env.goal_radius_m,
        "obstacles": [
            {
                "center": np.round(item.center[:2], 4).tolist(),
                "half": np.round(item.half[:2], 4).tolist(),
            }
            for item in env.obstacles
        ],
        "subgoals": [np.round(item[:2], 4).tolist() for item in env.subgoals],
    }


def _trajectory(events_path: Path, stride: int = 10) -> list[list[float]]:
    """Read onboard positions logged by the controller.

    Older reports predate pose logging, so retain the old command-integration
    fallback for historical visualization only. New professor-map runs always
    take the direct observation path and report its provenance.
    """
    logged: list[list[float]] = []
    controls: list[dict] = []
    tick = 0
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event["event_type"] != "control":
            continue
        payload = event["payload"]
        controls.append(payload)
        if "position_x" in payload:
            if tick % stride == 0:
                logged.append([round(float(payload["position_x"]), 3), round(float(payload["position_y"]), 3)])
            tick += 1
    if logged:
        return logged

    position = np.array([0.0, 0.0, 3.0])
    velocity = np.zeros(3)
    points = [[0.0, 0.0]]
    dt = 0.05
    alpha = dt / 0.35
    tick = 0
    for payload in controls:
        target = np.array([payload["vx"], payload["vy"], payload["vz"]], dtype=float)
        speed = float(np.linalg.norm(target))
        if speed > 5.0:
            target *= 5.0 / speed
        velocity += (target - velocity) * alpha
        position += velocity * dt
        tick += 1
        if tick % stride == 0:
            points.append(np.round(position[:2], 3).tolist())
    final = np.round(position[:2], 3).tolist()
    if points[-1] != final:
        points.append(final)
    return points


def export(report_dir: Path) -> dict:
    episodes = []
    scenes: dict[int, dict] = {}
    for episode_dir in sorted((report_dir / "episodes").iterdir()):
        if not episode_dir.is_dir():
            continue
        result = json.loads((episode_dir / "result.json").read_text(encoding="utf-8"))
        architecture = result["architecture_id"]
        seed = int(result["seed"])
        environment = result["environment_id"]
        manifest_path = report_dir / "manifests" / f"{architecture}__{environment}" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scenes.setdefault(seed, _scene(manifest, seed))
        status = result["status"]
        end = [round(status["position"]["x"], 3), round(status["position"]["y"], 3)]
        path = _trajectory(episode_dir / "events.jsonl")
        if not path or path[-1] != end:
            path.append(end)
        episodes.append(
            {
                "architecture": architecture,
                "environment": environment,
                "seed": seed,
                "success": bool(result["success"]),
                "termination": result["termination_reason"],
                "flightTime": result["metrics"]["flight_time_s"],
                "distanceToGoal": result["metrics"]["distance_to_goal_m"],
                "pathLength": result["metrics"]["path_length_m"],
                "collided": bool(status["collided"]),
                "collisions": int(status["collision_count"]),
                # Count foundation-model policy/reasoner calls, not simulated
                # perception bookkeeping. The oracle ceiling must therefore
                # report zero FM calls rather than its sensor update count.
                "modelCalls": (
                    0
                    if architecture == "c0"
                    else int(
                        result["metrics"].get("inference_calls_policy", 0)
                        + result["metrics"].get("inference_calls_reasoner", 0)
                    )
                ),
                "error": result.get("error"),
                "end": end,
                "path": path,
                "trajectorySource": "logged onboard pose",
            }
        )
    return {"source": report_dir.name, "scenes": scenes, "episodes": episodes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.report_dir.resolve()), separators=(",", ":")))


if __name__ == "__main__":
    main()
