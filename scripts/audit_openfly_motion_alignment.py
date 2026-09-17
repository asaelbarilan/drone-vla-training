"""Compare released compressed labels and raw consecutive-frame motion."""

import collections
import json
import math
from itertools import pairwise
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path("D:/drone_vla_pilot/data/openfly_train_pilot_20260917")
OUT = Path("reports/vla_openfly_train_20260917")
selection = json.loads((OUT / "selection.json").read_text())
raw_stats, compressed_stats = (
    collections.defaultdict(collections.Counter),
    collections.defaultdict(collections.Counter),
)
anomalies = []


def delta(a, b):
    d = [y - x for x, y in zip(a["pos"], b["pos"], strict=True)]
    yaw = (b["yaw"] - a["yaw"] + math.pi) % (2 * math.pi) - math.pi
    return tuple(round(v, 3) for v in (math.hypot(*d[:2]), d[2], math.degrees(yaw)))


expected = {
    "go straight": (3.0, 0.0, 0.0),
    "turn left": (0.0, 0.0, 30.0),
    "turn right": (0.0, 0.0, -30.0),
    "go up": (0.0, 3.0, 0.0),
    "go down": (0.0, -3.0, 0.0),
}
for item in selection["episodes"]:
    episode = item["episode"]
    records = pq.read_table(ROOT / "traj" / (episode["image_path"] + ".parquet")).to_pylist()
    records.sort(key=lambda r: r["frame_index"])
    for a, b in pairwise(records):
        observed = delta(a, b)
        raw_stats[a["action_type"]][observed] += 1
        if a["action_type"] not in expected or observed != expected[a["action_type"]]:
            anomalies.append(
                dict(
                    trajectory=episode["image_path"],
                    split=item["split"],
                    image=a["image_id"],
                    action=a["action_type"],
                    observed=observed,
                )
            )
    by = {r["image_id"]: r for r in records}
    for i in range(len(episode["action"]) - 1):
        observed = delta(by[episode["index_list"][i]], by[episode["index_list"][i + 1]])
        compressed_stats[str(episode["action"][i])][observed] += 1


def serialize(stats):
    return {
        action: [
            dict(xy_distance=d[0], z_delta=d[1], yaw_delta_deg=d[2], count=n)
            for d, n in counter.most_common()
        ]
        for action, counter in stats.items()
    }


report = dict(
    raw_consecutive_transitions=sum(sum(c.values()) for c in raw_stats.values()),
    raw_consecutive_motion=serialize(raw_stats),
    raw_anomalies=anomalies,
    compressed_annotation_motion=serialize(compressed_stats),
    conclusion=(
        "Raw frames largely align with their next atomic action. Compressed annotation images "
        "do not define uniform primitive endpoints: e.g. all22 action8 next-image gaps are3 "
        "source units although the released primitive dictionary says forward6. Turns can "
        "include subsequent translation before the next selected image. Do not derive "
        "velocity/duration targets or roll out native IDs from these gaps. The frozen native-ID "
        "pilot imitates released labels only, not verified continuous control. One raw turn "
        "has no measured yaw change; preserve and flag it, no retrospective split changes."
    ),
)
(OUT / "motion_alignment_audit.json").write_text(json.dumps(report, indent=2))
print(json.dumps(dict(raw_transitions=report["raw_consecutive_transitions"], anomalies=anomalies)))
