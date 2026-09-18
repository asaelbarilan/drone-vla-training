"""Audit all pinned TRAIN tags and episode phases without fetching image shards."""

import collections
import json
import math
from pathlib import Path

from uavlab.training.openfly_annotations import annotation_contract

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_repair_20260918"


def main():
    rows = json.loads(
        Path(
            "D:/drone_vla_pilot/data/openfly_train_pilot_20260917/Annotation/train.json"
        ).read_text()
    )
    for episode in rows:
        annotation_contract(episode)
    counts = collections.Counter(a for r in rows for a in r["action"])
    unsupported = [r for r in rows if any(a not in range(10) for a in r["action"])]
    mismatch = [r["image_path"] for r in rows if len(r["action"]) != len(r["index_list"])]
    report = dict(
        routes=len(rows),
        action_counts=dict(counts),
        unsupported_action_routes=len(unsupported),
        unsupported_examples=[r["image_path"] for r in unsupported[:10]],
        action_image_length_mismatch_routes=len(mismatch),
        mismatch_examples=mismatch[:10],
        empty_instructions=sum(not str(r.get("gpt_instruction", "")).strip() for r in rows),
        duplicate_route_ids=len(rows) - len({r["image_path"] for r in rows}),
        scope="All pinned TRAIN annotations; full-image/pose audit limited to110 pilot routes",
    )
    stats = collections.Counter()
    phases = collections.Counter()
    deltas = collections.defaultdict(collections.Counter)
    contracts = [annotation_contract(r) for r in unsupported]
    distances = [math.dist(c["navigation_goal_xyz"], c["last_recorded_xyz"]) for c in contracts]
    conflict = dict(
        phase_routes=len(unsupported),
        recorded_stop_over_20m_from_last_position=sum(d > 20 for d in distances),
        min_distance=min(distances),
        max_distance=max(distances),
        all_position_dimensions=dict(collections.Counter(len(p) for r in rows for p in r["pos"])),
        phase_contracts_validated=len(contracts),
        all_episode_schemas_validated=len(rows),
    )
    (OUT / "stop_phase_conflict.json").write_text(json.dumps(conflict, indent=2))
    for r in unsupported:
        acts = r["action"]
        prefix = 0
        while prefix < len(acts) and acts[prefix] == -1:
            prefix += 1
        tail = len(acts) - 2 if acts[-1] == 0 else len(acts) - 1
        while tail >= 0 and acts[tail] == -2:
            tail -= 1
        stop = acts.index(0)
        phases["stop_at_end" if stop == len(acts) - 1 else "stop_before_trailing_phase"] += 1
        if stop < len(acts) - 1 and set(acts[stop + 1 :]) == {-2}:
            phases["only_minus2_after_stop"] += 1
        for i, a in enumerate(acts):
            if a not in (-1, -2):
                continue
            stats[str(a) + "_count"] += 1
            if a == -1 and i < prefix:
                stats["-1_in_initial_run"] += 1
            if a == -2 and i > tail:
                stats["-2_in_final_run"] += 1
            if i + 1 < len(acts):
                d = tuple(
                    round(y - x, 3)
                    for x, y in zip(r["pos"][i][:3], r["pos"][i + 1][:3], strict=True)
                )
                deltas[str(a)][d] += 1
    negative = dict(
        counts=dict(stats),
        motion_deltas={
            k: [dict(delta=list(d), count=n) for d, n in c.most_common(8)]
            for k, c in deltas.items()
        },
    )
    phase = dict(
        routes=len(unsupported),
        counts=dict(phases),
        position_dimensions=dict(collections.Counter(len(r["pos"][0]) for r in rows)),
        examples=[
            dict(trajectory=r["image_path"], actions=r["action"], instruction=r["gpt_instruction"])
            for r in unsupported[:2]
        ],
    )
    for name, value in [
        ("all_annotation_audit", report),
        ("negative_tag_audit", negative),
        ("phase_audit", phase),
    ]:
        (OUT / (name + ".json")).write_text(json.dumps(value, indent=2))
    print(
        json.dumps(
            dict(
                routes=len(rows),
                unsupported_routes=len(unsupported),
                phase_counts=dict(phases),
                negative_counts=dict(stats),
            )
        )
    )


if __name__ == "__main__":
    main()
