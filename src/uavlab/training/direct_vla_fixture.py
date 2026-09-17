"""Small observable public-coordinate fixture with full source/control recording.

No trained VLA or visual navigation capability is claimed. The teacher needs
only public instruction coordinates and declared onboard odometry. Setup
rotations are recorded but excluded from training. No original data is edited.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import (
    ControlCommand,
    DecisionEnvelope,
    MemorySnapshot,
    MissionDirective,
    MissionSpec,
    PerceptionState,
    ProgressLabel,
    TaskFamily,
    Vec3,
)
from uavlab.core.compose import load_architecture
from uavlab.core.config import EnvironmentConfig
from uavlab.core.decision_router import DecisionRouter
from uavlab.core.frame_store import global_store
from uavlab.interfaces import DecisionContext
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.reasoning.aerovla import make_dual_view_mosaic
from uavlab.training.direct_vla_contract import (
    CONTRACT_ID,
    action_from_target,
    target_from_command,
    target_json,
)
from uavlab.training.qwen_vla_preflight import PILOT_EVALUATION_SEEDS
from uavlab.training.splits import check_collection_range

DT_NS = 50_000_000
HORIZON_S = 0.2
MAX_TICKS = 800
STOP_RADIUS_M = 0.35
STOP_SPEED_MPS = 0.1
KINDS = "public-coordinate teacher fixture; no trained model; no visual competency claim"


def instruction_for(goal: tuple[float, float, float]) -> str:
    return (
        "Fly to public ENU coordinate "
        + json.dumps(list(goal))
        + " metres. Stop within 0.35 metres only when speed is at most 0.1 m/s."
    )


def goal_from_instruction(instruction: str) -> tuple[float, float, float]:
    start, end = instruction.index("["), instruction.index("]") + 1
    goal = json.loads(instruction[start:end])
    if len(goal) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in goal):
        raise ValueError("invalid public goal")
    return tuple(float(x) for x in goal)


def student_state(obs) -> dict:
    return {
        "position_enu_m": list(obs.position.as_tuple()),
        "velocity_enu_mps": list(obs.velocity.as_tuple()),
        "yaw_enu_rad": obs.yaw_rad,
    }


def public_teacher(instruction: str, state: dict, t_ns: int):
    goal = np.array(goal_from_instruction(instruction))
    error = goal - np.array(state["position_enu_m"])
    distance = float(np.linalg.norm(error))
    speed = float(np.linalg.norm(state["velocity_enu_mps"]))
    terminal = distance <= STOP_RADIUS_M and speed <= STOP_SPEED_MPS
    velocity = np.zeros(3) if distance <= STOP_RADIUS_M else 0.8 * error
    norm = float(np.linalg.norm(velocity))
    if norm > 1.5:
        velocity *= 1.5 / norm
    yaw_error = math.atan2(
        math.sin(math.atan2(error[1], error[0]) - state["yaw_enu_rad"]),
        math.cos(math.atan2(error[1], error[0]) - state["yaw_enu_rad"]),
    )
    yaw_rate = max(-1.5, min(1.5, yaw_error * 1.5)) if distance > STOP_RADIUS_M else 0.0
    command = ControlCommand(
        t_sim_ns=t_ns,
        velocity=Vec3(x=velocity[0], y=velocity[1], z=velocity[2]),
        yaw_rate_rps=yaw_rate,
        expires_t_sim_ns=t_ns + int(HORIZON_S * 1e9),
    )
    return command, terminal, {"public_goal_error_m": distance, "speed_mps": speed}


def student_prompt(instruction: str, state: dict) -> str:
    return (
        "Direct drone control. Image: front RGB above downward RGB. "
        "Use only the instruction, image and supplied odometry. "
        + instruction
        + "\nOdometry: "
        + json.dumps(state, separators=(",", ":"))
        + "\nReturn JSON keys vx_body_bin,vy_body_bin,vz_body_bin,yaw_rate_bin,stop. "
        "Velocity axes are forward/left/up in the level frame defined by this observation yaw. "
        "Bins 0..64 map to -5..5 m/s on each velocity axis and -1.5..1.5 rad/s yaw "
        "(positive counterclockwise). Bin32 is exactly zero. "
        "The decoded ENU setpoint lasts 0.2 seconds. "
        "Nonterminal hold is all32 with stop=false. "
        "Mission termination is all32 with stop=true; it is not physical landing."
    )


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def context(mission, obs, name):
    return DecisionContext(
        mission=mission,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=0,
        episode_id=name,
    )


async def record(
    root: Path,
    seed: int,
    setup_ticks: int,
    setup_yaw_rate: float,
    goal_distance_m: float = 8.0,
):
    check_collection_range(seed, 1)
    if seed in PILOT_EVALUATION_SEEDS:
        raise ValueError("pilot evaluation seed may not enter collection")
    params = {
        "scene": "empty",
        "goal_distance_m": goal_distance_m,
        "n_obstacles": 0,
        "distractors": 3,
        "render": True,
        "render_down": True,
        "render_depth": False,
        "image_size": 224,
        "allow_privileged": False,
        "coarse_goal_direction": False,
        "max_speed_mps": 5.0,
        "wind_mps": 0.0,
        "success": {"goal_radius_m": STOP_RADIUS_M, "require_terminal_stop": True},
    }
    env = DeterministicEnv(**params)
    provisional = MissionSpec(
        mission_id="public-goal-generation",
        instruction="instantiate a public goal",
        task_family=TaskFamily.KNOWN_GOAL_NAV,
    )
    await env.reset(provisional, seed)
    instruction = instruction_for(tuple(float(x) for x in env.goal))
    config = EnvironmentConfig(
        id="direct_vla_public_goal_fixture",
        task_family=TaskFamily.KNOWN_GOAL_NAV,
        instruction=instruction,
        max_episode_s=MAX_TICKS * DT_NS / 1e9,
        params=params,
    )
    mission = MissionSpec(
        mission_id=f"vla-public-goal-{seed}",
        instruction=instruction,
        task_family=TaskFamily.KNOWN_GOAL_NAV,
        success=params["success"],
    )
    await env.reset(mission, seed)
    name = f"public_goal_s{seed}"
    folder = root / "runs" / name
    folder.mkdir(parents=True, exist_ok=False)
    image_dir = folder / "images"
    image_dir.mkdir()
    arch = load_architecture("c7").model_copy(
        update={
            "id": "direct_vla_public_teacher_fixture",
            "name": KINDS,
        }
    )
    controller = MockVelocityController()
    controller.reset(mission, seed)
    router = DecisionRouter(arch, verifier=None, planner=None, shield=None, controller=controller)
    router.reset(mission, seed)
    events, samples = [], []
    last_decision = None
    terminal = False
    failure = None

    def emit(kind, obs, payload, trace=None):
        events.append(
            {
                "episode_id": name,
                "event_type": kind,
                "seq": len(events),
                "t_sim_ns": obs.t_sim_ns,
                "t_wall_ns": 0,
                "component": "public_teacher_fixture",
                "payload": payload,
                "trace_id": trace,
            }
        )

    for tick in range(MAX_TICKS):
        obs = await env.observe()
        ctx = context(mission, obs, name)
        if tick < setup_ticks:
            command = ControlCommand(
                t_sim_ns=obs.t_sim_ns,
                velocity=Vec3(x=0, y=0, z=0),
                yaw_rate_rps=setup_yaw_rate,
            )
        else:
            if (tick - setup_ticks) % 4 == 0:
                state = student_state(obs)
                teacher, terminal, evidence = public_teacher(instruction, state, obs.t_sim_ns)
                target = target_from_command(teacher, obs.yaw_rad, terminal=terminal)
                action = action_from_target(target, obs.yaw_rad, duration_s=HORIZON_S)
                if action is None:
                    action = MissionDirective(
                        label=ProgressLabel.STOP,
                        rationale="public goal and observed speed gate",
                    )
                identity = f"{name}-decision-{len(samples):04d}"
                prompt = student_prompt(instruction, state)
                paths = {}
                hashes = {}
                for camera, ref in (("front", obs.rgb), ("down", obs.rgb_down)):
                    if ref is None:
                        raise ValueError("required source camera missing")
                    img = global_store().get(ref.uri)
                    if img is None:
                        raise ValueError("source frame missing")
                    file = image_dir / f"{tick:05d}_{camera}.png"
                    img.save(file, format="PNG")
                    paths[camera] = file.relative_to(root).as_posix()
                    hashes[camera] = hashlib.sha256(file.read_bytes()).hexdigest()
                mosaic = make_dual_view_mosaic(
                    global_store().get(obs.rgb.uri),
                    global_store().get(obs.rgb_down.uri),
                    224,
                )
                file = image_dir / f"{tick:05d}_mosaic.png"
                mosaic.save(file, format="PNG")
                paths["mosaic"] = file.relative_to(root).as_posix()
                hashes["mosaic"] = hashlib.sha256(file.read_bytes()).hexdigest()
                proposal = DecisionEnvelope(
                    decision_id=identity,
                    kind=action.kind,
                    payload=action,
                    source_observation_seq=obs.seq,
                    source_t_sim_ns=obs.t_sim_ns,
                    produced_t_wall_ns=0,
                    produced_t_sim_ns=obs.t_sim_ns,
                    producer="public_coordinate_teacher_not_model",
                    provenance={
                        "contract": CONTRACT_ID,
                        "target": target_json(target),
                        "source_yaw": repr(obs.yaw_rad),
                        "rgb_digest": obs.rgb.digest,
                    },
                )
                emit("decision_proposed", obs, proposal.model_dump(mode="json"), identity)
                outcome = router.accept(proposal, ctx)
                if not outcome.accepted:
                    raise ValueError(f"teacher proposal rejected: {outcome.reason}")
                emit("decision_executed", obs, {"accepted": True}, identity)
                sample = {
                    "seed": seed,
                    "split": "val" if seed % 5 == 0 else "train",
                    "tick": tick,
                    "t_sim_ns": obs.t_sim_ns,
                    "observation_seq": obs.seq,
                    "instruction": instruction,
                    "state": state,
                    "prompt": prompt,
                    "images": paths,
                    "image_sha256": hashes,
                    "target": json.loads(target_json(target)),
                    "teacher_command": teacher.model_dump(mode="json"),
                    "decoded_action": action.model_dump(mode="json"),
                    "terminal_evidence": evidence,
                    "decision_id": identity,
                    "intrinsics": obs.intrinsics.model_dump(mode="json"),
                }
                samples.append(sample)
                last_decision = identity
            command = controller.hold(ctx) if terminal else router.command_for_tick(ctx)[0]
        payload = {
            "position_x": obs.position.x,
            "position_y": obs.position.y,
            "position_z": obs.position.z,
            "observed_velocity": list(obs.velocity.as_tuple()),
            "yaw_rad": obs.yaw_rad,
            "observation_seq": obs.seq,
            "vx": command.velocity.x,
            "vy": command.velocity.y,
            "vz": command.velocity.z,
            "yaw_rate": command.yaw_rate_rps,
            "command": command.model_dump(mode="json"),
            "setup_only": tick < setup_ticks,
        }
        emit("control", obs, payload, last_decision)
        await env.step(command, DT_NS)
        if env.status().collided or env.status().out_of_bounds:
            failure = "collision_or_out_of_bounds"
            break
        if terminal:
            break
    status = env.status()
    success = terminal and failure is None
    result = {
        "success": success,
        "termination_reason": "agent_stopped" if success else failure or "timeout",
        "sim_duration_s": env._t_ns / 1e9,
        "used_privileged_observations": False,
        "validation_kind": KINDS,
        "metrics": {
            "distance_to_goal_m": status.distance_to_goal_m,
            "collisions": float(status.collision_count),
        },
        "status": status.model_dump(mode="json"),
    }
    manifest = {
        "architecture_config": arch.model_dump(mode="json"),
        "environment_config": config.model_dump(mode="json"),
        "seeds": [seed],
        "validation_kind": KINDS,
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "git_dirty": True,
        "contract": CONTRACT_ID,
        "setup_ticks": setup_ticks,
        "setup_yaw_rate_rps": setup_yaw_rate,
        "teacher_uses": ["instruction", "odometry"],
        "model_calls": 0,
    }
    write_json(folder / "manifest.json", manifest)
    write_json(folder / "result.json", result)
    (folder / "events.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events),
        encoding="utf-8",
    )
    await env.close()
    print(
        f"{name}: samples={len(samples)} success={success} t={result['sim_duration_s']:.2f}s",
        flush=True,
    )
    return folder, samples, result


async def collect(root: Path):
    if root.exists():
        raise FileExistsError(f"refusing to overwrite {root}")
    root.mkdir(parents=True)
    settings = [
        (0, 0.0),
        (20, 1.5),
        (20, -1.5),
        (40, 1.5),
        (10, 0.75),
        (10, -0.75),
        (30, -1.5),
        (0, 0.0),
    ]
    index, results = [], []
    for offset, (ticks, rate) in enumerate(settings):
        folder, samples, result = await record(root, 1400 + offset, ticks, rate)
        index.extend(samples)
        results.append({"run": folder.relative_to(root).as_posix(), **result})
    (root / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in index),
        encoding="utf-8",
    )
    for split in ("train", "val"):
        rows = [
            {
                "images": [r["images"]["mosaic"]],
                "messages": [
                    {"role": "user", "content": "<image>\n" + r["prompt"]},
                    {
                        "role": "assistant",
                        "content": json.dumps(r["target"], separators=(",", ":")),
                    },
                ],
            }
            for r in index
            if r["split"] == split
        ]
        (root / f"{split}_swift.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows),
            encoding="utf-8",
        )
    manifest = {
        "format": "direct_velocity_public_goal_fixture_v1",
        "contract": CONTRACT_ID,
        "swift_image_root": "dataset",
        "seeds": list(range(1400, 1408)),
        "split_rule": "validation iff seed%5==0",
        "samples": len(index),
        "samples_by_split": {s: sum(r["split"] == s for r in index) for s in ("train", "val")},
        "episodes": results,
        "training_ready": False,
        "purpose": KINDS,
        "teacher_inputs": ["instruction", "odometry"],
        "student_inputs": ["front_rgb", "down_rgb", "instruction", "odometry"],
        "excluded_from_training": ["setup rotations", "debug/truth metadata"],
        "action_horizon_s": HORIZON_S,
        "control_dt_ns": DT_NS,
        "pending": [
            "full source/control audit",
            "trained-backbone overfit",
            "visual task coverage",
        ],
    }
    write_json(root / "manifest.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(collect(args.out.resolve()))
    print(json.dumps({"samples": result["samples"], "split": result["samples_by_split"]}, indent=2))
