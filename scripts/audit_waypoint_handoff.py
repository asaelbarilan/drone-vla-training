"""D-97: exact historical source-to-waypoint audit; no inference or new flight.

Scene geometry is read for diagnostic ray checks and drawing only. All actual
replayed policies, accepted waypoints and controls use the saved sensor path.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from probe_passage_4160 import DT_NS, command
from probe_super_passage_4160 import ObservedSuper, context, rebuild_envelope, xyz

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.adapters.gym.render import _box_corners, _convex_hull
from uavlab.analysis.flight_debugger import read_events, read_json
from uavlab.contracts import MissionConstraints, MissionSpec, SuccessCriteria
from uavlab.core.config import ArchitectureConfig
from uavlab.core.decision_router import DecisionRouter
from uavlab.core.frame_store import global_store
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.reasoning.onfly import OnFlySemanticGeometricVerifier, _depth_at

RUN = Path("runs/c5_guarded_monitor_20260911_s1061")
OUT = Path("reports/waypoint_handoff_audit_20260912")


def finite(value):
    return float(value) if math.isfinite(value) else None


def ray_box_depth(origin, direction, center, half):
    """Slab intersection; direction has camera-forward depth one, not unit norm."""
    low, high = center - half, center + half
    enter, leave = -math.inf, math.inf
    for axis in range(3):
        if abs(direction[axis]) < 1e-12:
            if not low[axis] <= origin[axis] <= high[axis]:
                return math.inf
            continue
        first = (low[axis] - origin[axis]) / direction[axis]
        second = (high[axis] - origin[axis]) / direction[axis]
        enter, leave = max(enter, min(first, second)), min(leave, max(first, second))
    return max(enter, 0.0) if leave >= max(enter, 0.0) else math.inf


def geometric_depth(env, obs, u, v):
    origin = np.array(xyz(obs.position))
    direction = env._camera.unproject(u, v, 1.0, origin, obs.yaw_rad) - origin
    distances = [ray_box_depth(origin, direction, o.center, o.half) for o in env.obstacles]
    idx = int(np.argmin(distances))
    hit = distances[idx]
    return (
        finite(hit),
        idx if math.isfinite(hit) else None,
        ((origin + direction * hit).tolist() if math.isfinite(hit) else None),
    )


def owner_mask(env, obs):
    """Reproduce renderer draw ownership and validate the entire depth image."""
    cam = env._camera
    origin = np.array(xyz(obs.position))
    owners = Image.new("I", (cam.width, cam.height), 0)
    depth = Image.new("F", (cam.width, cam.height), float("inf"))
    draw, depths = ImageDraw.Draw(owners), ImageDraw.Draw(depth)
    records = {}
    drawables = []
    for i, o in enumerate(env.obstacles):
        drawables.append((float(np.linalg.norm(o.center - origin)), "box", i, o))
    visible = {hit.label for hit in obs.semantic_hits}
    for i, mark in enumerate(env.landmarks):
        if mark.label in visible:
            drawables.append((float(np.linalg.norm(mark.position - origin)), "mark", i, mark))
    drawables.sort(key=lambda item: -item[0])
    for distance, kind, idx, item in drawables:
        if distance > 90:
            continue
        if kind == "box":
            corners = _box_corners(item.center, item.half)
            pixels, values = cam.project(corners, origin, obs.yaw_rad)
            keep = values > 0.2
            if keep.sum() < 3:
                continue
            polygon = _convex_hull([(float(x), float(y)) for x, y in pixels[keep]])
            if len(polygon) < 3:
                continue
            owner = idx + 1
            value = float(values[keep].min())
            draw.polygon(polygon, fill=owner)
            depths.polygon(polygon, fill=value)
            corner = int(np.flatnonzero(keep)[np.argmin(values[keep])])
            records[owner] = {
                "kind": "obstacle",
                "index": idx,
                "painted_depth_m": value,
                "depth_corner_world": corners[corner].tolist(),
                "depth_corner_pixel": pixels[corner].tolist(),
            }
        else:
            pixels, values = cam.project(np.array([item.position]), origin, obs.yaw_rad)
            if values[0] <= 0.2:
                continue
            u, v = map(float, pixels[0])
            radius = max(2.0, cam.focal_px * 1.6 / max(values[0], 1e-3))
            rect = [u - radius * 0.55, v - radius * 2.2, u + radius * 0.55, v + radius * 0.9]
            owner = 1000 + idx
            draw.rectangle(rect, fill=owner)
            depths.rectangle(rect, fill=float(values[0]))
            records[owner] = {
                "kind": "landmark_billboard",
                "label": item.label,
                "painted_depth_m": float(values[0]),
            }
    actual = global_store().get(obs.depth.uri)
    assert np.array_equal(np.asarray(depth), actual), "Depth ownership reconstruction mismatch"
    return np.asarray(owners), records


def capture_source(env, obs, event, policy):
    prov = event["payload"]["provenance"]
    envelope = rebuild_envelope(event, obs, policy)
    u = int(prov["model_u"]) * (obs.intrinsics.width - 1) / 999.0
    v = int(prov["model_v"]) * (obs.intrinsics.height - 1) / 999.0
    x, y = round(u), round(v)
    depth = global_store().get(obs.depth.uri)
    owners, records = owner_mask(env, obs)
    owner = records.get(int(owners[y, x]), {"kind": "background"})
    patch = depth[max(0, y - 2) : y + 3, max(0, x - 2) : x + 3]
    ray, obstacle, hit = geometric_depth(env, obs, u, v)
    true_patch = [
        geometric_depth(env, obs, a, b)[0]
        for b in range(max(0, y - 2), min(obs.intrinsics.height, y + 3))
        for a in range(max(0, x - 2), min(obs.intrinsics.width, x + 3))
    ]
    finite_patch = [t for t in true_patch if t is not None and t > 0.05]
    raw = _depth_at(depth, u, v)
    source = {
        "id": event["trace_id"],
        "available_s": event["t_sim_ns"] / 1e9,
        "source_s": obs.t_sim_ns / 1e9,
        "source_seq": obs.seq,
        "source_position": xyz(obs.position),
        "source_velocity": xyz(obs.velocity),
        "source_yaw_rad": obs.yaw_rad,
        "model_pixel": [int(prov["model_u"]), int(prov["model_v"])],
        "pixel": [u, v],
        "pixel_rgb": list(global_store().get(obs.rgb.uri).getpixel((x, y))),
        "owner": owner,
        "center_depth_m": finite(float(depth[y, x])),
        "raw_patch_median_m": raw,
        "patch_depth_m": [[finite(t) for t in row] for row in patch],
        "capped_depth_m": float(prov["sampled_depth_m"]),
        "gated_depth_m": float(prov["gated_range_m"]),
        "world_waypoint": xyz(envelope.payload.target),
        "distance_from_source_m": obs.position.distance_to(envelope.payload.target),
        "exact_ray_box_depth_m": ray,
        "exact_ray_obstacle": obstacle,
        "exact_ray_hit": hit,
        "exact_box_patch_median_m": float(np.median(finite_patch)) if finite_patch else None,
        "exact_box_patch_m": [true_patch[i : i + 5] for i in range(0, len(true_patch), 5)],
        "depth_overstatement_m": raw - ray if raw is not None and ray is not None else None,
        "rgb_digest": obs.rgb.digest,
        "depth_digest": obs.depth.digest,
        "history_pixel": prov.get("history_pixel"),
        "history_model_point": prov.get("history_model_point"),
        "rgb_file": f"frames/{obs.seq:04d}.png",
    }
    folder = OUT / "frames"
    folder.mkdir(parents=True, exist_ok=True)
    global_store().get(obs.rgb.uri).save(OUT / source["rgb_file"])
    np.savez_compressed(folder / f"{obs.seq:04d}_depth.npz", depth=depth)
    return envelope, source


async def audit():
    OUT.mkdir(parents=True, exist_ok=True)
    m = read_json(RUN / "manifest.json")
    events = read_events(RUN / "events.jsonl")
    arch = ArchitectureConfig.model_validate(m["architecture_config"])
    ec = m["environment_config"]
    params = {**ec["params"], **ec["adapter"]["params"], "allow_privileged": False}
    mission = MissionSpec(
        mission_id="handoff_audit",
        instruction=ec["instruction"],
        task_family=ec["task_family"],
        constraints=MissionConstraints.model_validate(params["constraints"]),
        success=SuccessCriteria.model_validate(params.get("success", {})),
    )
    seed = m["seeds"][0]
    assert seed == 1061
    planner = ObservedSuper(**arch.planner.params)
    controller = MockVelocityController(**arch.controller.params)
    verifier = OnFlySemanticGeometricVerifier(**arch.verifier.params)
    for component in (planner, controller, verifier):
        component.reset(mission, seed)
    router = DecisionRouter(
        arch, verifier=verifier, planner=planner, shield=None, controller=controller
    )
    router.reset(mission, seed)
    grouped = defaultdict(list)
    for e in events:
        if e["event_type"] == "decision_proposed":
            grouped[e["payload"]["source_observation_seq"]].append(e)
    sources = {}
    envelopes = {}
    outcomes = {}
    controls = []
    check = {
        "poses": 0,
        "controls": 0,
        "plans": 0,
        "sources": 0,
        "max_position_error_m": 0.0,
        "max_control_error": 0.0,
    }

    def record(obs):
        for e in grouped.get(obs.seq, []):
            envelope, source = capture_source(env, obs, e, arch.policy.params)
            sources[e["trace_id"]] = source
            envelopes[e["trace_id"]] = envelope
            check["sources"] += 1

    env = DeterministicEnv(**params)
    obs = await env.reset(mission, seed)
    record(obs)
    previous = None
    for e in events:
        kind, p = e["event_type"], e["payload"]
        if kind == "decision_proposed":
            src = sources[e["trace_id"]]
            envelope = envelopes[e["trace_id"]]
            outcome = router.accept(envelope, context(mission, obs, e["t_sim_ns"]))
            outcomes[e["trace_id"]] = outcome
            accepted_envelope = (
                outcome.verification.replacement
                if (outcome.verification and outcome.verification.replacement)
                else envelope
            )
            accepted_goal = xyz(accepted_envelope.payload.target)
            src.update(
                accepted=outcome.accepted,
                reason=outcome.reason,
                accepted_waypoint=accepted_goal,
                execution_position=xyz(obs.position),
                execution_observation_s=obs.t_sim_ns / 1e9,
                distance_at_execution_m=obs.position.distance_to(envelope.payload.target),
                previous_id=previous["id"] if previous else None,
                goal_shift_m=math.dist(accepted_goal, previous["accepted_waypoint"])
                if previous
                else None,
                verifier_modified=outcome.verification.modified if outcome.verification else False,
                verifier_reason=outcome.verification.reason if outcome.verification else None,
            )
            if 24 <= src["available_s"] <= 50:
                src["planner"] = planner.snapshot(outcome, router, obs)
            if outcome.accepted:
                previous = src
        elif kind == "plan":
            result = outcomes[e["trace_id"]].trajectory
            assert result is not None
            actual = {
                "feasible": result.feasible,
                "points": len(result.points),
                "reason": result.reason,
                "planner_metadata": result.metadata,
            }
            assert actual == {k: p[k] for k in actual}, ("Plan mismatch", e["seq"])
            sources[e["trace_id"]]["plan_metadata"] = result.metadata
            check["plans"] += 1
        elif kind == "control":
            obs = await env.observe()
            record(obs)
            error = math.dist(xyz(obs.position), [p[f"position_{a}"] for a in "xyz"])
            check["max_position_error_m"] = max(error, check["max_position_error_m"])
            assert error < 1e-9 and obs.t_sim_ns == e["t_sim_ns"]
            predicted, _, _ = router.command_for_tick(context(mission, obs))
            values = [*xyz(predicted.velocity), predicted.yaw_rate_rps]
            error = max(
                abs(a - b)
                for a, b in zip(values, [p[k] for k in ("vx", "vy", "vz", "yaw_rate")], strict=True)
            )
            check["max_control_error"] = max(error, check["max_control_error"])
            assert error < 1e-9 and predicted.source_decision_id == e["trace_id"], (
                "Control mismatch",
                obs.seq,
            )
            check["poses"] += 1
            check["controls"] += 1
            controls.append(
                {
                    "t_s": obs.t_sim_ns / 1e9,
                    "position": xyz(obs.position),
                    "yaw_rad": obs.yaw_rad,
                    "source": e["trace_id"],
                    "velocity": xyz(predicted.velocity),
                }
            )
            await env.step(
                command(obs.t_sim_ns, [p[k] for k in ("vx", "vy", "vz")], p["yaw_rate"]), DT_NS
            )
    for src in sources.values():
        indices = [i for i, x in enumerate(controls) if x["source"] == src["id"]]
        used = [controls[i] for i in indices]
        reached_positions = [x["position"] for x in used]
        if indices:
            last_index = indices[-1] + 1
            reached_positions.append(
                controls[last_index]["position"]
                if last_index < len(controls)
                else env.vehicle.position.tolist()
            )
        src["controls_before_replacement"] = len(used)
        src["active_seconds"] = len(used) * 0.05
        src["travel_before_replacement_m"] = sum(
            math.dist(a, b) for a, b in itertools.pairwise(reached_positions)
        )
        src["closest_waypoint_distance_while_active_m"] = min(
            (math.dist(x, src["accepted_waypoint"]) for x in reached_positions), default=None
        )
    data = {
        "source_run": RUN.name,
        "model_calls": 0,
        "validation": check,
        "events_sha256": hashlib.sha256((RUN / "events.jsonl").read_bytes()).hexdigest(),
        "decisions": list(sources.values()),
        "controls": controls,
        "obstacles": [
            {"center": o.center.tolist(), "half": o.half.tolist()} for o in env.obstacles
        ],
    }
    (OUT / "trace.json").write_text(
        json.dumps(data, separators=(",", ":"), allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(check), flush=True)
    for src in sources.values():
        if 24 <= src["available_s"] <= 50:
            print(
                src["available_s"],
                src["source_s"],
                src["pixel"],
                src["owner"]["kind"],
                src["owner"].get("index"),
                "depth",
                src["raw_patch_median_m"],
                "ray",
                src["exact_ray_box_depth_m"],
                "goal",
                src["world_waypoint"],
                "shift",
                src["goal_shift_m"],
                flush=True,
            )
    await env.close()


if __name__ == "__main__":
    asyncio.run(audit())
