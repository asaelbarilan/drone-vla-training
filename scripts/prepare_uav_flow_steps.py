"""D154: per-frame next-step 6-DoF dataset from a UAV-Flow shard.

The D153 pilot predicted only an episode endpoint, three numbers from one frame.
That was a reduction I chose to match an already-computed baseline; it is not the
shape UAV-Flow is modelled with, and it left 412 training examples.

Here every frame is an example: current frame plus instruction, predict the
6-DoF step to the next frame. Steps are expressed in the episode's start frame,
the same frame `preprocessed_logs` uses, so a rollout is the running sum of the
predicted steps and its endpoint is directly comparable to the D153 baselines.
Body-frame actions would need the dataset's rotation convention, which is not
documented in the card and is not guessed at here.

The episode split is the same hash of the episode id as D153, so no validation
episode has leaked into training between the two runs.
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
OUT = ROOT / "reports/uav_flow_steps_20260921"
STORE = Path("D:/drone_vla_pilot/data/uav_flow_steps_20260921")
VAL_FRACTION = 0.2
THUMB = 256
JPEG_QUALITY = 92


def split_for(episode_id):
    digest = hashlib.sha256(episode_id.encode("utf-8")).digest()
    return "val" if int.from_bytes(digest[:4], "big") / 2**32 < VAL_FRACTION else "train"


def collect(shard):
    """Group each episode's frames and its trajectory, in frame order."""
    handle = pq.ParquetFile(shard)
    frames, logs = defaultdict(dict), {}
    for group in range(handle.metadata.num_row_groups):
        table = handle.read_row_group(group, columns=["id", "frame_idx", "image", "log"])
        for episode_id, frame_idx, image, blob in zip(
            table.column("id").to_pylist(),
            table.column("frame_idx").to_pylist(),
            table.column("image").to_pylist(),
            table.column("log").to_pylist(),
            strict=True,
        ):
            frames[episode_id][frame_idx] = image["bytes"]
            if episode_id not in logs:
                logs[episode_id] = json.loads(blob)
    return frames, logs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--shard",
        default="D:/drone_vla_pilot/data/uav_flow_20260921/train-00000-of-00054.parquet",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    picture_dir = STORE / "frames"
    picture_dir.mkdir(parents=True, exist_ok=True)

    frames, logs = collect(args.shard)
    rows, episodes, dropped = [], [], 0
    for episode_id, by_index in frames.items():
        log = logs[episode_id]
        track = log.get("preprocessed_logs")
        if not track or len(track) < 2:
            dropped += 1
            continue
        order = sorted(by_index)
        # Frame count and log length are close but not guaranteed equal; the
        # shorter one bounds how many steps can be paired with an observation.
        usable = min(len(order), len(track))
        if usable < 2:
            dropped += 1
            continue
        pose = np.asarray(track[:usable], dtype=float)
        deltas = np.diff(pose, axis=0)
        split = split_for(episode_id)
        folder = picture_dir / episode_id
        folder.mkdir(exist_ok=True)
        instruction = log["instruction_unified"].strip()
        for k in range(usable - 1):
            path = folder / f"{order[k]:05d}.jpg"
            if not path.exists():
                picture = Image.open(io.BytesIO(by_index[order[k]])).convert("RGB")
                picture.thumbnail((THUMB, THUMB))
                picture.save(path, quality=JPEG_QUALITY)
            rows.append(
                dict(
                    id=f"{episode_id}:{order[k]:05d}",
                    episode=episode_id,
                    split=split,
                    step=k,
                    steps_in_episode=usable - 1,
                    instruction=instruction,
                    image=str(path),
                    delta_6dof=[round(float(v), 4) for v in deltas[k]],
                )
            )
        episodes.append(
            dict(
                episode=episode_id,
                split=split,
                instruction=instruction,
                steps=usable - 1,
                endpoint_m=[round(float(v), 4) for v in pose[-1][:3]],
                frames=[str(folder / f"{i:05d}.jpg") for i in order[: usable - 1]],
            )
        )

    index = STORE / "steps.jsonl"
    index.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    episode_index = STORE / "episodes.jsonl"
    episode_index.write_text("".join(json.dumps(e) + "\n" for e in episodes), encoding="utf-8")

    train = [r for r in rows if r["split"] == "train"]
    val_eps = [e for e in episodes if e["split"] == "val"]
    scale = np.abs(np.array([r["delta_6dof"] for r in train]))
    manifest = dict(
        source_shard=str(args.shard),
        episodes=len(episodes),
        dropped_episodes=dropped,
        steps=len(rows),
        train_steps=len(train),
        val_steps=len(rows) - len(train),
        val_episodes=len(val_eps),
        steps_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
        episodes_sha256=hashlib.sha256(episode_index.read_bytes()).hexdigest(),
        val_fraction=VAL_FRACTION,
        thumbnail_px=THUMB,
        jpeg_quality=JPEG_QUALITY,
        task="current frame + instruction -> next 6-DoF step in the episode start frame",
        rollout="sum of predicted steps from frame 0; endpoint compared to the recorded endpoint",
        step_magnitude=dict(
            median_abs=[round(float(v), 4) for v in np.median(scale, axis=0)],
            p99_abs=[round(float(v), 4) for v in np.percentile(scale, 99, axis=0)],
        ),
        d153_baselines_metres=dict(no_text=5.786, text_only=2.264, median_trajectory=7.342),
    )
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
