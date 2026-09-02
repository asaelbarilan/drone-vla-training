"""Offline gate for OnFly's forced-choice monitor on an exact run replay."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from uavlab.contracts import ControlCommand, Frame, PerceptionState, Vec3
from uavlab.core.config import ArchitectureConfig, EnvironmentConfig, EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.plugins.inference.ollama import OllamaInference
from uavlab.plugins.reasoning.onfly import (
    _ONFLY_VISUALS,
    OnFlyHybridMemory,
    _encode_png,
    _extract_json,
    _monitor_prompt,
)


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _has_red(image) -> bool:
    import numpy as np

    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    return bool(
        (
            (rgb[..., 0] > 160)
            & (rgb[..., 0] > rgb[..., 1] + 30)
            & (rgb[..., 0] > rgb[..., 2] + 30)
        ).any()
    )


def _contact_sheet(images: list):
    from PIL import Image, ImageDraw

    columns = 3
    rows = (len(images) + columns - 1) // columns
    panel_w, panel_h, label_h = 224, 224, 24
    sheet = Image.new("RGB", (columns * panel_w, rows * (panel_h + label_h)), "black")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(images):
        x = (index % columns) * panel_w
        y = (index // columns) * (panel_h + label_h)
        sheet.paste(image.convert("RGB").resize((panel_w, panel_h)), (x, y + label_h))
        label = "LATEST" if index == len(images) - 1 else f"HISTORY {index + 1}"
        draw.text((x + 6, y + 5), label, fill="white")
    return sheet


def _latest_emphasis_sheet(images: list):
    from PIL import Image, ImageDraw

    sheet = Image.new("RGB", (672, 472), "black")
    draw = ImageDraw.Draw(sheet)
    history = images[:-1]
    for index, image in enumerate(history):
        x = (index % 2) * 112
        y = (index // 2) * 148
        draw.text((x + 4, y + 3), f"HISTORY {index + 1}", fill="white")
        sheet.paste(image.convert("RGB").resize((112, 112)), (x, y + 24))
    draw.text((236, 3), "LATEST (judge STOP/LOST from this large panel)", fill="white")
    sheet.paste(images[-1].convert("RGB").resize((436, 436)), (236, 28))
    return sheet


def _labeled_multi_images(images: list):
    """Preserve each sensor frame while making its temporal role explicit."""
    from PIL import Image, ImageDraw

    labeled = []
    for index, image in enumerate(images):
        rgb = image.convert("RGB")
        panel = Image.new("RGB", (rgb.width, rgb.height + 24), "black")
        label = "LATEST" if index == len(images) - 1 else f"HISTORY {index + 1}"
        ImageDraw.Draw(panel).text((6, 5), label, fill="white")
        panel.paste(rgb, (0, 24))
        labeled.append(panel)
    return labeled


async def _contexts(run_dir: Path) -> tuple[dict[float, list], str]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    events = _events(run_dir / "events.jsonl")
    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    env_cfg = EnvironmentConfig.model_validate(manifest["environment_config"])
    seed = int(manifest["seeds"][0])
    harness = Orchestrator(arch, env_cfg, EpisodeSpec(episode_id="monitor_probe", seed=seed))
    params = dict(env_cfg.params)
    params.update(env_cfg.adapter.params)
    params["allow_privileged"] = False
    params["failures"] = []
    env = harness.registry.build("environment", env_cfg.adapter.name, params)
    await env.reset(harness.mission, seed)

    memory = OnFlyHybridMemory(**arch.memory.params)
    memory.reset(harness.mission, seed)
    policy_sources = {
        int(event["payload"]["source_observation_seq"])
        for event in events
        if event["event_type"] == "decision_proposed"
        and event["payload"].get("producer") == "onfly_decision"
    }
    charged_s = float(arch.inference.params["fixed_latency_s"]["monitor"])
    pending = [
        (event["t_sim_ns"] / 1e9 - charged_s, event["t_sim_ns"] / 1e9)
        for event in events
        if event["event_type"] == "monitor"
    ]
    captured: dict[float, list] = {}

    controls = [event for event in events if event["event_type"] == "control"]
    for event in controls:
        observation = await env.observe()
        if observation.seq in policy_sources:
            memory.update(
                observation,
                PerceptionState(
                    observation_seq=observation.seq,
                    t_sim_ns=observation.t_sim_ns,
                ),
                None,
            )
        t_s = event["t_sim_ns"] / 1e9
        while pending and pending[0][0] <= t_s + 1e-9:
            _, result_t = pending.pop(0)
            selected = []
            for item in memory.snapshot().items:
                if item.image_uri and item.image_uri in _ONFLY_VISUALS:
                    selected.append(_ONFLY_VISUALS[item.image_uri].copy())
            captured[result_t] = selected

        payload = event["payload"]
        await env.step(
            ControlCommand(
                t_sim_ns=int(event["t_sim_ns"]),
                velocity=Vec3(
                    x=float(payload["vx"]),
                    y=float(payload["vy"]),
                    z=float(payload["vz"]),
                ),
                yaw_rate_rps=float(payload["yaw_rate"]),
                frame=Frame.ENU,
            ),
            50_000_000,
        )
    await env.close()
    return captured, harness.mission.instruction


def _ask(
    backend: OllamaInference,
    model: str,
    instruction: str,
    images: list,
    *,
    num_ctx: int,
    separate_messages: bool = False,
    per_image_evidence: bool = False,
) -> dict:
    schema = {
        "type": "object",
        "properties": {
            "earlier_target_visible": {"type": "boolean"},
            "latest_target_visible": {"type": "boolean"},
            "latest_target_scale": {
                "type": "string",
                "enum": ["absent", "small", "large"],
            },
            "status": {"type": "string", "enum": ["CONTINUE", "STOP", "LOST"]},
        },
        "required": [
            "earlier_target_visible",
            "latest_target_visible",
            "latest_target_scale",
            "status",
        ],
        "additionalProperties": False,
    }
    prompt = _monitor_prompt(instruction) + (
        " Inspect the latest image separately from all earlier images. Also report bounded "
        "visual evidence: earlier_target_visible, latest_target_visible, and "
        "latest_target_scale as absent, small, or large."
    )
    if per_image_evidence:
        schema = {
            "type": "object",
            "properties": {
                "target_visible_by_image": {
                    "type": "array",
                    "items": {"type": "boolean"},
                    "minItems": len(images),
                    "maxItems": len(images),
                },
                "latest_target_scale": {
                    "type": "string",
                    "enum": ["absent", "small", "large"],
                },
                "status": {"type": "string", "enum": ["CONTINUE", "STOP", "LOST"]},
            },
            "required": ["target_visible_by_image", "latest_target_scale", "status"],
            "additionalProperties": False,
        }
        prompt += (
            f" There are exactly {len(images)} chronological images. Return one target "
            "visibility boolean for EACH image in order as target_visible_by_image; the "
            "last boolean is the LATEST image and alone determines current visibility."
        )
    started = time.perf_counter()
    if separate_messages:
        messages = [
            {
                "role": "user",
                "content": (
                    "LATEST route image. Judge current visibility and STOP/LOST "
                    "from this image."
                    if index == len(images) - 1
                    else f"HISTORY route image {index + 1}."
                ),
                "images": [_encode_png(image)],
            }
            for index, image in enumerate(images)
        ]
        messages.append({"role": "user", "content": prompt})
    else:
        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [_encode_png(image) for image in images],
            }
        ]
    response = backend._post(
        "/api/chat",
        {
            "model": model,
            "messages": messages,
            "format": schema,
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.0,
                "num_predict": 48,
                "num_ctx": num_ctx,
                "seed": 0,
            },
        },
    )
    latency_s = time.perf_counter() - started
    message = response.get("message", {})
    content = str(message.get("content") or "")
    thinking = str(message.get("thinking") or "")
    selected_channel = "content" if content else "thinking"
    raw = content or thinking
    try:
        parsed = _extract_json(raw)
        parse_error = None
    except ValueError as exc:
        parsed = None
        parse_error = str(exc)
    return {
        "payload": parsed,
        "parse_error": parse_error,
        "server_error": response.get("error"),
        "response_keys": sorted(response),
        "raw_preview": raw[:500] if parse_error else None,
        "response_channel": selected_channel,
        "content_chars": len(content),
        "thinking_chars": len(thinking),
        "done_reason": response.get("done_reason"),
        "latency_s": round(latency_s, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--model", default="qwen3-vl:8b")
    parser.add_argument("--num-ctx", type=int, default=8192)
    parser.add_argument("--times", nargs="+", type=float, required=True)
    parser.add_argument("--contact-sheet", action="store_true")
    parser.add_argument("--latest-emphasis", action="store_true")
    parser.add_argument("--labeled-multi-image", action="store_true")
    parser.add_argument("--separate-messages", action="store_true")
    parser.add_argument("--per-image-evidence", action="store_true")
    parser.add_argument("--history-sheet-latest", action="store_true")
    parser.add_argument("--latest-only", action="store_true")
    parser.add_argument("--save-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contexts, instruction = asyncio.run(_contexts(args.run_dir))
    backend = OllamaInference(model_id=args.model, timeout_s=180.0)
    rows = []
    try:
        for requested in args.times:
            actual = min(contexts, key=lambda value: abs(value - requested))
            images = contexts[actual]
            if args.latest_emphasis:
                model_images = [_latest_emphasis_sheet(images)]
                layout = "latest_emphasis_sheet"
            elif args.latest_only:
                model_images = [images[-1]]
                layout = "latest_only"
            elif args.history_sheet_latest:
                model_images = [_contact_sheet(images[:-1]), images[-1]]
                layout = "history_sheet_plus_latest"
            elif args.labeled_multi_image:
                model_images = _labeled_multi_images(images)
                layout = "labeled_multi_image"
            elif args.contact_sheet:
                model_images = [_contact_sheet(images)]
                layout = "labeled_contact_sheet"
            else:
                model_images = images
                layout = "multi_image"
            if args.save_dir is not None:
                args.save_dir.mkdir(parents=True, exist_ok=True)
                for image_index, model_image in enumerate(model_images):
                    model_image.save(
                        args.save_dir
                        / f"monitor_{actual:.1f}s_{layout}_{image_index}.png"
                    )
            rows.append(
                {
                    "requested_monitor_result_t_s": requested,
                    "actual_monitor_result_t_s": actual,
                    "image_count": len(images),
                    "model_image_count": len(model_images),
                    "layout": layout,
                    "red_visible_by_image": [_has_red(image) for image in images],
                    "model_output": _ask(
                        backend,
                        args.model,
                        instruction,
                        model_images,
                        num_ctx=args.num_ctx,
                        separate_messages=args.separate_messages,
                        per_image_evidence=args.per_image_evidence,
                    ),
                    "message_layout": (
                        "one_labeled_message_per_image"
                        if args.separate_messages
                        else "single_message"
                    ),
                }
            )
    finally:
        backend.close()
    report = {
        "run": args.run_dir.as_posix(),
        "model": args.model,
        "prompt": "paper-compatible explicit post-acquisition LOST contract",
        "rows": rows,
        "truth_scope": "red-pixel visibility is offline scoring only",
    }
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
