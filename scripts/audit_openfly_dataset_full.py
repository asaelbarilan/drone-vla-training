"""Audit all 110 pilot source routes without modifying the frozen dataset."""

import collections
import hashlib
import json
import math
import re
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_repair_20260918"
CACHE = Path("D:/drone_vla_pilot/data/openfly_train_pilot_20260917")
DATA = Path("D:/drone_vla_pilot/data/joint_openfly_local_20260917_v1")
SELECTION = json.loads((ROOT / "reports/vla_joint_openfly_20260917/selection.json").read_text())
NAMES = {"stop": 0, "go straight": 1, "turn left": 2, "turn right": 3, "go up": 4, "go down": 5}
EXPECTED = {
    1: (3, 0, 0, 0),
    2: (0, 0, 0, 30),
    3: (0, 0, 0, -30),
    4: (0, 0, 3, 0),
    5: (0, 0, -3, 0),
    8: (6, 0, 0, 0),
    9: (9, 0, 0, 0),
}


def delta(a, b):
    dx, dy, dz = [y - x for x, y in zip(a["pos"], b["pos"], strict=True)]
    yaw = a["yaw"]
    return (
        dx * math.cos(yaw) + dy * math.sin(yaw),
        -dx * math.sin(yaw) + dy * math.cos(yaw),
        dz,
        math.degrees((b["yaw"] - yaw + math.pi) % (2 * math.pi) - math.pi),
    )


def close(a, b):
    return max(abs(x - y) for x, y in zip(a, b, strict=True)) < 0.01


def main():
    issues, macros, routes = [], [], []
    counts = collections.Counter()
    repeated_inputs = collections.defaultdict(list)
    panel = list(
        map(
            json.loads,
            (ROOT / "reports/vla_openfly_same_panel_20260918/inputs.jsonl")
            .read_text()
            .splitlines(),
        )
    )
    samples = []
    for item in SELECTION["episodes"]:
        e = item["episode"]
        trajectory = e["image_path"]
        records = sorted(
            pq.read_table(CACHE / "traj" / (trajectory + ".parquet")).to_pylist(),
            key=lambda r: r["frame_index"],
        )
        counts["routes"] += 1
        counts["raw_frames"] += len(records)
        ids = {r["image_id"]: i for i, r in enumerate(records)}
        hashes = [hashlib.sha256(r["image"]["bytes"]).hexdigest() for r in records]
        assert [r["frame_index"] for r in records] == list(range(len(records)))
        bad = []
        for i, r in enumerate(records):
            a = NAMES.get(r["action_type"])
            counts["raw_action_" + str(a)] += 1
            key = (e["gpt_instruction"], tuple(hashes[max(0, i - 2 + k)] for k in range(3)))
            repeated_inputs[key].append((trajectory, i, a))
            if a == 0:
                counts["terminal_stop"] += i == len(records) - 1
                continue
            if (
                i + 1 >= len(records)
                or a not in EXPECTED
                or not close(delta(r, records[i + 1]), EXPECTED[a])
            ):
                bad.append(i)
                issues.append(
                    dict(
                        trajectory=trajectory,
                        frame=i,
                        action=a,
                        kind="raw_motion",
                        measured=delta(r, records[i + 1]) if i + 1 < len(records) else None,
                    )
                )
            else:
                counts["raw_motion_pass"] += 1
            if hashes[i] == hashes[i + 1] and not close(delta(r, records[i + 1]), (0, 0, 0, 0)):
                issues.append(
                    dict(
                        trajectory=trajectory, frame=i, action=a, kind="identical_image_with_motion"
                    )
                )
        annotation_ids = [ids[x] for x in e["index_list"]]
        assert len(annotation_ids) == len(e["action"])
        for j, (end, a) in enumerate(zip(annotation_ids, e["action"], strict=True)):
            counts["annotation_action_" + str(a)] += 1
            if a not in (8, 9):
                continue
            length = 2 if a == 8 else 3
            start = end - length + 1
            backward_ok = (
                start >= 0
                and end + 1 < len(records)
                and all(
                    records[k]["action_type"] == "go straight" and k not in bad
                    for k in range(start, end + 1)
                )
                and close(delta(records[start], records[end + 1]), EXPECTED[a])
            )
            forward_ok = (
                end + length < len(records)
                and all(
                    records[k]["action_type"] == "go straight" and k not in bad
                    for k in range(end, end + length)
                )
                and close(delta(records[end], records[end + length]), EXPECTED[a])
            )
            next_index = annotation_ids[j + 1] if j + 1 < len(annotation_ids) else None
            entry = dict(
                trajectory=trajectory,
                split=item["split"],
                annotation_index=j,
                annotation_frame=end,
                action_id=a,
                inferred_start=start,
                backward_window_matches=backward_ok,
                forward_window_matches=forward_ok,
                next_annotation_delta=delta(records[end], records[next_index])
                if next_index is not None
                else None,
            )
            macros.append(entry)
            if item["split"] == "val" and backward_ok and not forward_ok:
                # Keep a separately labelled diagnostic. Never silently relabel existing data.
                for variant, index in [("annotation_frame", end), ("verified_start", start)]:
                    history = [max(0, index - 2), max(0, index - 1), index]
                    paths = [
                        str(DATA / "frames" / trajectory / (records[k]["image_id"] + ".png"))
                        for k in history
                    ]
                    samples.append(
                        dict(
                            id=f"macro:{trajectory}:{j}:{variant}",
                            trajectory=trajectory,
                            frame_index=index,
                            variant=variant,
                            action_id=a,
                            instruction=e["gpt_instruction"],
                            images=paths,
                            image_sha256=[hashes[k] for k in history],
                            start_frame=start,
                            annotation_frame=end,
                            endpoint=end + 1,
                        )
                    )
        has_vertical = any(r["action_type"] in ("go up", "go down") for r in records)
        vertical_words = bool(
            re.search(
                r"\b(climb|ascend|descend|upward|downward|up|down|higher|lower|rise|rises|altitude|elevat\w*)\b",
                e["gpt_instruction"],
                re.I,
            )
        )
        routes.append(
            dict(
                trajectory=trajectory,
                split=item["split"],
                vertical_motion=has_vertical,
                vertical_words=vertical_words,
                instruction=e["gpt_instruction"],
                first_annotation_frame=annotation_ids[0],
                last_annotation_frame=annotation_ids[-1],
                frames=len(records),
            )
        )
    conflicts = [v for v in repeated_inputs.values() if len({x[2] for x in v}) > 1]
    frozen = list(map(json.loads, (DATA / "index.jsonl").read_text().splitlines()))
    hash_splits = collections.defaultdict(set)
    for row in frozen:
        if row["source"] == "openfly":
            hash_splits[row["image_sha256"][-1]].add(row["split"])
    # Fixed first 12 pairs in deterministic selection order; labels/poses never enter inputs.
    selected = samples[:24]
    assert len(selected) == 24
    (OUT / "macro_inputs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in selected))
    report = dict(
        counts=dict(counts),
        issues=issues,
        macro_total=len(macros),
        macro_backward_matches=sum(m["backward_window_matches"] for m in macros),
        macro_forward_matches=sum(m["forward_window_matches"] for m in macros),
        macro_backward_only=sum(
            m["backward_window_matches"] and not m["forward_window_matches"] for m in macros
        ),
        exact_input_conflicts=conflicts,
        train_val_identical_current_images=sum(len(s) > 1 for s in hash_splits.values()),
        vertical_routes=sum(r["vertical_motion"] for r in routes),
        vertical_routes_without_explicit_vertical_word=sum(
            r["vertical_motion"] and not r["vertical_words"] for r in routes
        ),
        routes=routes,
        macros=macros,
        original_panel_count=len(panel),
        macro_diagnostic_cases=len(selected),
    )
    (OUT / "full_data_audit.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("issues", "routes", "macros", "exact_input_conflicts")
            }
        )
    )


if __name__ == "__main__":
    main()
