"""Observable RGB/instruction yaw pairs; synthetic teacher, not learned autonomy.

Color segmentation is used only to build/audit visible-target labels. It is
never a policy component, hidden-target search routine or inference fallback.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from uavlab.adapters.gym.deterministic_env import DeterministicEnv, Landmark
from uavlab.contracts import ControlCommand, MissionSpec, TaskFamily, Vec3
from uavlab.core.frame_store import global_store
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.reasoning.aerovla import make_dual_view_mosaic
from uavlab.training.direct_vla_fixture import DT_NS, context, student_state, write_json
from uavlab.training.direct_vla_frd import (
    CONTRACT_ID,
    action_from_target,
    student_prompt,
    target_from_command,
    target_json,
)

COLORS = {"red": (220, 35, 35), "blue": (35, 45, 220)}


def visible_bearing(mosaic, colour, cx, fx):
    pixels = np.asarray(mosaic.crop((0, 0, 224, 112))).astype(float)
    r, g, b = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    if colour == "red":
        mask = (r > 1.8 * g) & (r > 1.8 * b) & (r > 100)
    elif colour == "blue":
        mask = (b > 1.8 * r) & (b > 1.8 * g) & (b > 100)
    else:
        raise ValueError("unknown instruction colour")
    _, xs = np.where(mask)
    if len(xs) < 12 or xs.min() < 5 or xs.max() > 218:
        raise ValueError("target missing, too small or clipped; no privileged fallback")
    return math.atan2(float(xs.mean()) - cx, fx), {
        "visible_pixels": len(xs),
        "centroid_u": float(xs.mean()),
    }


def teacher(mosaic, instruction, intrinsics, t_ns, yaw):
    colour = next((c for c in COLORS if f"the {c} pillar" in instruction), None)
    if colour is None:
        raise ValueError("unsupported visual instruction")
    bearing, evidence = visible_bearing(mosaic, colour, intrinsics.cx, intrinsics.fx)
    cw = max(-1.5, min(1.5, 1.5 * bearing))
    command = ControlCommand(
        t_sim_ns=t_ns,
        velocity=Vec3(x=0, y=0, z=0),
        yaw_rate_rps=-cw,
        expires_t_sim_ns=t_ns + 200_000_000,
    )
    target = target_from_command(command, yaw)
    return target, {
        **evidence,
        "colour": colour,
        "bearing_cw_rad": bearing,
        "teacher_inputs": "exact mosaic pixels + instruction + horizontal camera calibration",
    }


async def collect(root):
    root.mkdir(parents=True, exist_ok=False)
    rows = []
    segment_checks = 0
    for seed in range(1410, 1418):
        rng = np.random.default_rng(seed)
        heading = float(rng.uniform(-math.pi, math.pi))
        geometries = [
            (
                float(rng.uniform(12, 15)),
                float(rng.uniform(0.2, 0.45)),
                float(rng.uniform(0.2, 0.45)),
            )
            for _ in range(2)
        ]
        for layout in range(4):
            distance, left, right = geometries[layout // 2]
            for requested in COLORS:
                instruction = (
                    f"Turn in place to center the {requested} pillar in the front camera. "
                    "Do not translate; keep the mission active."
                )
                mission = MissionSpec(
                    mission_id=f"visible-yaw-{seed}-{layout}-{requested}",
                    instruction=instruction,
                    task_family=TaskFamily.SEMANTIC_GOAL_NAV,
                )
                env = DeterministicEnv(
                    scene="empty",
                    n_obstacles=0,
                    distractors=0,
                    render=True,
                    render_down=True,
                    render_depth=False,
                    image_size=224,
                    allow_privileged=False,
                    coarse_goal_direction=False,
                )
                await env.reset(mission, seed)
                env.vehicle.yaw = heading
                start = env.vehicle.position.copy()
                forward = np.array([math.cos(heading), math.sin(heading), 0])
                right_axis = np.array([math.sin(heading), -math.cos(heading), 0])
                labels = ["red", "blue"] if layout % 2 == 0 else ["blue", "red"]
                env.landmarks = [
                    Landmark(
                        position=start
                        + forward * distance
                        + right_axis * (math.tan(angle) * distance),
                        label=f"visible_pillar_{i}",
                        color=COLORS[c],
                    )
                    for i, (c, angle) in enumerate(zip(labels, [-left, right], strict=True))
                ]
                env._last_hits = ()
                obs = await env.observe()
                mosaic = make_dual_view_mosaic(
                    global_store().get(obs.rgb.uri), global_store().get(obs.rgb_down.uri), 224
                )
                target, evidence = teacher(
                    mosaic, instruction, obs.intrinsics, obs.t_sim_ns, obs.yaw_rad
                )
                assert target.yaw_cw_bin != 32
                action = action_from_target(target, obs.yaw_rad, duration_s=0.2)
                folder = root / f"s{seed}" / f"layout{layout}" / requested
                folder.mkdir(parents=True)
                paths = {}
                hashes = {}
                for name, img in [
                    ("front", global_store().get(obs.rgb.uri)),
                    ("down", global_store().get(obs.rgb_down.uri)),
                    ("mosaic", mosaic),
                ]:
                    path = folder / f"{name}.png"
                    img.save(path)
                    paths[name] = path.relative_to(root).as_posix()
                    hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
                controller = MockVelocityController()
                controller.reset(mission, seed)
                trace = []
                for tick in range(4):
                    current = obs if tick == 0 else await env.observe()
                    command = controller.from_action(
                        action, context(mission, current, mission.mission_id), mission.mission_id
                    )
                    trace.append(
                        {
                            "state": student_state(current),
                            "t_sim_ns": current.t_sim_ns,
                            "command": command.model_dump(mode="json"),
                        }
                    )
                    await env.step(command, DT_NS)
                after = await env.observe()
                after_mosaic = make_dual_view_mosaic(
                    global_store().get(after.rgb.uri), global_store().get(after.rgb_down.uri), 224
                )
                after_bearing, _ = visible_bearing(
                    after_mosaic, requested, after.intrinsics.cx, after.intrinsics.fx
                )
                assert abs(after_bearing) < abs(evidence["bearing_cw_rad"]), (
                    "decoded control must reduce observed target error"
                )
                assert np.allclose(after.position.as_tuple(), obs.position.as_tuple()), (
                    "yaw-only task must not translate"
                )
                after_mosaic.save(folder / "after.png")
                row = {
                    "seed": seed,
                    "split": "val" if seed % 5 == 0 else "train",
                    "layout": layout,
                    "instruction_colour": requested,
                    "contract": CONTRACT_ID,
                    "task": "visible_target_yaw_alignment_diagnostic",
                    "instruction": instruction,
                    "state": student_state(obs),
                    "prompt": student_prompt(instruction, student_state(obs)),
                    "images": paths,
                    "image_sha256": hashes,
                    "target": json.loads(target_json(target)),
                    "intrinsics": obs.intrinsics.model_dump(mode="json"),
                    "teacher_evidence_audit_only": evidence,
                    "controls": trace,
                    "after_state": student_state(after),
                    "after_bearing_cw_rad": after_bearing,
                    "after_image": (folder / "after.png").relative_to(root).as_posix(),
                    "scene_audit_only": [
                        {"position": m.position.tolist(), "colour": list(m.color), "label": m.label}
                        for m in env.landmarks
                    ],
                }
                rows.append(row)
                segment_checks += 1
                await env.close()
    paired = 0
    for seed in range(1410, 1418):
        for layout in range(4):
            red, blue = [
                next(
                    r
                    for r in rows
                    if r["seed"] == seed and r["layout"] == layout and r["instruction_colour"] == c
                )
                for c in COLORS
            ]
            assert red["image_sha256"]["mosaic"] == blue["image_sha256"]["mosaic"]
            assert (red["target"]["yaw_cw_bin"] - 32) * (blue["target"]["yaw_cw_bin"] - 32) < 0
            swapped = next(
                r
                for r in rows
                if r["seed"] == seed
                and r["layout"] == (layout ^ 1)
                and r["instruction_colour"] == "red"
            )
            assert (red["target"]["yaw_cw_bin"] - 32) * (swapped["target"]["yaw_cw_bin"] - 32) < 0
            paired += 1
    by_hash = {}
    for r in rows:
        by_hash.setdefault(r["image_sha256"]["mosaic"], set()).add(r["split"])
    assert not any(len(s) > 1 for s in by_hash.values())
    (root / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    summary = {
        "contract": CONTRACT_ID,
        "samples": len(rows),
        "train": sum(r["split"] == "train" for r in rows),
        "val": sum(r["split"] == "val" for r in rows),
        "scene_groups": 8,
        "unique_source_mosaics": len(by_hash),
        "same_image_opposite_instruction_checks": paired,
        "same_instruction_color_swap_checks": paired,
        "executed_yaw_segments": segment_checks,
        "recorded_controls": 4 * segment_checks,
        "visual_error_decreased_segments": segment_checks,
        "cross_split_image_duplicates": 0,
        "trained_on": False,
        "teacher": "explicit visible-pixel synthetic color teacher; never used as model fallback",
        "limits": [
            "flat-shaded local simulator only",
            "yaw primitive only, not navigation/search competency",
            "no real/external-simulator training data admitted",
        ],
    }
    write_json(root / "manifest.json", summary)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(collect(args.out))
