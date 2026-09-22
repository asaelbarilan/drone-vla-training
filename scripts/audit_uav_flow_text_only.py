# ruff: noqa: E501
"""D153: how much of a UAV-Flow trajectory is predictable from the instruction alone?

The OpenFly panel failed this test badly: its 72 decisions shared only 21 route
instructions, and an oracle that ignored every image and answered the best single
action per route scored 36/72, far above any model. Before training on UAV-Flow we
ask the same question in its continuous form — predict each episode's trajectory
without ever looking at an image, using only the instruction text.

Two predictors, both leave-one-out so nothing is scored on itself:

  global : the mean trajectory of every other episode. Uses no text at all.
  text   : the mean trajectory of other episodes sharing the same unified
           instruction, falling back to global when the instruction is unique.

If `text` is much better than `global`, the instruction carries the answer and a
model can score well without grounding. If they are close, the text does not
determine the trajectory and vision has to do the work.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/uav_flow_text_only_20260921"
WAYPOINTS = 20
ROTATION_WORDS = ("spin", "rotate", "clockwise")


def resample(track, k=WAYPOINTS):
    """Resample a variable-length trajectory to k points on a normalised index."""
    a = np.asarray(track, dtype=float)
    src = np.linspace(0.0, 1.0, len(a))
    dst = np.linspace(0.0, 1.0, k)
    return np.stack([np.interp(dst, src, a[:, c]) for c in range(a.shape[1])], axis=1)


def load_episodes(path, limit=None):
    """One record per episode: the first frame's log holds the whole trajectory."""
    handle = pq.ParquetFile(path)
    seen, episodes = set(), []
    for group in range(handle.metadata.num_row_groups):
        table = handle.read_row_group(group, columns=["id", "log"])
        for episode_id, blob in zip(
            table.column("id").to_pylist(), table.column("log").to_pylist(), strict=True
        ):
            if episode_id in seen:
                continue
            seen.add(episode_id)
            log = json.loads(blob)
            track = log.get("preprocessed_logs")
            if not track or len(track) < 2:
                continue
            episodes.append(
                dict(
                    id=episode_id,
                    instruction=log["instruction_unified"].strip().lower(),
                    raw_instruction=log["instruction"],
                    steps=len(track),
                    track=resample(track),
                )
            )
        if limit and len(episodes) >= limit:
            break
    return episodes


def errors(truth, predicted):
    """Final-position error and mean waypoint error, translation channels only."""
    final = float(np.linalg.norm(truth[-1, :3] - predicted[-1, :3]))
    waypoint = float(np.mean(np.linalg.norm(truth[:, :3] - predicted[:, :3], axis=1)))
    return final, waypoint


def summarise(name, pairs):
    final = np.array([p[0] for p in pairs])
    waypoint = np.array([p[1] for p in pairs])
    return dict(
        predictor=name,
        n=len(pairs),
        final_error_median=round(float(np.median(final)), 3),
        final_error_mean=round(float(final.mean()), 3),
        waypoint_error_median=round(float(np.median(waypoint)), 3),
        waypoint_error_mean=round(float(waypoint.mean()), 3),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--shard",
        default="D:/drone_vla_pilot/data/uav_flow_20260921/train-00000-of-00054.parquet",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    episodes = load_episodes(args.shard, args.limit)
    tracks = np.stack([e["track"] for e in episodes])
    total = tracks.sum(axis=0)
    n = len(episodes)
    print(f"episodes: {n}")

    by_instruction = defaultdict(list)
    for i, e in enumerate(episodes):
        by_instruction[e["instruction"]].append(i)
    sizes = Counter(len(v) for v in by_instruction.values())
    with_sibling = sum(len(v) for v in by_instruction.values() if len(v) > 1)
    print(
        f"distinct instructions: {len(by_instruction)}; "
        f"episodes sharing an instruction with at least one other: {with_sibling}"
    )

    global_pairs, text_pairs, sibling_pairs = [], [], []
    for i, e in enumerate(episodes):
        truth = e["track"]
        global_mean = (total - truth) / (n - 1)
        global_pairs.append(errors(truth, global_mean))

        group = by_instruction[e["instruction"]]
        if len(group) > 1:
            others = np.stack([episodes[j]["track"] for j in group if j != i])
            text_mean = others.mean(axis=0)
            text_pairs.append(errors(truth, text_mean))
            sibling_pairs.append(global_pairs[-1])
        else:
            text_pairs.append(global_pairs[-1])

    report = dict(
        shard=str(args.shard),
        episodes=n,
        waypoints=WAYPOINTS,
        distinct_instructions=len(by_instruction),
        episodes_with_instruction_sibling=with_sibling,
        instruction_group_sizes=dict(sorted(sizes.items())),
        units="metres for the three translation channels; rotation channels excluded from the error",
        all_episodes=[summarise("global (no text)", global_pairs), summarise("text", text_pairs)],
        episodes_with_siblings_only=[
            summarise("global (no text)", sibling_pairs),
            summarise(
                "text",
                [
                    text_pairs[i]
                    for i, e in enumerate(episodes)
                    if len(by_instruction[e["instruction"]]) > 1
                ],
            ),
        ],
        rotation_only_episodes=sum(
            any(w in e["instruction"] for w in ROTATION_WORDS) for e in episodes
        ),
        track_extent_metres=dict(
            median_final_distance=round(
                float(np.median(np.linalg.norm(tracks[:, -1, :3], axis=1))), 3
            ),
            max_final_distance=round(float(np.max(np.linalg.norm(tracks[:, -1, :3], axis=1))), 3),
        ),
    )
    (OUT / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
