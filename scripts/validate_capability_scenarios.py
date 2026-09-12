"""Fly scripted geometry fixtures for eight tasks and export the existing debugger.

No VLM, planner, or architecture performance is evaluated. Control paths are
privileged positive controls proving task mechanics and physical reachability.
"""

import argparse
import asyncio
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from uavlab.adapters.gym.capability_env import SCENARIOS, CapabilityEnv, point
from uavlab.analysis.flight_debugger import export
from uavlab.contracts import ControlCommand, MissionSpec, Vec3
from uavlab.contracts.mission import MissionConstraints, SuccessCriteria
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.frame_store import global_store


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def event(kind, t_ns, seq, payload):
    return dict(
        event_type=kind,
        t_sim_ns=t_ns,
        seq=seq,
        component="scripted_fixture",
        trace_id=None,
        payload=payload,
    )


async def record(name, root, seed=1061):
    config = load_environment("capability_" + name)
    env = CapabilityEnv(**config.params)
    mission = MissionSpec(
        mission_id="scripted_fixture",
        instruction=config.instruction,
        task_family=config.task_family,
        success=SuccessCriteria.model_validate(config.params["success"]),
        constraints=MissionConstraints.model_validate(config.params["constraints"]),
    )
    obs = await env.reset(mission, seed)
    folder = root / ("fixture_" + name + f"_s{seed}")
    folder.mkdir(parents=True, exist_ok=False)
    global_store().get(obs.rgb.uri).save(folder / "initial.png")
    routes = {
        "known_goal": [env.goal.copy()],
        "visible_target": [env.goal.copy()],
        "turn_search": [env.goal.copy()],
        "overturned_vehicle": [env.goal.copy()],
        "conditional_gate": [
            point(4, -5 if env.left_blocked else 5),
            point(11, -5 if env.left_blocked else 5),
            env.goal.copy(),
        ],
        "ordered_visit": [p.copy() for p in env.subgoals] + [env.goal.copy()],
        "closing_passage": [point(6), point(8, 14), point(18, 14), env.goal.copy()],
        "follow_target": [],
    }
    route = routes[name]
    leg = 0
    events = []
    event_count = 0
    for _ in range(1200):
        obs = await env.observe()
        t = env._t_ns / 1e9
        position = env.vehicle.position
        if name == "follow_target":
            destination = env.goal - point(5, 0, 0)
            velocity = (destination - position) * 1.5 + point(0.7, 0, 0)
            face = env.goal - position
        else:
            destination = route[leg]
            if (
                np.linalg.norm(destination - position) < 0.5
                and leg < len(route) - 1
                and (name != "ordered_visit" or env._subgoals_done)
            ):
                leg += 1
                destination = route[leg]
            velocity = (destination - position) * 1.5
            face = destination - position
            if name == "turn_search" and t < 2.8:
                velocity[:] = 0
        speed = np.linalg.norm(velocity)
        if speed > 1.8:
            velocity *= 1.8 / speed
        desired_yaw = math.atan2(face[1], face[0])
        error = math.atan2(
            math.sin(desired_yaw - env.vehicle.yaw), math.cos(desired_yaw - env.vehicle.yaw)
        )
        yaw_rate = float(np.clip(error * 2, -1.0, 1.0)) if np.linalg.norm(face[:2]) > 0.1 else 0.0
        payload = dict(
            position_x=obs.position.x,
            position_y=obs.position.y,
            position_z=obs.position.z,
            vx=float(velocity[0]),
            vy=float(velocity[1]),
            vz=float(velocity[2]),
            yaw_rate=yaw_rate,
        )
        events.append(event("control", env._t_ns, len(events), payload))
        await env.step(
            ControlCommand(
                t_sim_ns=env._t_ns,
                velocity=Vec3(x=velocity[0], y=velocity[1], z=velocity[2]),
                yaw_rate_rps=yaw_rate,
            ),
            50_000_000,
        )
        for task_event in env.task_events[event_count:]:
            events.append(event("scenario_event", env._t_ns, len(events), task_event))
        event_count = len(env.task_events)
        if env.status().collided or env.status().out_of_bounds:
            break
        # Static fixtures demonstrate a physical stop, not just a fly-by.
        if env.status().task_complete and (
            name == "follow_target" or np.linalg.norm(env.vehicle.velocity) < 0.2
        ):
            break
    status = env.status()
    success = bool(status.task_complete and not status.collided and not status.out_of_bounds)
    result = dict(
        success=success,
        termination_reason="goal_reached" if success else "timeout",
        sim_duration_s=env._t_ns / 1e9,
        used_privileged_observations=True,
        validation_kind="scripted geometry fixture; NOT architecture performance",
        metrics={
            "distance_to_goal_m": status.distance_to_goal_m,
            "collisions": float(status.collision_count),
        },
        status=status.model_dump(mode="json"),
    )
    arch = load_architecture("c0").model_copy(
        update={"id": "scripted_control_fixture", "name": "Scripted geometry fixture"}
    )
    manifest = dict(
        architecture_config=arch.model_dump(mode="json"),
        environment_config=config.model_dump(mode="json"),
        seeds=[seed],
        git_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        git_dirty=bool(subprocess.check_output(["git", "diff", "--name-only"], text=True)),
        validation_kind=result["validation_kind"],
        fixture_driver=str(Path(__file__).resolve()),
    )
    write_json(folder / "manifest.json", manifest)
    write_json(folder / "result.json", result)
    (folder / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )
    final = await env.observe()
    global_store().get(final.rgb.uri).save(folder / "final.png")
    await env.close()
    print(
        f"{name}: {'PASS' if success else 'FAIL'} at {result['sim_duration_s']:.2f}s, "
        f"collisions={status.collision_count}",
        flush=True,
    )
    return folder, result


async def main(root, output):
    root.mkdir(parents=True, exist_ok=True)
    results = [await record(name, root) for name in SCENARIOS]
    summary = await export([p for p, _ in results], output)
    write_json(
        root / "SUMMARY.json",
        dict(
            validation_kind="scripted fixtures, no model calls",
            results={p.name: r for p, r in results},
            replay=summary,
        ),
    )
    if not all(r["success"] for _, r in results):
        raise SystemExit("Some physical fixture paths failed; see preserved recordings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("reports/capability_scenarios_20260912"))
    parser.add_argument(
        "--dashboard", type=Path, default=Path("reports/debugger/capability_scenarios.html")
    )
    args = parser.parse_args()
    asyncio.run(main(args.out, args.dashboard))
