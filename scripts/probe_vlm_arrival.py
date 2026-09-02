"""Probe Gemma's target-scale judgement on controlled rendered frames.

This is a diagnostic, not an architecture result: the script deliberately
places the camera at known distances so model outputs can be compared with
ground truth.  No such distance is exposed to the flight policy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path

import numpy as np

from uavlab.contracts import MissionSpec, TaskFamily
from uavlab.core.frame_store import global_store
from uavlab.core.registry import REGISTRY
from uavlab.interfaces import InferenceRequest
from uavlab.plugins.inference.ollama import OllamaInference
from uavlab.plugins.reasoning.vlm import PROMPT


SCALE_PROMPT = """You are the vision system of a small autonomous drone.

The target is the RED tower. Grey shapes are obstacles. Green shapes are not the target.
The image is {width} by {height} pixels.

Answer with ONE line of JSON and nothing else:
{{"found": <true|false>, "u": <base x pixel>, "v": <base y pixel>,
  "height_px": <visible red-tower height in pixels>}}

Measure height_px from the topmost visible red pixel to the bottommost visible red pixel.
Use zeros for u, v and height_px when no red tower is visible.
JSON:"""


async def run(args: argparse.Namespace) -> dict:
    mission = MissionSpec(
        mission_id="arrival-probe",
        instruction="fly to the target tower and stop there",
        task_family=TaskFamily.LONG_HORIZON_NAV,
    )
    env = REGISTRY.build(
        "environment",
        "grid3d",
        {
            "render": True,
            "n_obstacles": 0,
            "n_distractors": 3,
            "sensor_range_m": 60.0,
            "goal_distance_m": 35.0,
        },
    )
    await env.reset(mission, args.seed)
    backend = OllamaInference(
        model_id=args.model,
        temperature=0.0,
        num_predict=args.num_predict,
        endpoint="chat",
        keep_alive="30m",
        charge_mode="fixed",
        fixed_latency_s={"probe": 0.0},
    )

    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for distance in args.distances:
        # Put the camera on a horizontal ray from the target and face it.  The
        # model sees only the resulting pixels; distance is retained here solely
        # as the diagnostic label.
        heading = 0.37
        env.vehicle.position = env.goal - distance * np.array(
            [math.cos(heading), math.sin(heading), 0.0]
        )
        env.vehicle.position[2] = env.goal[2]
        env.vehicle.yaw = heading
        obs = await env.observe()
        image = global_store().get(obs.rgb.uri)
        image_path = args.out / f"distance_{distance:g}m.png"
        image.save(image_path)
        encoded = backend.encode_image(image)

        prompts = {
            "current": PROMPT.format(
                instruction=mission.instruction,
                width=image.width,
                height=image.height,
                umax=image.width - 1,
                vmax=image.height - 1,
            ),
            "scale": SCALE_PROMPT.format(width=image.width, height=image.height),
        }
        replies = {}
        for name, prompt in prompts.items():
            result = await backend.invoke(
                InferenceRequest(
                    model_id=args.model,
                    role="probe",
                    prompt_hash=f"arrival-probe:{name}",
                    input_tokens=len(prompt) // 4,
                    image_count=1,
                    observation_seq=obs.seq,
                    prompt=prompt,
                    images=(encoded,),
                )
            )
            replies[name] = str(result.payload)
        rows.append(
            {
                "distance_m": distance,
                "image": str(image_path),
                "current_reply": replies["current"],
                "scale_reply": replies["scale"],
            }
        )
        print(json.dumps(rows[-1]), flush=True)

    backend.close()
    report = {"model": args.model, "seed": args.seed, "probes": rows}
    (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemma3:4b")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--num-predict", type=int, default=64)
    parser.add_argument("--distances", type=float, nargs="+", default=[2, 3, 4, 6, 8, 12])
    parser.add_argument("--out", type=Path, default=Path("reports/vlm_arrival_probe"))
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
