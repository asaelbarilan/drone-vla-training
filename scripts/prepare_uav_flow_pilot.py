"""D153: freeze a UAV-Flow pilot split and its text-only baseline.

Pilot task, deliberately reduced: given the first frame of an episode and the
instruction, predict where the drone ends up — the final displacement in metres,
in the start frame. That is exactly the quantity the text-only audit measured, so
a trained model and the no-vision baseline are scored on the same number.

The split is by episode, hashed from the episode id so it is stable and does not
depend on row order. The baseline is recomputed here on the validation episodes
using only training episodes as reference, which is the honest comparison; the
leave-one-out figure in the earlier audit used the whole shard.
"""

import argparse
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/uav_flow_pilot_20260921"
STORE = Path("D:/drone_vla_pilot/data/uav_flow_pilot_20260921")
VAL_FRACTION = 0.2
THUMB = 256


def shard_prefix(path, size=1 << 20):
    """Hash only the first megabyte; the shard itself is several gigabytes."""
    with open(path, "rb") as handle:
        return handle.read(size)


def split_for(episode_id):
    digest = hashlib.sha256(episode_id.encode("utf-8")).digest()
    return "val" if int.from_bytes(digest[:4], "big") / 2**32 < VAL_FRACTION else "train"


def build(shard):
    """One record per episode: first frame, instruction, final displacement."""
    handle = pq.ParquetFile(shard)
    frames = STORE / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    seen, rows = set(), []
    for group in range(handle.metadata.num_row_groups):
        table = handle.read_row_group(group, columns=["id", "frame_idx", "image", "log"])
        for episode_id, frame_idx, image, blob in zip(
            table.column("id").to_pylist(),
            table.column("frame_idx").to_pylist(),
            table.column("image").to_pylist(),
            table.column("log").to_pylist(),
            strict=True,
        ):
            if episode_id in seen or frame_idx != 0:
                continue
            log = json.loads(blob)
            track = log.get("preprocessed_logs")
            if not track or len(track) < 2:
                continue
            seen.add(episode_id)
            path = frames / f"{episode_id}.png"
            picture = Image.open(io.BytesIO(image["bytes"])).convert("RGB")
            picture.thumbnail((THUMB, THUMB))
            picture.save(path)
            end = [round(float(v), 4) for v in track[-1][:3]]
            rows.append(
                dict(
                    id=episode_id,
                    split=split_for(episode_id),
                    instruction=log["instruction_unified"].strip(),
                    instruction_raw=log["instruction"].strip(),
                    steps=len(track),
                    image=str(path),
                    image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    endpoint_m=end,
                    distance_m=round(float(np.linalg.norm(end)), 4),
                )
            )
    return rows


def baseline(rows):
    """Predict a validation endpoint without any image, from the training set only."""
    train = [r for r in rows if r["split"] == "train"]
    val = [r for r in rows if r["split"] == "val"]
    key = lambda r: r["instruction"].lower()  # noqa: E731
    groups = defaultdict(list)
    for r in train:
        groups[key(r)].append(np.array(r["endpoint_m"]))
    overall = np.mean([np.array(r["endpoint_m"]) for r in train], axis=0)

    global_errors, text_errors, matched = [], [], 0
    for r in val:
        truth = np.array(r["endpoint_m"])
        global_errors.append(float(np.linalg.norm(truth - overall)))
        group = groups.get(key(r))
        if group:
            matched += 1
            text_errors.append(float(np.linalg.norm(truth - np.mean(group, axis=0))))
        else:
            text_errors.append(global_errors[-1])
    return dict(
        train_episodes=len(train),
        val_episodes=len(val),
        val_with_instruction_seen_in_train=matched,
        median_trajectory_m=round(float(np.median([r["distance_m"] for r in val])), 3),
        global_no_text=dict(
            median_final_error_m=round(float(np.median(global_errors)), 3),
            mean_final_error_m=round(float(np.mean(global_errors)), 3),
        ),
        text_only=dict(
            median_final_error_m=round(float(np.median(text_errors)), 3),
            mean_final_error_m=round(float(np.mean(text_errors)), 3),
        ),
        target_to_beat_m=round(float(np.median(text_errors)), 3),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--shard",
        default="D:/drone_vla_pilot/data/uav_flow_20260921/train-00000-of-00054.parquet",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    STORE.mkdir(parents=True, exist_ok=True)

    rows = build(args.shard)
    index = STORE / "index.jsonl"
    index.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    stats = baseline(rows)
    manifest = dict(
        source_shard=str(args.shard),
        source_sha256_prefix=hashlib.sha256(shard_prefix(args.shard)).hexdigest(),
        episodes=len(rows),
        index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
        val_fraction=VAL_FRACTION,
        thumbnail_px=THUMB,
        task="first frame + instruction -> final displacement (x, y, z) in metres, start frame",
        baseline=stats,
    )
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
