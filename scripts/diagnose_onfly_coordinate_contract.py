"""Replay logged OnFly views and test the VLM coordinate convention.

This is a diagnostic only: it does not change an architecture or execute a new
flight.  Logged control commands reconstruct the exact camera frames from an
existing deterministic-grid run, then the selected local VLM is asked for a
0--100 normalized image point.  Ground-truth red pixels are used only for this
offline error measurement and never enter the policy/runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
import sys
import time
import types

import numpy as np

# The bundled diagnostic runtime does not ship PyYAML.  This probe reads only
# JSON manifests, but importing ``uavlab`` also imports its optional YAML
# composition module.  A non-callable placeholder keeps that unrelated import
# from blocking a JSON-only diagnostic; architecture loading still fails loudly
# if somebody later changes this script to request YAML.
try:
    import yaml as _yaml  # noqa: F401
except ModuleNotFoundError:
    yaml_stub = types.ModuleType("yaml")

    def _no_yaml(*_args, **_kwargs):
        raise RuntimeError("PyYAML is required for YAML configuration loading")

    yaml_stub.safe_load = _no_yaml
    sys.modules["yaml"] = yaml_stub

from uavlab.contracts import ControlCommand, Frame, Vec3
from uavlab.core.config import ArchitectureConfig, EnvironmentConfig, EpisodeSpec
from uavlab.core.frame_store import global_store
from uavlab.core.orchestrator import Orchestrator
from uavlab.plugins.inference.ollama import OllamaInference
from uavlab.plugins.reasoning.onfly import _encode_png, _extract_json


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _red_bbox(image) -> tuple[int, int, int, int] | None:
    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    mask = (
        (rgb[..., 0] > 160)
        & (rgb[..., 0] > rgb[..., 1] + 30)
        & (rgb[..., 0] > rgb[..., 2] + 30)
    )
    ys, xs = np.nonzero(mask)
    if not xs.size:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


async def _reconstruct(run_dir: Path, wanted: set[int]):
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    env_cfg = EnvironmentConfig.model_validate(manifest["environment_config"])
    seed = int(manifest["seeds"][0])
    harness = Orchestrator(arch, env_cfg, EpisodeSpec(episode_id="coordinate_probe", seed=seed))

    params = dict(env_cfg.params)
    params.update(env_cfg.adapter.params)
    params["allow_privileged"] = False
    params["failures"] = []
    env = harness.registry.build("environment", env_cfg.adapter.name, params)
    await env.reset(harness.mission, seed)

    frames = {}
    controls = [e for e in _events(run_dir / "events.jsonl") if e["event_type"] == "control"]
    for event in controls:
        observation = await env.observe()
        if observation.seq in wanted and observation.rgb is not None:
            image = global_store().get(observation.rgb.uri)
            if image is not None:
                frames[observation.seq] = image.copy()
        payload = event["payload"]
        command = ControlCommand(
            t_sim_ns=int(event["t_sim_ns"]),
            velocity=Vec3(
                x=float(payload["vx"]),
                y=float(payload["vy"]),
                z=float(payload["vz"]),
            ),
            yaw_rate_rps=float(payload["yaw_rate"]),
            frame=Frame.ENU,
        )
        await env.step(command, 50_000_000)
        # Continue through the complete log even after all requested frames are
        # captured.  The final scored distance is an exact-replay check: if it
        # differs from the stored result, the camera frames are not admissible
        # evidence for diagnosing the original flight.
    replay_status = env.status()
    await env.close()
    return frames, replay_status


def _ask(
    backend: OllamaInference, model: str, image, contract: str
) -> tuple[int, int, str, float]:
    if contract == "normalized":
        prompt = (
            "Locate the center of the red tower. Return only JSON with integer u and v, "
            "where u and v are normalized image coordinates from 0 to 100: u=0 is the "
            "left edge, u=100 the right edge, v=0 the top edge, and v=100 the bottom edge."
        )
        maximum_u = maximum_v = 100
    elif contract == "qwen-1000":
        prompt = (
            "Locate the center of the red tower. Return only JSON with integer u and v "
            "as relative coordinates on a 1000 by 1000 reference grid: u=0 is the left "
            "edge, u=999 the right edge, v=0 the top edge, and v=999 the bottom edge."
        )
        maximum_u = maximum_v = 999
    else:
        prompt = (
            "You are OnFly's high-frequency decision agent on a UAV. Select the next "
            "image-space navigation target for the current subtask. Pixel (0,0) is "
            "top-left. Image size is 224x224. Subtask: fly to the red tower and stop "
            "there. There is no valid previous-goal pixel in the current view. Return "
            "only JSON with integer u and v. Do not report distance, world coordinates, "
            "completion, or flight controls."
        )
        maximum_u = image.width - 1
        maximum_v = image.height - 1
    schema = {
        "type": "object",
        "properties": {
            "u": {"type": "integer", "minimum": 0, "maximum": maximum_u},
            "v": {"type": "integer", "minimum": 0, "maximum": maximum_v},
        },
        "required": ["u", "v"],
        "additionalProperties": False,
    }
    started = time.perf_counter()
    response = backend._post(
        "/api/chat",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [_encode_png(image)]}],
            "format": schema,
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.0, "num_predict": 64, "seed": 0},
        },
    )
    latency_s = time.perf_counter() - started
    message = response.get("message", {})
    raw = str(message.get("content") or message.get("thinking") or "")
    parsed = _extract_json(raw)
    return int(parsed["u"]), int(parsed["v"]), raw, latency_s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model", default="qwen3-vl:8b")
    parser.add_argument("--seq", nargs="+", type=int, required=True)
    parser.add_argument(
        "--contract",
        choices=("normalized", "qwen-1000", "onfly-raw"),
        default="normalized",
    )
    args = parser.parse_args()

    wanted = set(args.seq)
    frames, replay_status = asyncio.run(_reconstruct(args.run_dir, wanted))
    original_result = json.loads((args.run_dir / "result.json").read_text(encoding="utf-8"))
    original_distance = float(original_result["metrics"]["distance_to_goal_m"])
    backend = OllamaInference(model_id=args.model, timeout_s=180.0)
    rows = []
    try:
        for seq in args.seq:
            image = frames.get(seq)
            if image is None:
                rows.append({"observation_seq": seq, "error": "frame not reconstructed"})
                continue
            bbox = _red_bbox(image)
            if bbox is None:
                rows.append({"observation_seq": seq, "error": "red target not visible"})
                continue
            x0, y0, x1, y1 = bbox
            truth_u = 100.0 * (x0 + x1) / 2.0 / (image.width - 1)
            truth_v = 100.0 * (y0 + y1) / 2.0 / (image.height - 1)
            pred_u, pred_v, _, latency_s = _ask(backend, args.model, image, args.contract)
            row = {
                "observation_seq": seq,
                "bbox_px": [x0, y0, x1, y1],
                "truth_normalized": [round(truth_u, 2), round(truth_v, 2)],
                "prediction_returned": [pred_u, pred_v],
                "latency_s": round(latency_s, 4),
            }
            if args.contract == "normalized":
                row["error_normalized"] = round(
                    math.hypot(pred_u - truth_u, pred_v - truth_v), 2
                )
            elif args.contract == "qwen-1000":
                truth_x = (x0 + x1) / 2.0
                truth_y = (y0 + y1) / 2.0
                row["truth_pixel"] = [round(truth_x, 2), round(truth_y, 2)]
                row["error_after_qwen_scaling_px"] = round(
                    math.hypot(
                        pred_u * (image.width - 1) / 999.0 - truth_x,
                        pred_v * (image.height - 1) / 999.0 - truth_y,
                    ),
                    2,
                )
            else:
                truth_x = (x0 + x1) / 2.0
                truth_y = (y0 + y1) / 2.0
                row["truth_pixel"] = [round(truth_x, 2), round(truth_y, 2)]
                row["error_if_raw_pixels"] = round(
                    math.hypot(pred_u - truth_x, pred_v - truth_y), 2
                )
                row["error_if_normalized_0_100"] = round(
                    math.hypot(
                        pred_u * (image.width - 1) / 100.0 - truth_x,
                        pred_v * (image.height - 1) / 100.0 - truth_y,
                    ),
                    2,
                )
            rows.append(row)
    finally:
        backend.close()

    error_key = {
        "normalized": "error_normalized",
        "qwen-1000": "error_after_qwen_scaling_px",
        "onfly-raw": "error_if_raw_pixels",
    }[args.contract]
    errors = [row[error_key] for row in rows if error_key in row]
    print(
        json.dumps(
            {
                "model": args.model,
                "coordinate_contract": args.contract,
                "replay_distance_to_goal_m": replay_status.distance_to_goal_m,
                "original_distance_to_goal_m": original_distance,
                "replay_distance_error_m": abs(
                    replay_status.distance_to_goal_m - original_distance
                ),
                "rows": rows,
                "mean_primary_error": round(float(np.mean(errors)), 2) if errors else None,
                "max_primary_error": round(float(np.max(errors)), 2) if errors else None,
                "median_latency_s": round(
                    float(np.median([row["latency_s"] for row in rows if "latency_s" in row])),
                    4,
                )
                if rows
                else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
