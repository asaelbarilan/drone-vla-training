"""D-96: one fixed-goal SUPER diagnostic, with validated historical warm start.

No inference services are constructed. Only the diagnostic supplies a privileged
metric goal. Planner, router, controller, sensor and dynamics code is unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
from probe_passage_4160 import DT_NS, SOURCE_SEQ, SOURCE_TIME_NS, command

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.analysis.flight_debugger import read_events, read_json
from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    MemorySnapshot,
    MissionConstraints,
    MissionSpec,
    PerceptionState,
    SuccessCriteria,
    Vec3,
    WaypointGoal,
)
from uavlab.core.camera import Camera
from uavlab.core.config import ArchitectureConfig
from uavlab.core.decision_router import DecisionRouter
from uavlab.core.frame_store import global_store
from uavlab.interfaces import DecisionContext
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.planning.super import SuperLocalPlanner
from uavlab.plugins.reasoning.onfly import (
    OnFlySemanticGeometricVerifier,
    _depth_at,
    bearing_gated_range,
)

FIXED_TARGET = Vec3(x=20.7940515013, y=21.7478134662, z=2.4739341311)
END_NS = 90_000_000_000
REPLAN_NS = 1_000_000_000


def xyz(v):
    return [v.x, v.y, v.z]


def context(mission, obs, now=None):
    return DecisionContext(
        mission=mission,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns if now is None else now,
        t_wall_ns=0,
        episode_id="privileged_super_passage_4160",
    )


class ObservedSuper(SuperLocalPlanner):
    """Read-only recording around the original planner methods."""

    def plan(self, goal, ctx):
        self.exploratory = []
        return super().plan(goal, ctx)

    def _resample(self, seeds):
        path = super()._resample(seeds)
        self.exploratory = [xyz(point) for point in path]
        return path

    def snapshot(self, outcome, router, obs):
        occupied = sorted(self._occupied)
        radius = math.ceil(self._required_clearance / self.resolution_m)
        # Exactly the discrete disk tested by _blocked, not a drawn guess.
        offsets = [
            (dx, dy)
            for dx in range(-radius, radius + 1)
            for dy in range(-radius, radius + 1)
            if math.hypot(dx, dy) * self.resolution_m <= self._required_clearance
        ]
        blocked = sorted({(x + dx, y + dy) for x, y in occupied for dx, dy in offsets})
        traj = router.source.trajectory if router.source is not None else None
        return {
            "t_s": obs.t_sim_ns / 1e9,
            "position": xyz(obs.position),
            "accepted": outcome.accepted,
            "reason": outcome.reason,
            "diagnostics": asdict(self.last_diagnostics),
            "free_cells": sorted(self._free),
            "occupied_cells": occupied,
            "blocked_cells": blocked,
            "exploratory": self.exploratory,
            "active_trajectory": traj.model_dump(mode="json") if traj else None,
            "attempted_trajectory": outcome.trajectory.model_dump(mode="json")
            if outcome.trajectory
            else None,
        }


def rebuild_envelope(event, obs, policy):
    """Lift the saved integer pixel with the replayed source depth, no VLM."""
    payload = event["payload"]
    prov = payload["provenance"]
    assert obs.rgb.digest == prov["rgb_digest"]
    assert obs.depth.digest == prov["depth_digest"]
    intr = obs.intrinsics
    u = int(prov["model_u"]) * (intr.width - 1) / 999.0
    v = int(prov["model_v"]) * (intr.height - 1) / 999.0
    depth = np.asarray(global_store().get(obs.depth.uri))
    sampled = _depth_at(depth, u, v)
    clipped = min(policy["max_depth_m"], sampled if sampled is not None else policy["max_depth_m"])
    half_fov = math.atan(intr.width / (2 * intr.fx))
    gated = bearing_gated_range(
        clipped, u, fx=intr.fx, cx=intr.cx, half_fov_rad=half_fov, sigma_theta=policy["sigma_theta"]
    )
    assert f"{clipped:.6f}" == prov["sampled_depth_m"]
    assert f"{gated:.6f}" == prov["gated_range_m"]
    camera = Camera(
        width=intr.width,
        height=intr.height,
        fov_deg=math.degrees(2 * half_fov),
        pitch_rad=policy["camera_pitch_rad"],
    )
    point = camera.unproject(
        u, v, max(0.0, gated - policy["goal_standoff_m"]), np.array(xyz(obs.position)), obs.yaw_rad
    )
    return DecisionEnvelope(
        decision_id=event["trace_id"],
        kind=DecisionKind.WAYPOINT,
        payload=WaypointGoal(target=Vec3(x=point[0], y=point[1], z=point[2])),
        source_observation_seq=obs.seq,
        source_t_sim_ns=obs.t_sim_ns,
        produced_t_wall_ns=0,
        produced_t_sim_ns=event["t_sim_ns"],
        confidence=payload["confidence"],
        producer=payload["producer"],
        provenance=prov,
    )


async def run_probe(run, out):
    manifest = read_json(run / "manifest.json")
    events = read_events(run / "events.jsonl")
    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    ec = manifest["environment_config"]
    params = {**ec["params"], **ec["adapter"]["params"], "allow_privileged": False}
    mission = MissionSpec(
        mission_id="super_passage_diagnostic",
        instruction=ec["instruction"],
        task_family=ec["task_family"],
        constraints=MissionConstraints.model_validate(params["constraints"]),
        success=SuccessCriteria.model_validate(params.get("success", {})),
    )
    seed = manifest["seeds"][0]
    if seed != 1061:
        raise ValueError("This diagnostic is restricted to the selected development seed")
    planner = ObservedSuper(**arch.planner.params)
    controller = MockVelocityController(**arch.controller.params)
    verifier = OnFlySemanticGeometricVerifier(**arch.verifier.params)
    for component in (planner, controller, verifier):
        component.reset(mission, seed)
    router = DecisionRouter(
        arch, verifier=verifier, planner=planner, shield=None, controller=controller
    )
    router.reset(mission, seed)
    proposals = defaultdict(list)
    for e in events:
        if e["event_type"] == "decision_proposed" and e["t_sim_ns"] < SOURCE_TIME_NS:
            proposals[e["payload"]["source_observation_seq"]].append(e)
    envelopes = {}

    def record_source(obs):
        for e in proposals.get(obs.seq, []):
            envelopes[e["trace_id"]] = rebuild_envelope(e, obs, arch.policy.params)

    env = DeterministicEnv(**params)
    obs = await env.reset(mission, seed)
    record_source(obs)
    check = {
        "positions_checked": 0,
        "max_position_error_m": 0.0,
        "plans_checked": 0,
        "matching_plan_metadata": 0,
        "controls_checked": 0,
        "max_control_error": 0.0,
    }
    outcomes = {}
    for e in events:
        if e["t_sim_ns"] > SOURCE_TIME_NS:
            break
        kind, payload = e["event_type"], e["payload"]
        if kind == "decision_proposed":
            outcomes[e["trace_id"]] = router.accept(
                envelopes[e["trace_id"]], context(mission, obs, e["t_sim_ns"])
            )
        elif kind == "plan":
            result = outcomes[e["trace_id"]].trajectory
            check["plans_checked"] += 1
            assert result is not None
            actual = {
                "feasible": result.feasible,
                "points": len(result.points),
                "reason": result.reason,
                "planner_metadata": result.metadata,
            }
            expected = {key: payload[key] for key in actual}
            if actual != expected:
                raise ValueError(
                    f"Historical planner mismatch at {e['t_sim_ns']}: {actual} != {expected}"
                )
            check["matching_plan_metadata"] += 1
        elif kind == "control":
            obs = await env.observe()
            record_source(obs)
            error = float(
                np.linalg.norm(
                    np.array(xyz(obs.position)) - [payload[f"position_{a}"] for a in "xyz"]
                )
            )
            check["positions_checked"] += 1
            check["max_position_error_m"] = max(error, check["max_position_error_m"])
            assert error < 1e-9 and obs.t_sim_ns == e["t_sim_ns"]
            predicted, _, _ = router.command_for_tick(context(mission, obs))
            # Monitor overrides have no bearing on historical map reconstruction;
            # only compare commands with the same named motion source.
            if predicted.source_decision_id == e["trace_id"]:
                values = [*xyz(predicted.velocity), predicted.yaw_rate_rps]
                wanted = [payload[k] for k in ("vx", "vy", "vz", "yaw_rate")]
                check["controls_checked"] += 1
                check["max_control_error"] = max(
                    check["max_control_error"],
                    max(abs(a - b) for a, b in zip(values, wanted, strict=True)),
                )
            if obs.t_sim_ns == SOURCE_TIME_NS:
                break
            await env.step(
                command(
                    obs.t_sim_ns, [payload[k] for k in ("vx", "vy", "vz")], payload["yaw_rate"]
                ),
                DT_NS,
            )
    assert obs.seq == SOURCE_SEQ and not env.status().collided
    assert check["max_control_error"] < 1e-9, check
    check["source_frames_checked"] = len(envelopes)
    print("WARM START " + json.dumps(check), flush=True)
    out.mkdir(parents=True, exist_ok=True)
    initial = {"position": xyz(obs.position), "velocity": xyz(obs.velocity), "yaw_rad": obs.yaw_rad}
    historical_last_goal = xyz(planner._last_goal)
    # The diagnostic input is a metric destination: no image-provenance verifier,
    # policy or monitor. Preserve SUPER history and the current router trajectory.
    router.verifier = None
    router.cancel_fixed_reorientation()
    plans, samples = [], []
    next_plan = SOURCE_TIME_NS
    outcome_label = "DURATION_LIMIT"
    while True:
        distance = obs.position.distance_to(FIXED_TARGET)
        collided = env.status().collided
        done = collided or distance <= 0.5 or obs.t_sim_ns >= END_NS
        if collided:
            outcome_label = "COLLISION"
        elif distance <= 0.5:
            outcome_label = "REACHED_FIXED_WAYPOINT"
        ctx = context(mission, obs)
        if not done and obs.t_sim_ns >= next_plan:
            envelope = DecisionEnvelope(
                decision_id=f"fixed-{len(plans)}",
                kind=DecisionKind.WAYPOINT,
                payload=WaypointGoal(target=FIXED_TARGET),
                source_observation_seq=obs.seq,
                source_t_sim_ns=obs.t_sim_ns,
                produced_t_wall_ns=0,
                produced_t_sim_ns=obs.t_sim_ns,
                producer="manual_fixed_destination_diagnostic",
            )
            outcome = router.accept(envelope, ctx)
            plans.append(planner.snapshot(outcome, router, obs))
            next_plan += REPLAN_NS
        control, _, _ = router.command_for_tick(ctx)
        clearance = min(o.distance(env.vehicle.position) for o in env.obstacles)
        sample = {
            "t_s": obs.t_sim_ns / 1e9,
            "elapsed_s": (obs.t_sim_ns - SOURCE_TIME_NS) / 1e9,
            "position": xyz(obs.position),
            "velocity": xyz(obs.velocity),
            "yaw_rad": obs.yaw_rad,
            "command": control.model_dump(mode="json"),
            "plan_index": len(plans) - 1,
            "distance_to_fixed_waypoint_m": distance,
            "surface_clearance_m": clearance,
            "collided": collided,
        }
        samples.append(sample)
        if len(samples) % 2 == 1 or done:
            frame_dir = out / "camera"
            frame_dir.mkdir(exist_ok=True)
            filename = f"{len(samples) - 1:04d}.png"
            global_store().get(obs.rgb.uri).save(frame_dir / filename)
            sample["camera_file"] = "camera/" + filename
        if done:
            break
        await env.step(control, DT_NS)
        obs = await env.observe()
    summary = {
        "privileged_diagnostic": True,
        "source_run": run.name,
        "model_calls": 0,
        "outcome": outcome_label,
        "warm_start_validation": check,
        "initial": initial,
        "historical_last_goal": historical_last_goal,
        "fixed_waypoint": xyz(FIXED_TARGET),
        "elapsed_s": samples[-1]["elapsed_s"],
        "final_position": samples[-1]["position"],
        "final_waypoint_distance_m": samples[-1]["distance_to_fixed_waypoint_m"],
        "min_surface_clearance_m": min(s["surface_clearance_m"] for s in samples),
        "collided": samples[-1]["collided"],
        "planning_attempts": len(plans),
        "accepted_plans": sum(p["accepted"] for p in plans),
        "plan_reasons": dict(Counter(p["diagnostics"]["reason"] for p in plans)),
        "planner_clearance_m": planner._required_clearance,
        "drone_radius_m": env.drone_radius_m,
        "map_resolution_m": planner.resolution_m,
        "replan_period_s": 1.0,
        "source_events_sha256": hashlib.sha256((run / "events.jsonl").read_bytes()).hexdigest(),
        "architecture_config": manifest["architecture_config"],
    }
    data = {
        "summary": summary,
        "plans": plans,
        "samples": samples,
        "obstacles": [
            {"center": o.center.tolist(), "half": o.half.tolist()} for o in env.obstacles
        ],
    }
    (out / "trace.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps({k: v for k, v in summary.items() if k != "architecture_config"}, indent=2),
        flush=True,
    )
    await env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, default=Path("runs/c5_guarded_monitor_20260911_s1061"))
    parser.add_argument("--out", type=Path, default=Path("reports/super_passage_probe_20260912"))
    args = parser.parse_args()
    asyncio.run(run_probe(args.run, args.out))
