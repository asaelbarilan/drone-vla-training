"""Collect Qwen3-VL supervised action-token data from local-simulator experts.

The student receives only the same dual RGB mosaic, language instruction, and
coarse bearing bucket as the deployed AeroVLA-style policy. Simulator truth is
used only by the teacher and to label terminal actions; it is never serialized
as a student input.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uavlab.contracts import ControlCommand
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.plugins.reasoning.aerovla import (
    FORWARD_RANGE,
    NUM_BINS,
    VERTICAL_DOWN_RANGE,
    YAW_RANGE,
    AeroVLAOutput,
    aerovla_prompt,
    make_dual_view_mosaic,
    parse_aerovla_output,
)
from uavlab.training.splits import check_collection_range


@dataclass(slots=True)
class CapturedVLASample:
    image: Any
    target: AeroVLAOutput
    hint: str
    tick: int
    t_sim_ns: int


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: row must be a JSON object")
            rows.append(value)
    return rows


def validate_dataset(dataset_dir: Path) -> dict[str, object]:
    """Fail closed on leakage, missing images, malformed targets, or collapse."""
    dataset_dir = Path(dataset_dir)
    required = [
        "manifest.json",
        "index.jsonl",
        "train.jsonl",
        "val.jsonl",
        "train_swift.jsonl",
        "val_swift.jsonl",
    ]
    missing = [name for name in required if not (dataset_dir / name).is_file()]
    if missing:
        raise ValueError(f"dataset is missing required files: {', '.join(missing)}")

    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    index = _read_jsonl(dataset_dir / "index.jsonl")
    split_rows = {
        "train": _read_jsonl(dataset_dir / "train.jsonl"),
        "val": _read_jsonl(dataset_dir / "val.jsonl"),
    }
    swift_rows = {
        "train": _read_jsonl(dataset_dir / "train_swift.jsonl"),
        "val": _read_jsonl(dataset_dir / "val_swift.jsonl"),
    }
    if len(index) != sum(len(rows) for rows in split_rows.values()):
        raise ValueError("index and train/validation sample counts differ")

    by_image: dict[str, dict[str, Any]] = {}
    split_seeds: dict[str, set[int]] = {"train": set(), "val": set()}
    target_counts: Counter[str] = Counter()
    land_count = 0
    for row in index:
        relative = row.get("image")
        split = row.get("split")
        seed = row.get("seed")
        target = row.get("target")
        if not isinstance(relative, str) or not (dataset_dir / relative).is_file():
            raise ValueError(f"missing image referenced by index: {relative!r}")
        if relative in by_image:
            raise ValueError(f"duplicate indexed image: {relative}")
        if split not in split_seeds or not isinstance(seed, int):
            raise ValueError(f"invalid split or seed for {relative}")
        if seed not in range(1000, 2000):
            raise ValueError(f"seed leakage for {relative}: {seed} is outside training seeds")
        parsed = parse_aerovla_output(json.dumps(target, separators=(",", ":")))
        canonical = action_json(parsed)
        target_counts[canonical] += 1
        land_count += int(parsed.land)
        split_seeds[split].add(seed)
        by_image[relative] = row

    overlap = split_seeds["train"] & split_seeds["val"]
    if overlap:
        raise ValueError(f"train/validation seeds overlap: {sorted(overlap)[:5]}")

    seen_images: set[str] = set()
    for split, rows in split_rows.items():
        for row in rows:
            relative = row.get("image")
            conversations = row.get("conversations")
            if relative not in by_image or by_image[relative]["split"] != split:
                raise ValueError(
                    f"{split}.jsonl contains unknown or cross-split image {relative!r}"
                )
            if relative in seen_images:
                raise ValueError(f"duplicate annotation for image {relative}")
            seen_images.add(relative)
            if not isinstance(conversations, list) or len(conversations) != 2:
                raise ValueError(f"{relative}: conversations must contain human and assistant")
            human, assistant = conversations
            if human.get("from") != "human" or human.get("value", "").count("<image>") != 1:
                raise ValueError(f"{relative}: human turn must contain exactly one image token")
            if assistant.get("from") != "gpt":
                raise ValueError(f"{relative}: second turn must be the assistant target")
            parsed = parse_aerovla_output(assistant.get("value"))
            indexed = parse_aerovla_output(json.dumps(by_image[relative]["target"]))
            if action_json(parsed) != action_json(indexed):
                raise ValueError(f"{relative}: annotation target differs from index")

    if seen_images != set(by_image):
        raise ValueError("some indexed samples are absent from train/validation annotations")
    for split, rows in swift_rows.items():
        if len(rows) != len(split_rows[split]):
            raise ValueError(f"{split}_swift.jsonl sample count differs from official annotations")
        for row in rows:
            images = row.get("images")
            messages = row.get("messages")
            if not isinstance(images, list) or len(images) != 1 or not isinstance(images[0], str):
                raise ValueError(f"{split}_swift.jsonl has an invalid image reference")
            swift_path = Path(images[0])
            if not swift_path.is_absolute():
                swift_path = Path.cwd() / swift_path
            matches = [
                relative
                for relative in by_image
                if (dataset_dir / relative).resolve() == swift_path.resolve()
            ]
            if len(matches) != 1:
                raise ValueError(f"{split}_swift.jsonl image is outside this dataset: {images[0]}")
            relative = matches[0]
            if by_image[relative]["split"] != split:
                raise ValueError(f"{split}_swift.jsonl crosses the seed split")
            if not isinstance(messages, list) or len(messages) != 2:
                raise ValueError(f"{relative}: ms-swift messages must contain user and assistant")
            valid_user = messages[0].get("role") == "user"
            valid_image_token = messages[0].get("content", "").count("<image>") == 1
            if not valid_user or not valid_image_token:
                raise ValueError(f"{relative}: ms-swift user turn must contain one image token")
            if messages[1].get("role") != "assistant":
                raise ValueError(f"{relative}: invalid ms-swift assistant turn")
            parsed = parse_aerovla_output(messages[1].get("content"))
            indexed = parse_aerovla_output(json.dumps(by_image[relative]["target"]))
            if action_json(parsed) != action_json(indexed):
                raise ValueError(f"{relative}: ms-swift target differs from index")
    if not index:
        raise ValueError("dataset contains no samples")
    if not split_seeds["train"] or not split_seeds["val"]:
        raise ValueError("both train and validation must contain at least one complete seed")
    if land_count == 0:
        raise ValueError("dataset has no LAND-positive sample")

    max_action_count = max(target_counts.values())
    largest_action_fraction = max_action_count / len(index)
    if len(index) >= 100 and largest_action_fraction > 0.5:
        raise ValueError(
            f"action collapse: one target occupies {largest_action_fraction:.1%} of samples"
        )
    report: dict[str, object] = {
        "valid": True,
        "samples": len(index),
        "train_samples": len(split_rows["train"]),
        "validation_samples": len(split_rows["val"]),
        "train_seeds": len(split_seeds["train"]),
        "validation_seeds": len(split_seeds["val"]),
        "unique_actions": len(target_counts),
        "largest_action_fraction": largest_action_fraction,
        "terminal_positive_rate": land_count / len(index),
        "format": manifest.get("format"),
    }
    return report


def quantize(value: float, value_range: tuple[float, float]) -> int:
    """Nearest one of AeroVLA's 99 uniformly spaced numerical tokens."""
    low, high = value_range
    clipped = min(high, max(low, float(value)))
    return round((clipped - low) * (NUM_BINS - 1) / (high - low))


def _wrap_angle(value: float) -> float:
    return math.atan2(math.sin(value), math.cos(value))


def expert_command_to_aerovla(
    command: ControlCommand,
    yaw_rad: float,
    *,
    horizon_s: float = 0.25,
    terminal: bool = False,
) -> AeroVLAOutput:
    """Convert one expert ENU command to the released AeroVLA token geometry.

    Horizontal velocity determines a short body-relative displacement and the
    yaw needed to face it. Vertical velocity becomes down-positive displacement.
    A nonterminal zero command uses the smallest positive forward bin because
    the released codec interprets an all-zero displacement as LAND.
    """
    if horizon_s <= 0:
        raise ValueError("horizon_s must be positive")
    if terminal:
        return AeroVLAOutput(0, quantize(0.0, VERTICAL_DOWN_RANGE), quantize(0.0, YAW_RANGE), True)

    vx, vy, vz = command.velocity.x, command.velocity.y, command.velocity.z
    horizontal_speed = math.hypot(vx, vy)
    forward_m = min(FORWARD_RANGE[1], horizontal_speed * horizon_s)
    if horizontal_speed > 1e-6:
        desired_yaw = math.atan2(vy, vx)
        yaw_delta_enu = _wrap_angle(desired_yaw - yaw_rad)
    else:
        yaw_delta_enu = command.yaw_rate_rps * horizon_s

    output = AeroVLAOutput(
        forward_bin=quantize(forward_m, FORWARD_RANGE),
        vertical_bin=quantize(-vz * horizon_s, VERTICAL_DOWN_RANGE),
        # Released actions use NED clockwise-positive yaw; the simulator is ENU.
        yaw_bin=quantize(-yaw_delta_enu, YAW_RANGE),
        land=False,
    )
    if output.forward_bin == 0 and output.vertical_bin == 49 and output.yaw_bin == 49:
        return AeroVLAOutput(1, 49, 49, False)
    return output


def action_json(target: AeroVLAOutput) -> str:
    return json.dumps(
        {
            "forward_bin": target.forward_bin,
            "vertical_bin": target.vertical_bin,
            "yaw_bin": target.yaw_bin,
            "land": target.land,
        },
        separators=(",", ":"),
    )


def qwen_record(
    image_path: str,
    instruction: str,
    hint: str,
    target: AeroVLAOutput,
) -> dict[str, object]:
    """Official Qwen3-VL single-image SFT format with the deployment prompt."""
    return {
        "image": image_path,
        "conversations": [
            {
                "from": "human",
                "value": "<image>\n" + aerovla_prompt(instruction, hint, "json"),
            },
            {"from": "gpt", "value": action_json(target)},
        ],
    }


def swift_record(
    image_path: str,
    instruction: str,
    hint: str,
    target: AeroVLAOutput,
) -> dict[str, object]:
    """Native ms-swift multimodal JSONL format, with the identical prompt."""
    return {
        "images": [image_path],
        "messages": [
            {
                "role": "user",
                "content": "<image>\n" + aerovla_prompt(instruction, hint, "json"),
            },
            {"role": "assistant", "content": action_json(target)},
        ],
    }


async def collect_episode(
    arch: Any,
    env: Any,
    seed: int,
    *,
    stride: int = 10,
    horizon_s: float = 0.25,
    image_size: int = 224,
) -> tuple[list[CapturedVLASample], bool]:
    """Fly one expert episode and capture synchronized dual-view action pairs."""
    if stride < 1:
        raise ValueError("stride must be positive")
    from uavlab.adapters.gym.deterministic_env import DeterministicEnv
    from uavlab.core.frame_store import global_store

    samples: list[CapturedVLASample] = []
    original = DeterministicEnv.step
    tick = 0

    async def recording_step(self, command, dt_ns):
        nonlocal tick
        if tick % stride == 0:
            seq = max(self._seq - 1, 0)
            front = global_store().get(f"frame://{self._frame_ns}/rgb/{seq}")
            down = global_store().get(f"frame://{self._frame_ns}/rgb_down/{seq}")
            hint = self._coarse_goal_direction()
            if front is not None and down is not None and hint is not None:
                terminal = self.status().distance_to_goal_m <= self.goal_radius_m
                samples.append(
                    CapturedVLASample(
                        image=make_dual_view_mosaic(front, down, image_size),
                        target=expert_command_to_aerovla(
                            command,
                            self.vehicle.yaw,
                            horizon_s=horizon_s,
                            terminal=terminal,
                        ),
                        hint=hint,
                        tick=tick,
                        t_sim_ns=self._t_ns,
                    )
                )
        tick += 1
        await original(self, command, dt_ns)

    DeterministicEnv.step = recording_step
    try:
        result = await Orchestrator(
            arch,
            env,
            EpisodeSpec(episode_id=f"qwen_vla_expert_{seed}", seed=seed),
        ).run()
    finally:
        DeterministicEnv.step = original
    return samples, bool(result.success)


def collect(
    out_dir: Path,
    *,
    episodes: int = 100,
    env_name: str = "grid_nav_aerovla",
    expert: str = "c0",
    stride: int = 10,
    horizon_s: float = 0.25,
    start_seed: int = 1000,
    validation_modulus: int = 5,
    jpeg_quality: int = 85,
    config_root: Path | None = None,
    progress: bool = True,
) -> dict[str, object]:
    """Create image files plus official Qwen JSONL annotations and a manifest."""
    check_collection_range(start_seed, episodes)
    if validation_modulus < 2:
        raise ValueError("validation_modulus must be at least 2")
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError(f"refusing to mix a new dataset into non-empty {out_dir}")
    image_dir = out_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    arch = load_architecture(expert, config_root)
    env = load_environment(env_name, config_root)
    if not env.params.get("render") or not env.params.get("render_down"):
        raise ValueError("Qwen-VLA collection requires front and downward rendering")
    if not env.params.get("coarse_goal_direction"):
        raise ValueError("Qwen-VLA collection requires the declared coarse bearing prior")

    annotations: dict[str, list[dict[str, object]]] = {"train": [], "val": []}
    swift_annotations: dict[str, list[dict[str, object]]] = {"train": [], "val": []}
    index_rows: list[dict[str, object]] = []
    action_counts: Counter[str] = Counter()
    kept = skipped = 0

    for offset in range(episodes):
        seed = start_seed + offset
        samples, success = asyncio.run(
            collect_episode(
                arch,
                env,
                seed,
                stride=stride,
                horizon_s=horizon_s,
            )
        )
        if not success:
            skipped += 1
            continue
        kept += 1
        split = "val" if seed % validation_modulus == 0 else "train"
        for sample in samples:
            name = f"s{seed}_t{sample.tick:05d}.jpg"
            relative = f"images/{name}"
            sample.image.save(image_dir / name, format="JPEG", quality=jpeg_quality)
            annotations[split].append(
                qwen_record(relative, env.instruction, sample.hint, sample.target)
            )
            swift_image = (out_dir / relative).resolve().as_posix()
            swift_annotations[split].append(
                swift_record(swift_image, env.instruction, sample.hint, sample.target)
            )
            answer = action_json(sample.target)
            action_counts[answer] += 1
            index_rows.append(
                {
                    "image": relative,
                    "seed": seed,
                    "split": split,
                    "tick": sample.tick,
                    "t_sim_ns": sample.t_sim_ns,
                    "coarse_goal_direction": sample.hint,
                    "target": json.loads(answer),
                }
            )
        if progress and (offset + 1) % 10 == 0:
            print(
                f"  {offset + 1}/{episodes} episodes kept={kept} skipped={skipped} "
                f"samples={len(index_rows)}",
                flush=True,
            )

    if not index_rows:
        raise RuntimeError("expert produced no successful dual-view samples")
    for split, rows in annotations.items():
        with (out_dir / f"{split}.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        with (out_dir / f"{split}_swift.jsonl").open("w", encoding="utf-8") as handle:
            for row in swift_annotations[split]:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out_dir / "index.jsonl").open("w", encoding="utf-8") as handle:
        for row in index_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    image_bytes = sum(path.stat().st_size for path in image_dir.glob("*.jpg"))
    terminal_count = sum(int(row["target"]["land"]) for row in index_rows)
    manifest: dict[str, object] = {
        "format": "qwen3_vl_single_image_sft_v1+ms_swift_messages_v1",
        "expert": expert,
        "environment": env_name,
        "instruction": env.instruction,
        "episodes_requested": episodes,
        "episodes_kept": kept,
        "episodes_skipped_as_failures": skipped,
        "seeds": [start_seed, start_seed + episodes - 1],
        "held_out_seeds": [1, 40],
        "split_rule": f"validation iff seed % {validation_modulus} == 0",
        "samples": len(index_rows),
        "train_samples": len(annotations["train"]),
        "validation_samples": len(annotations["val"]),
        "stride_control_ticks": stride,
        "label_horizon_s": horizon_s,
        "image_size": 224,
        "jpeg_quality": jpeg_quality,
        "image_bytes": image_bytes,
        "terminal_positive_rate": terminal_count / len(index_rows),
        "action_contract": {
            "bins": NUM_BINS,
            "forward_range_m": list(FORWARD_RANGE),
            "vertical_down_range_m": list(VERTICAL_DOWN_RANGE),
            "yaw_ned_range_rad": list(YAW_RANGE),
        },
        "top_actions": action_counts.most_common(20),
        "student_inputs": ["front_rgb", "down_rgb", "instruction", "coarse_goal_direction"],
        "privileged_teacher_only": True,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest
