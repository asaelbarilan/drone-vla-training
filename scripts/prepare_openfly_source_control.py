"""Prepare one source-matched env18 control, selected before any new inference."""

import hashlib
import io
import json
import os
import struct
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import numpy as np
import pyarrow.parquet as pq
import requests
from audit_openfly_execution import RAW_ACTIONS, trace
from inspect_openfly_rlds_records import bounded_range, crc
from PIL import Image
from tensorflow.core.example.example_pb2 import Example

from uavlab.training.openfly_codec import CODEBOOK, OpenFlyCodec

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_execution_20260919"
CACHE = Path("D:/drone_vla_pilot/data/openfly_rlds_execution_20260919")
RAW_REVISION = "a12316d56a4e35a32ad626fb725ed7089937a1c4"


def main():
    audit = json.loads((OUT / "subset_identity_audit.json").read_text())
    source = next(r for r in audit["rows"] if r["subset"] == "vlnv20")
    route = source["identity"]["episode_metadata/file_path"].split("/uav_vln_data/")[1]
    assert route == "env_airsim_18/astar_data/medium_long/2025-01-19_04-40-57_927964"
    selection = json.loads((ROOT / "reports/vla_joint_openfly_20260917/selection.json").read_text())
    assert route not in {r["episode"]["image_path"] for r in selection["episodes"]}
    for split in ("seen", "unseen"):
        path = Path(f"D:/drone_vla_pilot/data/openfly_eval_20260917/Annotation/{split}.json")
        assert route not in {r["image_path"] for r in json.loads(path.read_text())}
    train = json.loads(
        Path(
            "D:/drone_vla_pilot/data/openfly_train_pilot_20260917/Annotation/train.json"
        ).read_text()
    )
    annotation = next(r for r in train if r["image_path"] == route)
    frozen = {
        "route": route,
        "subset": "vlnv20",
        "rlds_revision": audit["revision"],
        "raw_revision": RAW_REVISION,
        "shard": source["sampled_shard"],
        "selection_rule": "First record of first vlnv20 shard, matching smallest env18 scene",
        "our_adapter_train_or_dev_overlap": False,
        "official_eval_overlap": False,
        "model_outputs_inspected_before_selection": False,
    }
    selection_path = OUT / "source_control_selection.json"
    if selection_path.exists():
        assert json.loads(selection_path.read_text()) == frozen
    else:
        selection_path.write_text(json.dumps(frozen, indent=2))
    CACHE.mkdir(parents=True, exist_ok=True)
    record_path = CACHE / "vlnv20.tfrecord"
    url = (
        "https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly-rlds/resolve/"
        + audit["revision"]
        + "/"
        + source["sampled_shard"]
    )
    if not record_path.exists():
        header = bounded_range(url, 0, 11)
        length, checksum = struct.unpack("<QI", header)
        assert crc(header[:8]) == checksum and 0 < length < 16 * 1024 * 1024
        payload = bounded_range(url, 12, length + 15)
        assert crc(payload[:-4]) == struct.unpack("<I", payload[-4:])[0]
        record_path.write_bytes(header + payload)
    blob = record_path.read_bytes()
    length, checksum = struct.unpack("<QI", blob[:12])
    assert crc(blob[:8]) == checksum and len(blob) == length + 16
    assert crc(blob[12:-4]) == struct.unpack("<I", blob[-4:])[0]
    fields = Example.FromString(blob[12:-4]).features.feature
    assert fields["episode_metadata/file_path"].bytes_list.value[0].decode().endswith(route)
    vectors = np.asarray(fields["steps/action"].float_list.value).reshape(-1, 8)
    config = json.loads(Path("D:/drone_vla_pilot/models/openfly-agent-7b/config.json").read_text())
    codec = OpenFlyCodec(config, "vlnv20")
    codec.require_source_statistics(source["statistics"][0]["data"]["action"])
    ids = []
    for vector in vectors:
        matches = np.flatnonzero(np.all(vector == CODEBOOK, axis=1))
        assert len(matches) == 1
        ids.append(int(matches[0]))
    codec.require_coverage(ids)
    images = {}
    for field in ("image_1", "image_2", "image_3"):
        images[field] = []
        for i, encoded in enumerate(fields["steps/observation/" + field].bytes_list.value):
            dest = CACHE / field / f"{i:04}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(encoded)
            images[field].append({"path": str(dest), "sha256": hashlib.sha256(encoded).hexdigest()})
    raw_path = CACHE / "vlnv20_raw.parquet"
    if not raw_path.exists():
        raw_url = (
            "https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly/resolve/"
            + RAW_REVISION
            + "/traj/"
            + route
            + ".parquet"
        )
        with requests.get(raw_url, stream=True, timeout=(20, 60)) as response:
            response.raise_for_status()
            cap = 64 * 1024 * 1024
            if int(response.headers.get("Content-Length", 0)) > cap:
                raise ValueError("Raw Parquet exceeds download cap")
            data = response.raw.read(cap + 1)
            if len(data) > cap:
                raise ValueError("Raw Parquet exceeds download cap")
            raw_path.write_bytes(data)
    raw = sorted(pq.read_table(raw_path).to_pylist(), key=lambda r: r["frame_index"])
    assert [r["frame_index"] for r in raw] == list(range(len(raw)))
    arrays = [
        [
            np.asarray(
                Image.open(io.BytesIO(r["image"]["bytes"]))
                .convert("RGB")
                .resize((224, 224), method)
            ).astype(np.int16)
            for method in (
                Image.Resampling.BILINEAR,
                Image.Resampling.BICUBIC,
                Image.Resampling.LANCZOS,
                Image.Resampling.NEAREST,
            )
        ]
        for r in raw
    ]
    alignment = []
    for i, image in enumerate(images["image_1"]):
        packed = np.asarray(Image.open(image["path"]).convert("RGB")).astype(np.int16)
        error, index, kernel = min(
            (float(np.abs(packed - a).mean()), j, k)
            for j, values in enumerate(arrays)
            for k, a in enumerate(values)
        )
        alignment.append(
            {"packed_step": i, "raw_frame": index, "pixel_mae_255": error, "kernel_index": kernel}
        )
    current_hashes = [r["sha256"] for r in images["image_1"]]
    future = []
    for i in range(len(ids)):
        for field in ("image_2", "image_3"):
            matches = [
                j for j, sha in enumerate(current_hashes) if sha == images[field][i]["sha256"]
            ]
            if matches and min(matches) > i:
                future.append({"step": i, "slot": field, "matching_future_steps": matches})
    raw_ids = [RAW_ACTIONS.get(r["action_type"]) for r in raw]
    atomic = trace(raw_ids, list(range(len(raw))), raw)
    packed_trace = trace(ids, [a["raw_frame"] for a in alignment], raw)
    result = {
        "selection": frozen,
        "source_statistics_verified": True,
        "record_crc_verified": True,
        "record_bytes": len(blob),
        "record_sha256": hashlib.sha256(blob).hexdigest(),
        "raw_parquet_bytes": raw_path.stat().st_size,
        "raw_parquet_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "raw_frames": len(raw),
        "packed_steps": len(ids),
        "packed_action_ids": ids,
        "packed_instruction": fields["steps/language_instruction"].bytes_list.value[0].decode(),
        "current_instruction": annotation["gpt_instruction"],
        "images": images,
        "alignment": alignment,
        "future_history": future,
        "raw_atomic": atomic,
        "original_packed": packed_trace,
        "atomic_gate_passed": not atomic["invalid_data_label"]
        and atomic["max_position_error"] < 1e-6
        and atomic["max_yaw_error_degrees"] < 1e-6,
        "renderer_used": False,
        "model_used": False,
    }
    (OUT / "source_control.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "record_bytes",
                    "raw_parquet_bytes",
                    "raw_frames",
                    "packed_steps",
                    "atomic_gate_passed",
                )
            }
        ),
        flush=True,
    )
    print(
        json.dumps(
            {
                "packed_max_position_error": packed_trace["max_position_error"],
                "future_history_slots": len(future),
                "max_image_mae": max(a["pixel_mae_255"] for a in alignment),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
