"""Re-render a stored run from its event log, without re-running the model.

A real-model episode costs minutes of inference and is not free to repeat, so
looking at one must not require flying it again. Everything needed is already in
`events.jsonl`: the environment config and seed are in the manifest, and every
command the controller issued is a `control` event. Replaying those commands
through the deterministic environment reproduces the pose and the camera frame
exactly — this is the same mechanism as the exact-replay checks in the OnFly
reports, which reproduce final distance to 0.0 m.

What this buys, beyond convenience: the video shows the trajectory that was
actually scored, not a fresh one that might differ. For a stochastic backend
that distinction is the difference between evidence and illustration.

The decision overlay is the point of the thing. A plan view alone shows a
vehicle wandering; adding where the model *pointed*, and whether the goal was in
frame at all, is what separates "it could not see the target" from "it saw the
target and went elsewhere".
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def _load(run_dir: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return manifest, events


def replay(run_dir: Path, stride: int = 4):
    """Re-fly a stored run's commands. Returns (scene, samples, decisions)."""
    from uavlab.adapters.gym.deterministic_env import DeterministicEnv
    from uavlab.analysis.replay_video import Sample, Scene
    from uavlab.contracts import ControlCommand, MissionSpec, Vec3
    from uavlab.core.config import EnvironmentConfig
    from uavlab.core.frame_store import global_store
    from uavlab.core.registry import REGISTRY

    run_dir = Path(run_dir)
    manifest, events = _load(run_dir)
    env_cfg = EnvironmentConfig.model_validate(manifest["environment_config"])
    seed = int(manifest["seeds"][0])

    params = dict(env_cfg.params)
    params["render"] = True
    env = REGISTRY.build("environment", env_cfg.adapter.name, params)
    mission = MissionSpec(
        mission_id=f"replay:{run_dir.name}",
        instruction=env_cfg.instruction,
        task_family=env_cfg.task_family,
        success=params.get("success", {}),
        constraints=params.get("constraints", {}),
        allowed_skills=tuple(params.get("allowed_skills", ())),
    )
    asyncio.run(env.reset(mission, seed))

    scene = Scene(
        obstacles=[(o.center.copy(), o.half.copy()) for o in env.obstacles],
        landmarks=[(m.position.copy(), m.label, bool(m.is_target)) for m in env.landmarks],
        goal=np.asarray(env.goal, dtype=float).copy(),
        geofence_m=float(mission.constraints.geofence_radius_m),
        goal_radius_m=float(env.goal_radius_m),
    )

    controls = [e for e in events if e["event_type"] == "control"]
    # Decisions are indexed by the observation they were made from, so the
    # overlay can say what the model was looking at rather than merely when.
    decisions = {
        e["payload"].get("source_observation_seq"): e["payload"]
        for e in events
        if e["event_type"] == "decision_executed"
    }

    dt_ns = int(1e9 / max(env_cfg.params.get("control_hz", 20.0), 1.0)) if False else None
    if len(controls) > 1:
        deltas = [b["t_sim_ns"] - a["t_sim_ns"] for a, b in zip(controls, controls[1:])]
        dt_ns = int(np.median([d for d in deltas if d > 0]) or 5_000_000)
    else:
        dt_ns = 50_000_000

    samples: list[Sample] = []
    for i, event in enumerate(controls):
        p = event["payload"]
        command = ControlCommand(
            t_sim_ns=int(event["t_sim_ns"]),
            velocity=Vec3(x=float(p["vx"]), y=float(p["vy"]), z=float(p["vz"])),
            yaw_rate_rps=float(p["yaw_rate"]),
        )
        asyncio.run(env.step(command, dt_ns))
        if i % stride:
            continue
        status = env.status()
        image = global_store().get(f"frame://{env._frame_ns}/rgb/{max(env._seq - 1, 0)}")
        samples.append(
            Sample(
                t_s=env._t_ns / 1e9,
                position=env.vehicle.position.copy(),
                yaw=float(env.vehicle.yaw),
                speed=float(np.linalg.norm(env.vehicle.velocity)),
                distance_to_goal=float(status.distance_to_goal_m),
                collided=bool(status.collided),
                frame=image.copy() if image is not None else None,
            )
        )
    return scene, samples, decisions, manifest


def goal_bearing_deg(sample, goal: np.ndarray) -> float:
    """Signed bearing to the goal in the body frame. 0 is dead ahead."""
    dx, dy = goal[0] - sample.position[0], goal[1] - sample.position[1]
    rel = math.atan2(dy, dx) - sample.yaw
    return math.degrees((rel + math.pi) % (2 * math.pi) - math.pi)


def render(run_dir: Path, out_path: Path, fps: int = 15, stride: int = 4, fov_deg: float = 90.0):
    """Write an mp4 of a stored run, with the goal-bearing overlay."""
    import cv2

    from uavlab.analysis import replay_video as rv

    scene, samples, _decisions, manifest = replay(run_dir, stride)
    if not samples:
        raise RuntimeError(f"no control events in {run_dir}")
    project = rv._Projector(scene, samples)
    width, height = rv.PANEL * 2 + rv.MARGIN, rv.PANEL + rv.BAR_H
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"could not open a video writer for {out_path}")

    half = fov_deg / 2.0
    name = manifest.get("architecture_id", run_dir.name)
    try:
        for i, s in enumerate(samples):
            canvas = np.full((height, width, 3), rv.BG, dtype=np.uint8)
            plan = rv._plan_panel(scene, samples, i, project)

            # The camera's field of view, drawn on the map. Without it a viewer
            # cannot tell whether the target was even available to be seen.
            p = project(s.position[:2])
            for sign in (-1, 1):
                a = s.yaw + sign * math.radians(half)
                end = (int(p[0] + 90 * math.cos(a)), int(p[1] - 90 * math.sin(a)))
                cv2.line(plan, p, end, (70, 70, 70), 1, cv2.LINE_AA)

            canvas[rv.BAR_H:, : rv.PANEL] = plan
            canvas[rv.BAR_H:, rv.PANEL + rv.MARGIN :] = rv._camera_panel(s)

            bearing = goal_bearing_deg(s, scene.goal)
            in_fov = abs(bearing) <= half
            cv2.putText(canvas, f"{name}   seed {manifest['seeds'][0]}", (rv.MARGIN, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, rv.INK, 1, cv2.LINE_AA)
            cv2.putText(canvas,
                        f"t {s.t_s:5.1f}s    to goal {s.distance_to_goal:5.1f} m    "
                        f"goal bearing {bearing:+6.1f} deg",
                        (rv.MARGIN, rv.BAR_H + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                        rv.INK, 1, cv2.LINE_AA)
            cv2.putText(canvas,
                        "GOAL IN FIELD OF VIEW" if in_fov else "goal outside field of view",
                        (rv.MARGIN, rv.BAR_H + 52), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        rv.GOOD if in_fov else rv.BAD, 1, cv2.LINE_AA)
            writer.write(canvas)
        for _ in range(fps):
            writer.write(canvas)
    finally:
        writer.release()
    return {"video": str(out_path), "frames": len(samples),
            "final_distance_m": round(samples[-1].distance_to_goal, 2)}
