"""Exact saved-source geometry diagnosis; no model calls or new flight."""

import asyncio
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.adapters.gym.capability_env import CapabilityEnv
from uavlab.contracts import ControlCommand, MissionSpec, Vec3
from uavlab.core.camera import Camera
from uavlab.core.frame_store import global_store
from uavlab.plugins.reasoning.onfly import _depth_at

OUT = Path("reports/hover_stable_20260914")


async def audit(seed):
    root = Path(f"runs/c5_hover_stable_20260914_s{seed}")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    config = manifest["environment_config"]
    mission = MissionSpec(
        mission_id="saved-only",
        instruction=config["instruction"],
        task_family=config["task_family"],
        success=config["params"]["success"],
        constraints=config["params"]["constraints"],
    )
    env = CapabilityEnv(**config["params"])
    await env.reset(mission, seed)
    lines = (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    calls = {
        c["observation_seq"]: c
        for p in (root / "debug/calls").glob("*.json")
        if (c := json.loads(p.read_text(encoding="utf-8")))["role"] == "monitor"
        and c["status"] == "complete"
    }
    controls = [e for e in events if e["event_type"] == "control"]
    rows = []
    approach = None
    poses = []
    for event in controls:
        obs = await env.observe()
        p = event["payload"]
        origin = np.array([obs.position.x, obs.position.y, obs.position.z])
        assert np.linalg.norm(origin - [p["position_x"], p["position_y"], p["position_z"]]) < 1e-7
        poses.append(
            {
                "t": obs.t_sim_ns / 1e9,
                "position": origin.tolist(),
                "yaw_deg": math.degrees(obs.yaw_rad),
                "true_hover_s": env.status().extras["hover_streak_s"],
                "true_visible": env.status().goal_visible,
            }
        )
        if obs.seq in calls:
            c = calls[obs.seq]
            r = json.loads(c["response"])
            assert np.array_equal(
                np.asarray(global_store().get(obs.rgb.uri)),
                np.asarray(Image.open(root / c["image_files"][-1]).convert("RGB")),
            )
            u, v = r.get("u"), r.get("v")
            depth = np.asarray(global_store().get(obs.depth.uri))
            intr = obs.intrinsics
            d = (
                _depth_at(depth, u * (intr.width - 1) / 999, v * (intr.height - 1) / 999, patch=0)
                if u is not None and v is not None
                else None
            )
            row = {
                "call": c["id"],
                "source_t": obs.t_sim_ns / 1e9,
                "available_t": c["completed_t_sim_ns"] / 1e9,
                "reply": r,
                "depth_m": d,
            }
            if d is not None:
                cam = Camera(width=intr.width, height=intr.height, pitch_rad=-0.1)
                point = cam.unproject(
                    u * (intr.width - 1) / 999, v * (intr.height - 1) / 999, d, origin, obs.yaw_rad
                )
                delta = point - origin
                if approach is None:
                    approach = delta.copy()
                    approach[2] = 0
                    approach /= np.linalg.norm(approach)
                along = float(delta @ approach)
                cross = float(np.linalg.norm((delta - along * approach)[:2]))
                row.update(
                    point=point.tolist(),
                    range_m=float(np.linalg.norm(delta)),
                    along_m=along,
                    cross_m=cross,
                    source_speed=obs.velocity.norm(),
                )
            rows.append(row)
        await env.step(
            ControlCommand(
                t_sim_ns=event["t_sim_ns"],
                velocity=Vec3(x=p["vx"], y=p["vy"], z=p["vz"]),
                yaw_rate_rps=p["yaw_rate"],
            ),
            50_000_000,
        )
    for row in rows:
        matches = [
            e
            for e in events
            if e["event_type"] == "monitor" and e["t_sim_ns"] / 1e9 == row["available_t"]
        ]
        if matches:
            row["saved_monitor"] = matches[0]["payload"]
    return {
        "seed": seed,
        "poses_checked": len(poses),
        "source_images_checked": len(rows),
        "monitors": rows,
        "pose_samples": [
            p
            for p in poses
            if p["t"] in (9.2, 11.2, 13.2, 15.2, 17.2, 18.0, 18.95, 19.0, 20.0, 21.0, 22.0)
        ],
    }


async def main():
    result = [await audit(s) for s in (1060, 1062)]
    (OUT / "SOURCE_AUDIT.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for run in result:
        print("seed", run["seed"])
        for r in run["monitors"]:
            if 9 < r["source_t"] < 17:
                print({k: v for k, v in r.items() if k not in ("reply", "saved_monitor")})
        print(run["pose_samples"])


if __name__ == "__main__":
    asyncio.run(main())
