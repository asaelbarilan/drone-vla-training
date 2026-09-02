"""Pre-gate diagnostic for SPF's point-plus-distance model interface.

This script deliberately places the camera at known distances on the locked
development seeds. Ground-truth distance is retained only in the diagnostic
report and is never exposed to the model or flight policy.
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

PROMPT = """You are the spatial waypoint policy for a small autonomous drone.

MISSION: {instruction}

Look at the current forward camera image and choose exactly one image point for
the drone's next safe movement. Point directly at the requested goal when it is
visible. Otherwise point at visible free space that best advances the mission.

Return one JSON object and nothing else:
{{"u": <integer 0-1000>, "v": <integer 0-1000>, "distance": <integer 1-10>}}

Coordinates are normalized: (0,0) is top-left, (500,500) is the image center
and (1000,1000) is bottom-right. `distance` is intended forward travel, not
sensor depth. Use this ordered visual scale: 1 only when the requested target is
extremely close (roughly more than 35% of image width); 2 when very close
(roughly 25-35%); 3-5 at medium apparent size; and 6-10 when far/small. A tiny
target should be 9-10. When the target is not visible, choose a safe search
point and use 5. Never reverse this scale.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "u": {"type": "integer", "minimum": 0, "maximum": 1000},
        "v": {"type": "integer", "minimum": 0, "maximum": 1000},
        "distance": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["u", "v", "distance"],
    "additionalProperties": False,
}


async def run(args: argparse.Namespace) -> dict:
    mission = MissionSpec(
        mission_id="spf-model-probe",
        instruction="fly to the red tower and stop there",
        task_family=TaskFamily.LONG_HORIZON_NAV,
    )
    backend = OllamaInference(
        model_id=args.model,
        temperature=0.0,
        num_predict=64,
        sampling_seed=0,
        endpoint="chat",
        think=None if args.omit_think else False,
        response_channel=args.response_channel,
        keep_alive="30m",
        charge_mode="fixed",
        fixed_latency_s={"probe": 0.0},
    )
    args.out.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for seed in args.seeds:
        env = REGISTRY.build(
            "environment",
            "grid3d",
            {
                "render": True,
                "render_depth": False,
                "image_size": 224,
                "n_obstacles": 0,
                "distractors": 3,
                "sensor_range_m": 60.0,
                "goal_distance_m": 35.0,
            },
        )
        await env.reset(mission, seed)
        for distance in args.distances:
            heading = 0.37
            env.vehicle.position = env.goal - distance * np.array(
                [math.cos(heading), math.sin(heading), 0.0]
            )
            env.vehicle.position[2] = env.goal[2]
            env.vehicle.yaw = heading
            obs = await env.observe()
            assert obs.rgb is not None
            image = global_store().get(obs.rgb.uri)
            assert image is not None
            path = args.out / f"seed_{seed}_distance_{distance:g}m.png"
            image.save(path)
            prompt = PROMPT.format(
                instruction=mission.instruction,
                width=image.width,
                height=image.height,
            )
            result = await backend.invoke(
                InferenceRequest(
                    model_id=args.model,
                    role="probe",
                    prompt_hash="spf-probe:v1",
                    input_tokens=len(prompt) // 4,
                    image_count=1,
                    observation_seq=obs.seq,
                    prompt=prompt,
                    images=(backend.encode_image(image),),
                    response_schema=None if args.no_schema else SCHEMA,
                )
            )
            raw = str(result.payload or "")
            diagnostic = None
            if not raw and args.dump_server_payload:
                # Repeat one request through the transport's raw endpoint so a
                # successful response hidden in a provider-specific field is
                # distinguishable from an actual empty model generation.
                diagnostic = backend._post(
                    "/api/chat",
                    {
                        "model": args.model,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                                "images": [backend.encode_image(image)],
                            }
                        ],
                        "stream": False,
                        "keep_alive": "30m",
                        "think": False,
                        "format": SCHEMA,
                        "options": {
                            "temperature": 0.0,
                            "num_predict": 64,
                            "seed": 0,
                        },
                    },
                )
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            row = {
                "seed": seed,
                "camera_distance_m": distance,
                "image": str(path),
                "raw": raw,
                "parsed": parsed,
                "latency_s": result.latency_ns / 1e9,
                "server_payload": diagnostic,
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
        await env.close()

    backend.close()
    valid = [
        row
        for row in rows
        if isinstance(row["parsed"], dict) and set(row["parsed"]) == {"u", "v", "distance"}
    ]
    report = {
        "model": args.model,
        "seeds": args.seeds,
        "distances_m": args.distances,
        "valid_schema": len(valid),
        "total": len(rows),
        "rows": rows,
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3-vl:8b")
    parser.add_argument(
        "--response-channel",
        choices=["content", "thinking", "content_or_thinking"],
        default="thinking",
    )
    parser.add_argument(
        "--omit-think",
        action="store_true",
        help="Do not send Ollama's think option (needed by models without that field).",
    )
    parser.add_argument(
        "--no-schema",
        action="store_true",
        help="Diagnostic only: ask for JSON without provider-side constrained decoding.",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[1040])
    parser.add_argument("--distances", type=float, nargs="+", default=[30, 12, 4, 2])
    parser.add_argument("--dump-server-payload", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("reports/paper_implementation/spf_probe"))
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
