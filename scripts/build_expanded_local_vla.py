"""D138 additive local collection, independent replay audits, and balanced schedules."""

import argparse
import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path

from audit_direct_vla_fixture import audit as audit_coordinate
from audit_visual_yaw_fixture import audit as audit_visual

from uavlab.training import direct_vla_contract as flu
from uavlab.training import direct_vla_frd as frd
from uavlab.training.direct_vla_fixture import KINDS, record, write_json
from uavlab.training.mixed_batches import balanced_schedule, task_class
from uavlab.training.visual_yaw_fixture import collect as collect_visual

OLD = Path("D:/drone_vla_pilot/data/local_mixed_20260917_v1")
OLD_SHA = "0738e416de4a8cc905af67d8b310ab8817a4138ab681a7c473639717e377aef1"


def read_rows(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def build(root, reports):
    root.mkdir(parents=True, exist_ok=False)
    reports.mkdir(parents=True, exist_ok=False)
    assert sha(OLD / "index.jsonl") == OLD_SHA
    coordinate = root / "coordinate_source_flu"
    coordinate.mkdir()
    rows, episodes = [], []
    settings = [(0, 0), (20, 1.5), (20, -1.5), (40, 1.5), (30, -1.5)]
    for seed in range(1450, 1470):
        ticks, rate = settings[((seed - 1450) // 4) % len(settings)]
        folder, samples, result = await record(
            coordinate, seed, ticks, rate, goal_distance_m=[4.0, 8.0, 12.0, 16.0][(seed - 1450) % 4]
        )
        assert result["success"], result
        rows.extend(samples)
        episodes.append({"run": folder.relative_to(coordinate).as_posix(), **result})
    (coordinate / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    for split in ("train", "val"):
        swift = [
            dict(
                images=[r["images"]["mosaic"]],
                messages=[
                    dict(role="user", content="<image>\n" + r["prompt"]),
                    dict(role="assistant", content=json.dumps(r["target"], separators=(",", ":"))),
                ],
            )
            for r in rows
            if r["split"] == split
        ]
        (coordinate / f"{split}_swift.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in swift), encoding="utf-8"
        )
    write_json(
        coordinate / "manifest.json",
        dict(
            contract=flu.CONTRACT_ID,
            seeds=list(range(1450, 1470)),
            episodes=episodes,
            samples=len(rows),
            samples_by_split=dict(Counter(r["split"] for r in rows)),
            purpose=KINDS,
        ),
    )
    coord_report = reports / "coordinate"
    coord_report.mkdir()
    coord_audit = await audit_coordinate(coordinate, coord_report)
    write_json(reports / "coordinate_raw_audit.json", coord_audit)
    visual = root / "visual"
    await collect_visual(
        visual, range(1500, 1540), (10, 18), (0.15, 0.50), visibility_preflight=True
    )
    visual_audit = await audit_visual(visual, range(1500, 1540))
    write_json(reports / "visual_audit.json", visual_audit)
    old_rows = read_rows(OLD / "index.jsonl")
    merged = list(old_rows)
    for row in rows:
        old_target = flu.parse_target(json.dumps(row["target"]))
        target = frd.from_flu(old_target)
        assert frd.action_from_target(
            target, row["state"]["yaw_enu_rad"], duration_s=0.2
        ) == flu.action_from_target(old_target, row["state"]["yaw_enu_rad"], duration_s=0.2)
        merged.append(
            {
                **row,
                "target": json.loads(frd.target_json(target)),
                "source_target_flu": row["target"],
                "contract": frd.CONTRACT_ID,
                "prompt": frd.student_prompt(row["instruction"], row["state"]),
                "data_root": str(coordinate),
                "task_group": "coordinate",
            }
        )
    for r in read_rows(visual / "index.jsonl"):
        merged.append(
            {
                **r,
                "data_root": str(visual),
                "task_group": "visual",
                "decision_id": f"visible_yaw_s{r['seed']}_l{r['layout']}_{r['instruction_colour']}",
            }
        )
    assert len({r["decision_id"] for r in merged}) == len(merged)
    # Preserve all original rows. Exclude only new rows whose exact rendered
    # mosaic conflicts with an original opposite split; then reserve remaining
    # new validation images before admitting new training images.
    original_splits = {}
    for r in old_rows:
        original_splits.setdefault(r["image_sha256"]["mosaic"], set()).add(r["split"])
    admitted, excluded = [], []
    for r in merged[len(old_rows) :]:
        if original_splits.get(r["image_sha256"]["mosaic"], {r["split"]}) != {r["split"]}:
            excluded.append(
                dict(decision_id=r["decision_id"], reason="original opposite split image")
            )
        else:
            admitted.append(r)
    val_hashes = {r["image_sha256"]["mosaic"] for r in admitted if r["split"] == "val"}
    merged = list(old_rows)
    for r in admitted:
        if r["split"] == "train" and r["image_sha256"]["mosaic"] in val_hashes:
            excluded.append(dict(decision_id=r["decision_id"], reason="new validation image"))
        else:
            merged.append(r)
    write_json(reports / "excluded_rows.json", excluded)
    split_images = {}
    for r in merged:
        assert r["seed"] not in set(range(1, 41)) | set(range(1060, 1065))
        assert r["split"] == ("val" if r["seed"] % 5 == 0 else "train")
        assert r["prompt"] == frd.student_prompt(r["instruction"], r["state"])
        assert sha(Path(r["data_root"]) / r["images"]["mosaic"]) == r["image_sha256"]["mosaic"]
        split_images.setdefault(r["image_sha256"]["mosaic"], set()).add(r["split"])
    assert all(len(x) == 1 for x in split_images.values())
    assert merged[: len(old_rows)] == old_rows
    (root / "index.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in merged), encoding="utf-8"
    )
    old_manifest = json.loads((OLD / "manifest.json").read_text())
    schedules = {
        "existing_control": balanced_schedule(old_rows, 400),
        "expanded": balanced_schedule(merged, 400),
    }
    by_id = {r["decision_id"]: r for r in merged}
    exposure = {
        name: dict(Counter(task_class(by_id[k]) for batch in schedule for k in batch))
        for name, schedule in schedules.items()
    }
    manifest = dict(
        contract=frd.CONTRACT_ID,
        index_sha256=sha(root / "index.jsonl"),
        original_index_sha256=OLD_SHA,
        original_validation_rows_unchanged=84,
        generation_eval_ids=old_manifest["generation_eval_ids"],
        sources=[str(OLD), str(coordinate), str(visual)],
        samples=len(merged),
        excluded_new_rows=len(excluded),
        counts=dict(Counter(r["split"] + "/" + task_class(r) for r in merged)),
        scene_groups=dict(
            Counter(split for split, seed in set((r["split"], r["seed"]) for r in merged))
        ),
        schedules=schedules,
        exposures=exposure,
        effective_batch_size=4,
        microbatch_size=1,
        planned_updates=400,
        planned_sample_exposures=1600,
        cross_split_duplicate_images=0,
        coordinate_action_equivalence_checks=len(rows),
        training_started=False,
        external_rows=0,
        real_world_rows=0,
        limits=(
            "Local same-renderer diagnostic; no obstacle avoidance, "
            "external-domain or real-flight coverage"
        ),
    )
    write_json(root / "manifest.json", manifest)
    write_json(reports / "data_audit.json", {k: v for k, v in manifest.items() if k != "schedules"})
    assert sha(OLD / "index.jsonl") == OLD_SHA
    print(json.dumps({k: v for k, v in manifest.items() if k != "schedules"}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--reports", type=Path, required=True)
    a = p.parse_args()
    asyncio.run(build(a.out, a.reports))
