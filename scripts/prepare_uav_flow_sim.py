"""D165: add UAV-Flow-Sim flights to an official-format store (training only).

The D164 closed-loop gap points at a domain gap: the adapter was trained on real
flights only and flown in the simulator. UAV-Flow-Sim (wangxiangyu0814/UAV-Flow-Sim,
21 shards, 10,109 flights) is recorded in the same simulator and the same format.

Processing is the official uav_dataset.py maths (process_episode from
prepare_uav_flow_official) after one change: the simulator logs are in
centimetres, the real logs and our action statistics in metres, so x, y, z of
both raw_logs and preprocessed_logs are divided by 100 first (yaw is degrees in
both). Every simulator flight goes to training; validation stays the real unseen
split. Flights whose start lies within 0.5 m of any UAV-Flow-Eval test task start
are excluded (168 flights, list in --exclude) so no test trajectory can leak.

Rows are appended to the store's episodes.jsonl (a copy of the original is kept)
with site "sim" and source "sim"; frames go to frames/sim_<id>/. The action
statistics are NOT recomputed: the adapter continues from a checkpoint whose
token meaning depends on them. The share of simulator steps outside the range is
reported instead.
"""

import argparse
import io
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from prepare_uav_flow_official import (
    JPEG_QUALITY,
    REPEAT,
    STORE,
    THUMB,
    process_episode,
    shard_images,
    shard_logs,
)


def to_metres(log):
    out = dict(log)
    for key in ("raw_logs", "preprocessed_logs"):
        rows = np.array(log[key], dtype=float)
        rows[:, :3] /= 100.0
        out[key] = rows.tolist()
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", nargs="+", required=True)
    parser.add_argument("--exclude", type=Path, required=True, help="JSON list of flight ids")
    parser.add_argument("--manifest", type=Path, required=True, help="store manifest (stats)")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    excluded = set(json.loads(args.exclude.read_text(encoding="utf-8")))
    stats = json.loads(args.manifest.read_text(encoding="utf-8"))["action_stats_train"]
    low, high = np.array(stats["q01"]), np.array(stats["q99"])
    episodes_path = STORE / "episodes.jsonl"
    backup = STORE / "episodes.real_only.jsonl"
    if not backup.exists():
        shutil.copy(episodes_path, backup)
    frames_dir = STORE / "frames"

    def write_frame(job):
        path, blob = job
        if not path.exists():
            picture = Image.open(io.BytesIO(blob)).convert("RGB")
            picture.thumbnail((THUMB, THUMB))
            picture.save(path, quality=JPEG_QUALITY)

    rows, clipped, total, skipped = [], 0, 0, 0
    for shard in args.shard:
        logs, counts = shard_logs(shard)
        keep = {}
        for episode_id, log in logs.items():
            track = log.get("preprocessed_logs")
            if episode_id in excluded or not track or len(track) < 2:
                skipped += 1
                continue
            order = sorted(counts[episode_id])
            if min(len(order), len(track)) < 2:
                skipped += 1
                continue
            keep[episode_id] = order
        with ThreadPoolExecutor(args.workers) as pool:
            jobs = []
            for episode_id, index, blob in shard_images(shard, set(keep)):
                folder = frames_dir / f"sim_{episode_id}"
                folder.mkdir(exist_ok=True)
                jobs.append((folder / f"{index:05d}.jpg", blob))
                if len(jobs) >= 512:
                    list(pool.map(write_frame, jobs))
                    jobs = []
            list(pool.map(write_frame, jobs))
        for episode_id, order in keep.items():
            log = to_metres(logs[episode_id])
            actions, proprio = process_episode(log)
            n = min(len(order), len(actions))
            moves = actions[: n - 1]
            clipped += int(((moves < low) | (moves > high)).any(axis=1).sum())
            total += len(moves)
            folder = frames_dir / f"sim_{episode_id}"
            rows.append(
                dict(
                    episode=f"sim_{episode_id}",
                    site="sim",
                    source="sim",
                    split_unseen="train",
                    instruction=log["instruction"].strip(),
                    instruction_unified=log["instruction_unified"].strip(),
                    images=[str(folder / f"{order[i]:05d}.jpg") for i in range(n)],
                    actions=[[round(float(v), 6) for v in a] for a in actions[:n]],
                    proprio=[[round(float(v), 6) for v in p] for p in proprio[:n]],
                    endpoint_start_frame=[round(float(v), 4) for v in proprio[n - 1][:3]],
                )
            )
        print(f"{shard}: kept {len(keep)} flights, total {len(rows)}", flush=True)

    with open(episodes_path, "a", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row) + "\n")
    report = dict(
        sim_flights_added=len(rows),
        sim_flights_skipped=skipped,
        sim_frames=sum(len(r["actions"]) for r in rows),
        sim_samples_with_oversampling=sum(len(r["actions"]) + 2 * REPEAT for r in rows),
        sim_steps_outside_action_range=round(clipped / max(total, 1), 4),
        units="simulator centimetres divided by 100 to metres (x, y, z); yaw unchanged",
        excluded_list=str(args.exclude),
    )
    (STORE / "sim_added.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
