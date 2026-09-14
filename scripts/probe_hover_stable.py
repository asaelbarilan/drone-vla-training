"""D-110 saved-control geometry/heading countercheck, no inference or flight claim."""

import asyncio
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from uavlab.adapters.gym.capability_env import CapabilityEnv
from uavlab.contracts import ControlCommand, MissionSpec, Vec3
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.reasoning.onfly_hover import OnFlyHoverMonitor

OUT = Path("reports/hover_stable_20260914")


async def main():
    root = Path("runs/c5_hover_repeat_20260914_s1062")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    config = manifest["environment_config"]
    mission = MissionSpec(
        mission_id="saved-probe",
        instruction=config["instruction"],
        task_family=config["task_family"],
        success=config["params"]["success"],
        constraints=config["params"]["constraints"],
    )
    env = CapabilityEnv(**config["params"])
    await env.reset(mission, 1062)
    audit = json.loads(
        Path("reports/hover_repeat_20260914/DEPARTURE_AUDIT.json").read_text(encoding="utf-8")
    )[1]
    row = next(r for r in audit["monitors"] if r["available_t"] == 15.2)
    first = next(r for r in audit["monitors"] if "point" in r)
    monitors = []
    for fixed in (False, True):
        m = OnFlyHoverMonitor(
            current_grounding=True,
            target_bound_stop=True,
            structured_evidence=True,
            arrival_memory_s=4,
            camera_pitch_rad=-0.1,
            stable_hover_reference=fixed,
        )
        m.reset(mission, 1062)
        m._initial_position = Vec3(x=0, y=0, z=3)
        direction = np.array(first["point"]) - np.array([0, 0, 3])
        direction[2] = 0
        direction /= np.linalg.norm(direction)
        m._approach = direction
        m._tracked_target = np.array(row["point"])
        m._tracked_target_t_ns = int(row["source_t"] * 1e9)
        m._tracked_confirmations = 2
        monitors.append(m)
    ctl = MockVelocityController(yaw_hold_radius_m=0.25, max_yaw_rate_rps=0.4)
    ctl.reset(mission, 1062)
    poses = 0
    checks = []
    for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e["event_type"] != "control":
            continue
        obs = await env.observe()
        p = e["payload"]
        poses += 1
        assert (
            np.linalg.norm(
                np.array([obs.position.x, obs.position.y, obs.position.z])
                - [p["position_x"], p["position_y"], p["position_z"]]
            )
            < 1e-7
        )
        if obs.t_sim_ns == 9_200_000_000:
            ctl._held_yaw = obs.yaw_rad
        if obs.t_sim_ns == 13_950_000_000:
            old, new = [m._hover_geometry(obs) for m in monitors]
            assert not old and new
            checks.append(
                dict(t=13.95, old_geometry=bool(old), fixed_geometry=bool(new), point=row["point"])
            )
        if obs.t_sim_ns == 18_000_000_000:
            residual = Vec3(x=p["vx"] / 1.1, y=p["vy"] / 1.1, z=0)
            yaw = ctl._yaw_rate_toward(residual, SimpleNamespace(observation=obs))
            assert p["yaw_rate"] < 0 and yaw > 0
            checks.append(
                dict(
                    t=18,
                    old_yaw_rate=p["yaw_rate"],
                    fixed_return_to_held_heading_rate=yaw,
                    translation_speed=math.hypot(p["vx"], p["vy"]),
                )
            )
        await env.step(
            ControlCommand(
                t_sim_ns=e["t_sim_ns"],
                velocity=Vec3(x=p["vx"], y=p["vy"], z=p["vz"]),
                yaw_rate_rps=p["yaw_rate"],
            ),
            50_000_000,
        )
    assert len(checks) == 2
    OUT.mkdir(parents=True, exist_ok=True)
    result = dict(
        saved_run=root.name,
        poses_matched=poses,
        checks=checks,
        scope="Saved-pose component checks; not a counterfactual flight; zero inference",
    )
    (OUT / "SAVED_PROBE.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
