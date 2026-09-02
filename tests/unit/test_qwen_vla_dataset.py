from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from uavlab.contracts import ControlCommand, Vec3
from uavlab.plugins.reasoning.aerovla import (
    FORWARD_RANGE,
    VERTICAL_DOWN_RANGE,
    YAW_RANGE,
    dequantize,
    parse_aerovla_output,
)
from uavlab.training.qwen_vla_dataset import (
    action_json,
    expert_command_to_aerovla,
    quantize,
    qwen_record,
    swift_record,
    validate_dataset,
)


def command(vx: float, vy: float, vz: float = 0.0, yaw_rate: float = 0.0) -> ControlCommand:
    return ControlCommand(
        t_sim_ns=0,
        velocity=Vec3(x=vx, y=vy, z=vz),
        yaw_rate_rps=yaw_rate,
    )


def test_quantizer_is_inverse_of_released_bin_centres() -> None:
    assert quantize(0.0, FORWARD_RANGE) == 0
    assert quantize(5.0, FORWARD_RANGE) == 98
    assert quantize(0.0, VERTICAL_DOWN_RANGE) == 49
    assert quantize(0.0, YAW_RANGE) == 49
    for value in (0.0, 0.4, 1.25, 3.7, 5.0):
        recovered = dequantize(quantize(value, FORWARD_RANGE), FORWARD_RANGE)
        assert recovered == pytest.approx(value, abs=5.0 / 98 / 2 + 1e-9)


def test_expert_enu_command_becomes_body_relative_aerovla_target() -> None:
    forward = expert_command_to_aerovla(command(5.0, 0.0), yaw_rad=0.0)
    assert dequantize(forward.forward_bin, FORWARD_RANGE) == pytest.approx(1.25, abs=0.03)
    assert forward.vertical_bin == 49 and forward.yaw_bin == 49 and not forward.land

    left = expert_command_to_aerovla(command(0.0, 5.0), yaw_rad=0.0)
    assert dequantize(left.yaw_bin, YAW_RANGE) < 0.0
    right = expert_command_to_aerovla(command(0.0, -5.0), yaw_rad=0.0)
    assert dequantize(right.yaw_bin, YAW_RANGE) > 0.0

    climb = expert_command_to_aerovla(command(1.0, 0.0, 2.0), yaw_rad=0.0)
    assert dequantize(climb.vertical_bin, VERTICAL_DOWN_RANGE) < 0.0


def test_nonterminal_hold_does_not_alias_land_and_terminal_does() -> None:
    hold = expert_command_to_aerovla(command(0.0, 0.0), yaw_rad=math.pi)
    assert (hold.forward_bin, hold.vertical_bin, hold.yaw_bin, hold.land) == (1, 49, 49, False)
    land = expert_command_to_aerovla(command(0.0, 0.0), yaw_rad=0.0, terminal=True)
    assert (land.forward_bin, land.vertical_bin, land.yaw_bin, land.land) == (0, 49, 49, True)


def test_qwen_record_uses_official_format_and_strict_deployment_answer() -> None:
    target = expert_command_to_aerovla(command(2.0, 0.0), yaw_rad=0.0)
    record = qwen_record(
        "images/s1000_t00000.jpg",
        "fly to the red tower and stop there",
        "straight ahead",
        target,
    )
    assert record["image"].endswith(".jpg")
    assert record["conversations"][0]["value"].count("<image>") == 1
    answer = record["conversations"][1]["value"]
    assert json.loads(answer) == json.loads(action_json(target))
    assert parse_aerovla_output(answer) == target


def test_swift_record_uses_native_format_and_same_target() -> None:
    target = expert_command_to_aerovla(command(2.0, 0.0), yaw_rad=0.0)
    record = swift_record("images/a.jpg", "find red", "ahead", target)
    assert record["images"] == ["images/a.jpg"]
    assert record["messages"][0]["content"].count("<image>") == 1
    assert parse_aerovla_output(record["messages"][1]["content"]) == target


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_dataset_validator_checks_seed_split_images_and_land(tmp_path: Path) -> None:
    (tmp_path / "images").mkdir()
    target_train = expert_command_to_aerovla(command(2.0, 0.0), yaw_rad=0.0)
    target_val = expert_command_to_aerovla(command(0.0, 0.0), yaw_rad=0.0, terminal=True)
    rows = []
    annotations = {"train": [], "val": []}
    for split, seed, target in (
        ("train", 1001, target_train),
        ("val", 1005, target_val),
    ):
        relative = f"images/s{seed}.jpg"
        (tmp_path / relative).write_bytes(b"jpeg")
        rows.append(
            {
                "image": relative,
                "seed": seed,
                "split": split,
                "target": json.loads(action_json(target)),
            }
        )
        annotations[split].append(qwen_record(relative, "find red", "ahead", target))
    (tmp_path / "manifest.json").write_text('{"format":"test"}', encoding="utf-8")
    _write_jsonl(tmp_path / "index.jsonl", rows)
    _write_jsonl(tmp_path / "train.jsonl", annotations["train"])
    _write_jsonl(tmp_path / "val.jsonl", annotations["val"])
    _write_jsonl(
        tmp_path / "train_swift.jsonl",
        [
            swift_record(
                (tmp_path / "images/s1001.jpg").resolve().as_posix(),
                "find red",
                "ahead",
                target_train,
            )
        ],
    )
    _write_jsonl(
        tmp_path / "val_swift.jsonl",
        [
            swift_record(
                (tmp_path / "images/s1005.jpg").resolve().as_posix(),
                "find red",
                "ahead",
                target_val,
            )
        ],
    )

    report = validate_dataset(tmp_path)
    assert report["valid"] is True
    assert report["train_seeds"] == 1
    assert report["validation_seeds"] == 1
    assert report["terminal_positive_rate"] == 0.5


def test_dataset_validator_rejects_held_out_seed(tmp_path: Path) -> None:
    (tmp_path / "images").mkdir()
    target = expert_command_to_aerovla(command(0.0, 0.0), yaw_rad=0.0, terminal=True)
    relative = "images/s1.jpg"
    (tmp_path / relative).write_bytes(b"jpeg")
    row = {
        "image": relative,
        "seed": 1,
        "split": "train",
        "target": json.loads(action_json(target)),
    }
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    _write_jsonl(tmp_path / "index.jsonl", [row])
    _write_jsonl(tmp_path / "train.jsonl", [qwen_record(relative, "find", "ahead", target)])
    _write_jsonl(tmp_path / "val.jsonl", [])
    swift_image = (tmp_path / relative).resolve().as_posix()
    _write_jsonl(
        tmp_path / "train_swift.jsonl",
        [swift_record(swift_image, "find", "ahead", target)],
    )
    _write_jsonl(tmp_path / "val_swift.jsonl", [])

    with pytest.raises(ValueError, match="seed leakage"):
        validate_dataset(tmp_path)
