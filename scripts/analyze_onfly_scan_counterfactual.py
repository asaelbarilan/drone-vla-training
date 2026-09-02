"""Offline full-yaw visibility audit for a completed local OnFly run.

The audit replays logged controls exactly and asks only whether the semantic
target would enter the ordinary camera after an in-place yaw scan. Simulator
truth is used after the run for diagnosis and is never exposed to the policy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

import numpy as np

from uavlab.contracts import ControlCommand, Frame, Vec3
from uavlab.core.config import ArchitectureConfig, EnvironmentConfig, EpisodeSpec
from uavlab.core.orchestrator import Orchestrator


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def analyze(run_dir: Path, sample_period_s: float) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    events = _events(run_dir / "events.jsonl")
    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    env_cfg = EnvironmentConfig.model_validate(manifest["environment_config"])
    seed = int(manifest["seeds"][0])
    harness = Orchestrator(arch, env_cfg, EpisodeSpec(episode_id="scan_audit", seed=seed))
    params = dict(env_cfg.params)
    params.update(env_cfg.adapter.params)
    params["allow_privileged"] = False
    params["failures"] = []
    env = harness.registry.build("environment", env_cfg.adapter.name, params)
    await env.reset(harness.mission, seed)

    sample_ns = max(1, round(sample_period_s * 1e9))
    next_sample_ns = 0
    rows: list[dict] = []
    controls = [event for event in events if event["event_type"] == "control"]
    for event in controls:
        t_ns = int(event["t_sim_ns"])
        if t_ns >= next_sample_ns:
            position = env.vehicle.position.copy()
            delta = env.goal - position
            distance = float(np.linalg.norm(delta))
            world_bearing = math.atan2(float(delta[1]), float(delta[0]))
            yaw_delta = math.atan2(
                math.sin(world_bearing - env.vehicle.yaw),
                math.cos(world_bearing - env.vehicle.yaw),
            )
            blocked = bool(env._segment_blocked(np.asarray([env.goal]))[0])
            in_range = distance <= env.sensor_range_m
            rows.append(
                {
                    "t_sim_s": t_ns / 1e9,
                    "distance_to_goal_m": distance,
                    "current_yaw_delta_to_target_deg": math.degrees(yaw_delta),
                    "target_line_of_sight": not blocked,
                    "target_in_sensor_range": in_range,
                    "visible_after_full_yaw_scan": in_range and not blocked,
                    "visible_in_current_90deg_view": (
                        in_range and not blocked and abs(yaw_delta) <= math.radians(45.0)
                    ),
                }
            )
            next_sample_ns += sample_ns

        payload = event["payload"]
        await env.step(
            ControlCommand(
                t_sim_ns=t_ns,
                velocity=Vec3(
                    x=float(payload["vx"]),
                    y=float(payload["vy"]),
                    z=float(payload["vz"]),
                ),
                yaw_rate_rps=float(payload["yaw_rate"]),
                frame=Frame.ENU,
            ),
            50_000_000,
        )

    replay_distance = env.status().distance_to_goal_m
    await env.close()
    stored_distance = float(result["metrics"]["distance_to_goal_m"])
    replay_error = abs(replay_distance - stored_distance)
    if replay_error > 1e-9:
        raise RuntimeError(f"exact replay failed: final distance error {replay_error}")

    scan_visible = [row for row in rows if row["visible_after_full_yaw_scan"]]
    current_visible = [row for row in rows if row["visible_in_current_90deg_view"]]
    return {
        "run": run_dir.as_posix(),
        "seed": seed,
        "sample_period_s": sample_period_s,
        "samples": len(rows),
        "scan_visible_samples": len(scan_visible),
        "current_view_visible_samples": len(current_visible),
        "first_scan_visible": scan_visible[0] if scan_visible else None,
        "last_scan_visible": scan_visible[-1] if scan_visible else None,
        "rows": rows,
        "truth_scope": "offline counterfactual only; never exposed to C5",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--sample-period-s", type=float, default=2.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(analyze(args.run_dir, args.sample_period_s))
    text = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
