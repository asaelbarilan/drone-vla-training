"""Build portable playback of original dataset frames, never reconstructed flights."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

from uavlab.training.qwen_vla_dataset import _read_jsonl
from uavlab.training.qwen_vla_preflight import audit_dataset


def build(source: Path, destination: Path) -> dict:
    source = source.resolve()
    audit = audit_dataset(source)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    index = _read_jsonl(source / "index.jsonl")
    annotations = {
        r["image"]: r["conversations"]
        for split in ("train", "val")
        for r in _read_jsonl(source / f"{split}.jsonl")
    }
    episodes = defaultdict(list)
    for row in index:
        raw = (source / row["image"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != audit["image_sha256"][row["image"]]:
            raise ValueError("source changed after audit")
        encoded = base64.b64encode(raw).decode("ascii")
        if base64.b64decode(encoded) != raw:
            raise ValueError("embedded image differs from source")
        episodes[row["seed"]].append(
            {
                **row,
                "sha256": digest,
                "image_url": "data:image/jpeg;base64," + encoded,
                "prompt": annotations[row["image"]][0]["value"],
                "assistant_target": annotations[row["image"]][1]["value"],
            }
        )
    summaries = []
    for seed, rows in sorted(episodes.items()):
        rows.sort(key=lambda r: r["t_sim_ns"])
        if any(b["t_sim_ns"] <= a["t_sim_ns"] for a, b in pairwise(rows)):
            raise ValueError(f"nonmonotonic timestamps in seed {seed}")
        summaries.append(
            {
                "seed": seed,
                "split": rows[0]["split"],
                "samples": len(rows),
                "first_saved_s": rows[0]["t_sim_ns"] / 1e9,
                "last_saved_s": rows[-1]["t_sim_ns"] / 1e9,
                "land_labels": sum(r["target"]["land"] for r in rows),
            }
        )
    payload = {"manifest": manifest, "summaries": summaries, "episodes": episodes}
    template = (
        Path(__file__).resolve().parents[1] / "src/uavlab/analysis/vla_dataset_viewer.html"
    ).read_text(encoding="utf-8")
    # Prevent source text from ending the script element; DOM writes use textContent.
    serialized = json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")
    destination.mkdir(parents=True, exist_ok=True)
    page = destination / "viewer.html"
    page.write_text(template.replace("__DATASET_JSON__", serialized), encoding="utf-8")
    summary = {
        "kind": "original_saved_dataset_camera_playback",
        "source_dataset": str(source),
        "index_sha256": hashlib.sha256((source / "index.jsonl").read_bytes()).hexdigest(),
        "manifest_sha256": audit["manifest_sha256"],
        "viewer_sha256": hashlib.sha256(page.read_bytes()).hexdigest(),
        "embedded_images_verified_byte_identical": len(index),
        "episodes": summaries,
        "audit": {k: v for k, v in audit.items() if k != "image_sha256"},
        "original_full_pose_and_control_logs_in_dataset": False,
        "new_simulations": 0,
        "model_predictions": 0,
        "training_runs": 0,
        "limits": [
            "Sparse camera samples; no interpolated or newly rendered images.",
            "Labels are converted C0 supervision, not original controls or model predictions.",
            "The coarse goal bearing is computed using simulator goal position.",
            "Single synthetic domain and instruction; no real-flight or external-simulator data.",
            "A fresh deterministic replay needs source-image matching before attribution.",
        ],
    }
    (destination / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.source, args.out)
    print(
        json.dumps(
            {
                "viewer": str(args.out / "viewer.html"),
                "verified_images": result["embedded_images_verified_byte_identical"],
                "episodes": len(result["episodes"]),
                "training_ready": result["audit"]["training_ready"],
            },
            indent=2,
        )
    )
