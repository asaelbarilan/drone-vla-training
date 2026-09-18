"""D146 independent frozen-panel source identity, motion and annotation audit."""

import hashlib
import json
import math
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_forensics_20260918"
CACHE = Path("D:/drone_vla_pilot/data/openfly_train_pilot_20260917")
rows = list(
    map(
        json.loads,
        (ROOT / "reports/vla_openfly_same_panel_20260918/inputs.jsonl").read_text().splitlines(),
    )
)
annotations = {
    e["image_path"]: e for e in json.loads((CACHE / "Annotation/train.json").read_text())
}
names = {"stop": 0, "go straight": 1, "turn left": 2, "turn right": 3, "go up": 4, "go down": 5}
expected = {1: (3, 0, 0, 0), 2: (0, 0, 0, 30), 3: (0, 0, 0, -30), 4: (0, 0, 3, 0), 5: (0, 0, -3, 0)}
records = {}
results = []
for row in rows:
    trajectory = row["trajectory"]
    i = row["frame_index"]
    target = row["action_id"]
    if trajectory not in records:
        records[trajectory] = sorted(
            pq.read_table(CACHE / "traj" / (trajectory + ".parquet")).to_pylist(),
            key=lambda r: r["frame_index"],
        )
    raw = records[trajectory]
    r = raw[i]
    annotation = annotations[trajectory]
    assert names[r["action_type"]] == target
    history = [max(0, i - 2), max(0, i - 1), i]
    assert [hashlib.sha256(raw[j]["image"]["bytes"]).hexdigest() for j in history] == row[
        "image_sha256"
    ]
    assert [Path(p).stem for p in row["images"]] == [raw[j]["image_id"] for j in history]
    error = None
    if target:
        nxt = raw[i + 1]
        dx, dy, dz = [b - a for a, b in zip(r["pos"], nxt["pos"], strict=True)]
        dyaw = math.degrees((nxt["yaw"] - r["yaw"] + math.pi) % (2 * math.pi) - math.pi)
        measured = (
            dx * math.cos(r["yaw"]) + dy * math.sin(r["yaw"]),
            -dx * math.sin(r["yaw"]) + dy * math.cos(r["yaw"]),
            dz,
            dyaw,
        )
        error = max(abs(a - b) for a, b in zip(measured, expected[target], strict=True))
        assert error < 0.01
    else:
        assert (
            i == len(raw) - 1
            and annotation["action"][-1] == 0
            and annotation["index_list"][-1] == r["image_id"]
        )
    indices = [
        j for j, image_id in enumerate(annotation["index_list"]) if image_id == r["image_id"]
    ]
    labels = [annotation["action"][j] for j in indices]
    results.append(
        dict(
            id=row["id"],
            target=target,
            motion_error=error,
            annotation_ids=labels,
            annotation_direction_match=any((1 if x in (8, 9) else x) == target for x in labels),
            previous_raw_action=names.get(raw[max(0, i - 1)]["action_type"]),
            next_raw_action=names.get(raw[min(len(raw) - 1, i + 1)]["action_type"]),
        )
    )
report = dict(
    n=len(results),
    trajectories=len(records),
    image_identity_pass=72,
    next_motion_pass=sum(x["motion_error"] is not None for x in results),
    terminal_annotation_pass=sum(x["target"] == 0 for x in results),
    present_in_compressed_annotations=sum(bool(x["annotation_ids"]) for x in results),
    annotation_direction_agreement=sum(x["annotation_direction_match"] for x in results),
    cases=results,
)
(OUT / "label_audit.json").write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k != "cases"}))
