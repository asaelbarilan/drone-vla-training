"""Export annotated decision-frame contact sheets from a completed OnFly run.

Simulator truth is used only for the green offline-scoring box. The architecture
never receives the mask or any annotation generated here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from uavlab.contracts import ControlCommand, Frame, Vec3
from uavlab.core.config import ArchitectureConfig, EnvironmentConfig, EpisodeSpec
from uavlab.core.frame_store import global_store
from uavlab.core.orchestrator import Orchestrator


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _red_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
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


def _annotate(
    image: Image.Image,
    *,
    predicted: tuple[float, float],
    bbox: tuple[int, int, int, int] | None,
    text: str,
) -> Image.Image:
    image = image.convert("RGB")
    canvas = Image.new("RGB", (image.width, image.height + 38), "white")
    canvas.paste(image, (0, 0))
    draw = ImageDraw.Draw(canvas)
    u, v = predicted
    draw.line((u - 7, v, u + 7, v), fill=(0, 255, 255), width=2)
    draw.line((u, v - 7, u, v + 7), fill=(0, 255, 255), width=2)
    if bbox is not None:
        draw.rectangle(bbox, outline=(0, 255, 0), width=2)
    draw.text((4, image.height + 3), text, fill="black")
    return canvas


async def export(run_dir: Path, output: Path, every: int = 8) -> dict[str, object]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    events = _events(run_dir / "events.jsonl")
    decisions = [
        event
        for event in events
        if event["event_type"] == "decision_proposed"
        and event["payload"].get("producer") == "onfly_decision"
    ]
    by_observation = {
        int(event["payload"]["source_observation_seq"]): event for event in decisions
    }
    monitors = {
        int(event["t_sim_ns"]): event
        for event in events
        if event["event_type"] == "monitor"
    }

    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    env_cfg = EnvironmentConfig.model_validate(manifest["environment_config"])
    seed = int(manifest["seeds"][0])
    harness = Orchestrator(arch, env_cfg, EpisodeSpec(episode_id="visual_debug", seed=seed))
    params = dict(env_cfg.params)
    params.update(env_cfg.adapter.params)
    params["allow_privileged"] = False
    params["failures"] = []
    env = harness.registry.build("environment", env_cfg.adapter.name, params)
    await env.reset(harness.mission, seed)

    panels: list[Image.Image] = []
    metadata: list[dict[str, object]] = []
    decision_index = 0
    controls = [event for event in events if event["event_type"] == "control"]
    for event in controls:
        observation = await env.observe()
        decision = by_observation.get(observation.seq)
        if decision is not None and observation.rgb is not None:
            should_keep = decision_index % every == 0
            status = env.status()
            image = global_store().get(observation.rgb.uri)
            if image is not None:
                bbox = _red_bbox(image)
                provenance = decision["payload"]["provenance"]
                predicted = (float(provenance["pixel_u"]), float(provenance["pixel_v"]))
                if bbox is not None:
                    should_keep = True
                if should_keep:
                    nearest_monitor = monitors.get(int(event["t_sim_ns"]))
                    monitor_label = (
                        nearest_monitor["payload"].get("label") if nearest_monitor else "-"
                    )
                    text = (
                        f"t={event['t_sim_ns'] / 1e9:.1f}s d={status.distance_to_goal_m:.1f}m "
                        f"target={'yes' if bbox else 'no'} mon={monitor_label}"
                    )
                    panels.append(_annotate(image, predicted=predicted, bbox=bbox, text=text))
                    metadata.append(
                        {
                            "t_sim_s": event["t_sim_ns"] / 1e9,
                            "distance_to_goal_m": status.distance_to_goal_m,
                            "target_visible": bbox is not None,
                            "predicted_pixel": list(predicted),
                            "monitor": monitor_label,
                        }
                    )
            decision_index += 1

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

    if not panels:
        raise RuntimeError("run contained no replayable OnFly decision images")
    columns = 4
    rows = (len(panels) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * panels[0].width, rows * panels[0].height), "#222222")
    for index, panel in enumerate(panels):
        sheet.paste(panel, ((index % columns) * panel.width, (index // columns) * panel.height))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    metadata_path = output.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return {"frames": len(panels), "sheet": str(output), "metadata": str(metadata_path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--every", type=int, default=8)
    args = parser.parse_args()
    if args.every < 1:
        raise SystemExit("--every must be positive")
    print(json.dumps(asyncio.run(export(args.run_dir, args.output, args.every)), indent=2))


if __name__ == "__main__":
    main()
