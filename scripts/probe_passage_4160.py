"""D-95: two bounded manual crossing attempts from a user-selected saved state.

Privileged physical diagnostic only. Does not instantiate any policy, planner
or inference backend. Does not modify the historical run or simulator dynamics.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.analysis.flight_debugger import read_events, read_json
from uavlab.contracts import (
    ControlCommand,
    MissionConstraints,
    MissionSpec,
    SuccessCriteria,
    Vec3,
)
from uavlab.core.frame_store import global_store

SOURCE_TIME_NS = 41_600_000_000
SOURCE_SEQ = 833
DT_NS = 50_000_000
MAX_SECONDS = 24.0
OPENING_U = 128.0  # Visually selected center of the opening in the 224 px source image.


def command(t, velocity, yaw_rate=0.0):
    return ControlCommand(
        t_sim_ns=t,
        velocity=Vec3(x=float(velocity[0]), y=float(velocity[1]), z=float(velocity[2])),
        yaw_rate_rps=yaw_rate,
    )


async def restore(run):
    manifest = read_json(run / "manifest.json")
    config = manifest["environment_config"]
    params = dict(config["params"])
    params.update(config["adapter"]["params"])
    params["allow_privileged"] = False
    mission = MissionSpec(
        mission_id="manual_passage_probe",
        instruction=config["instruction"],
        task_family=config["task_family"],
        constraints=MissionConstraints.model_validate(params.get("constraints", {})),
        success=SuccessCriteria.model_validate(params.get("success", {})),
    )
    env = DeterministicEnv(**params)
    await env.reset(mission, manifest["seeds"][0])
    max_error = 0.0
    for event in read_events(run / "events.jsonl"):
        if event["event_type"] != "control":
            continue
        obs = await env.observe()
        payload = event["payload"]
        actual = np.array([obs.position.x, obs.position.y, obs.position.z])
        logged = np.array([payload[f"position_{axis}"] for axis in "xyz"])
        max_error = max(max_error, float(np.linalg.norm(actual - logged)))
        if obs.t_sim_ns != event["t_sim_ns"] or max_error > 1e-9:
            raise ValueError("Saved state restoration did not match the control log")
        if event["t_sim_ns"] == SOURCE_TIME_NS:
            if obs.seq != SOURCE_SEQ or env.status().collided:
                raise ValueError("Unexpected source observation or prior collision")
            return env, obs, manifest, max_error
        await env.step(
            command(
                event["t_sim_ns"],
                [payload["vx"], payload["vy"], payload["vz"]],
                payload["yaw_rate"],
            ),
            DT_NS,
        )
    raise ValueError("Source time was not present")


def frame_data(env, obs, rgb, target_velocity, clearance):
    return {
        "t": obs.t_sim_ns / 1e9,
        "elapsed": (obs.t_sim_ns - SOURCE_TIME_NS) / 1e9,
        "observation_seq": obs.seq,
        "position": [obs.position.x, obs.position.y, obs.position.z],
        "velocity": [obs.velocity.x, obs.velocity.y, obs.velocity.z],
        "yaw_rad": obs.yaw_rad,
        "command_mps": target_velocity.tolist(),
        "surface_clearance_m": clearance,
        "collided": env.status().collided,
        "rgb": rgb.copy(),
    }


def movie(path, samples, obstacles, summary):
    """Render real probe camera frames next to a close-up physical trajectory."""
    size = (1160, 710)
    ffmpeg = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "bgr24",
        "-video_size",
        f"{size[0]}x{size[1]}",
        "-framerate",
        "10",
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    process = subprocess.Popen(ffmpeg, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        chosen = list(range(0, len(samples), 2))
        if chosen[-1] != len(samples) - 1:
            chosen.append(len(samples) - 1)
        chosen = [0] * 10 + chosen + [len(samples) - 1] * 20
        for idx in chosen:
            s = samples[idx]
            canvas = np.full((size[1], size[0], 3), (26, 18, 12), np.uint8)
            # Fixed close-up scale shows the body and the disputed passage.
            def project(p):
                return int(290 + (p[0] - 18.5) * 30), int(375 - (p[1] - 16) * 30)
            for o in obstacles:
                lo = np.array(o["center"]) - np.array(o["half"])
                hi = np.array(o["center"]) + np.array(o["half"])
                if not lo[2] <= s["position"][2] <= hi[2]:
                    continue
                a, b = project(lo), project(hi)
                a = (max(15, min(a[0], 565)), max(100, min(a[1], 650)))
                b = (max(15, min(b[0], 565)), max(100, min(b[1], 650)))
                cv2.rectangle(canvas, a, b, (92, 84, 78), -1)
                cv2.rectangle(canvas, a, b, (151, 133, 119), 1)
            trail = np.array([project(x["position"]) for x in samples[: idx + 1]], np.int32)
            if len(trail) > 1:
                cv2.polylines(canvas, [trail], False, (218, 210, 89), 2, cv2.LINE_AA)
            p = project(s["position"])
            cv2.circle(canvas, p, round(summary["planner_clearance_m"] * 30), (113, 90, 72), 1)
            cv2.circle(
                canvas,
                p,
                round(summary["drone_radius_m"] * 30),
                (93, 92, 238) if s["collided"] else (108, 221, 241),
                -1,
            )
            end = project(np.array(s["position"]) + np.array(s["command_mps"]) * 3)
            cv2.arrowedLine(canvas, p, end, (137, 226, 147), 2, tipLength=0.2)
            camera = cv2.cvtColor(np.asarray(s["rgb"]), cv2.COLOR_RGB2BGR)
            canvas[105:645, 600:1140] = cv2.resize(
                camera, (540, 540), interpolation=cv2.INTER_NEAREST
            )
            minimum_clearance = min(x["surface_clearance_m"] for x in samples[: idx + 1])
            final = idx == len(samples) - 1
            state = summary["outcome"] if final else "MOVING"
            for text, origin, scale, colour in [
                (summary["title"], (20, 30), 0.7, (237, 232, 224)),
                (
                    "MANUAL PHYSICAL TEST - no VLM / no local planner",
                    (20, 59),
                    0.5,
                    (183, 167, 149),
                ),
                (
                    f"source 41.60 s | elapsed {s['elapsed']:.2f} s | {state}",
                    (20, 87),
                    0.53,
                    (116, 214, 249),
                ),
                (
                    "Close-up map | filled circle = actual drone body",
                    (20, 674),
                    0.45,
                    (206, 194, 176),
                ),
                ("Outer ring = planner's 1.8 m clearance", (20, 698), 0.45, (158, 147, 135)),
                (
                    f"Surface clearance {s['surface_clearance_m']:.3f} m | body radius 0.400 m",
                    (602, 674),
                    0.43,
                    (206, 194, 176),
                ),
                (
                    f"Minimum so far {minimum_clearance:.3f} m",
                    (602, 698),
                    0.45,
                    (206, 194, 176),
                ),
            ]:
                cv2.putText(
                    canvas, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale, colour, 1, cv2.LINE_AA
                )
            if idx == 0:
                cv2.imwrite(str(path.with_name(path.stem + "_start.png")), canvas)
            if final:
                cv2.imwrite(str(path.with_name(path.stem + "_end.png")), canvas)
            process.stdin.write(canvas.tobytes())
    finally:
        process.stdin.close()
    errors = process.stderr.read().decode()
    if process.wait() != 0:
        raise RuntimeError(errors)


async def attempt(run, out, mode):
    env, obs, manifest, restore_error = await restore(run)
    initial = np.array([obs.position.x, obs.position.y, obs.position.z])
    initial_yaw = obs.yaw_rad
    if mode == "heading":
        bearing = initial_yaw
        title = "A - Straight ahead at the restored heading"
    else:
        camera = env._camera
        v_level = camera.height / 2 - camera.focal_px * math.tan(-camera.pitch_rad)
        ray = camera.ray_world(OPENING_U, v_level, initial_yaw)
        bearing = math.atan2(ray[1], ray[0])
        title = "B - Aimed at the visible opening center (u=128)"
    target_v = 0.6 * np.array([math.cos(bearing), math.sin(bearing), 0.0])
    obstacles = [{"center": o.center.tolist(), "half": o.half.tolist()} for o in env.obstacles]
    # Rear face of the left obstacle, plus the physical body radius. Truth is
    # used only to label a completed crossing, never to steer the manual command.
    exit_y = float(env.obstacles[2].center[1] + env.obstacles[2].half[1] + env.drone_radius_m)
    planner_params = manifest["architecture_config"]["planner"]["params"]
    planner_clearance = (
        manifest["environment_config"]["params"]["constraints"]["min_obstacle_clearance_m"]
        + planner_params["clearance_margin_m"]
    )
    summary = {
        "title": title,
        "mode": mode,
        "privileged_diagnostic": True,
        "source_run": run.name,
        "source_t_s": 41.6,
        "source_observation_seq": obs.seq,
        "restoration_max_position_error_m": restore_error,
        "initial_position": initial.tolist(),
        "initial_velocity": [obs.velocity.x, obs.velocity.y, obs.velocity.z],
        "initial_yaw_deg": math.degrees(initial_yaw),
        "command_bearing_deg": math.degrees(bearing),
        "command_mps": target_v.tolist(),
        "drone_radius_m": env.drone_radius_m,
        "planner_clearance_m": planner_clearance,
        "exit_y_m": exit_y,
        "max_seconds": MAX_SECONDS,
        "model_calls": 0,
        "outcome": "DURATION_LIMIT",
    }
    samples = []
    try:
        for _ in range(round(MAX_SECONDS / 0.05) + 1):
            clearance = min(o.distance(env.vehicle.position) for o in env.obstacles)
            image = global_store().get(obs.rgb.uri)
            samples.append(frame_data(env, obs, image, target_v, clearance))
            if env.status().collided:
                summary["outcome"] = "COLLISION - STOPPED AT FIRST CONTACT"
                break
            if obs.position.y >= exit_y:
                summary["outcome"] = "CLEARED BOTH OBSTACLES WITHOUT COLLISION"
                break
            if obs.t_sim_ns - SOURCE_TIME_NS >= int(MAX_SECONDS * 1e9):
                break
            yaw_error = math.atan2(math.sin(bearing - obs.yaw_rad), math.cos(bearing - obs.yaw_rad))
            yaw_rate = max(-0.4, min(0.4, 1.5 * yaw_error))
            await env.step(command(obs.t_sim_ns, target_v, yaw_rate), DT_NS)
            obs = await env.observe()
    finally:
        await env.close()
    summary.update(
        elapsed_s=samples[-1]["elapsed"],
        final_position=samples[-1]["position"],
        min_surface_clearance_m=min(x["surface_clearance_m"] for x in samples),
        collided=samples[-1]["collided"],
        net_displacement_m=float(np.linalg.norm(np.array(samples[-1]["position"]) - initial)),
    )
    image = samples[0]["rgb"]
    image.save(out / "source_4160.png")
    (out / f"{mode}.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "obstacles": obstacles,
                "samples": [{k: v for k, v in x.items() if k != "rgb"} for x in samples],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2), flush=True)
    movie(out / f"{mode}.mp4", samples, obstacles, summary)
    return summary


async def main_async(args):
    args.out.mkdir(parents=True, exist_ok=True)
    summaries = []
    for mode in ("heading", "opening"):
        summaries.append(await attempt(args.run, args.out, mode))
    (args.out / "summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, default=Path("runs/c5_guarded_monitor_20260911_s1061"))
    p.add_argument("--out", type=Path, default=Path("reports/passage_probe_20260912"))
    asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    main()
