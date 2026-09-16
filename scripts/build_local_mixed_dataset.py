"""Reproduce the frozen mixed-local index/schedule without altering source corpora."""

import argparse
import hashlib
import json
import random
from pathlib import Path

ROOTS = [
    Path("D:/drone_vla_pilot/data/public_goal_fixture_20260916_frd_v2"),
    Path("D:/drone_vla_pilot/data/visible_yaw_pairs_20260916_v3"),
]
HASHES = [
    "409ee16d5dbe14ddfff9592d7aca732891e8d95403f0d8a957641286f02c29fe",
    "11f45ed28821bd28ca1f08d327d95de491dad387ab234cf649bbf1c904a5cf19",
]


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    rows = []
    sources = []
    for root, sha in zip(ROOTS, HASHES, strict=True):
        assert hashlib.sha256((root / "index.jsonl").read_bytes()).hexdigest() == sha
        sources.append(dict(root=str(root), index_sha256=sha))
        for line in (root / "index.jsonl").read_text().splitlines():
            r = json.loads(line)
            r["data_root"] = str(root)
            r["task_group"] = "coordinate" if root == ROOTS[0] else "visual"
            if "decision_id" not in r:
                r["decision_id"] = (
                    f"visible_yaw_s{r['seed']}_l{r['layout']}_{r['instruction_colour']}"
                )
            assert r["seed"] not in set(range(1, 41)) | set(range(1060, 1065))
            assert r["split"] == ("val" if r["seed"] % 5 == 0 else "train")
            assert (
                hashlib.sha256((root / r["images"]["mosaic"]).read_bytes()).hexdigest()
                == r["image_sha256"]["mosaic"]
            )
            rows.append(r)
    train = [r for r in rows if r["split"] == "train"]
    val = [r for r in rows if r["split"] == "val"]
    assert (len(train), len(val)) == (252, 84)
    evaluation = [r["decision_id"] for r in val if r["task_group"] == "visual"]
    for seed in (1400, 1405):
        candidates = [r for r in val if r["seed"] == seed]
        evaluation += [
            candidates[round(i * (len(candidates) - 1) / 5)]["decision_id"] for i in range(6)
        ]
    assert len(set(evaluation)) == 28
    rng = random.Random(132)
    schedule = []
    while len(schedule) < 400:
        order = [r["decision_id"] for r in train]
        rng.shuffle(order)
        schedule.extend(order)
    schedule = schedule[:400]
    assert set(schedule[:252]) == {r["decision_id"] for r in train}
    (out / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    manifest = dict(
        sources=sources,
        train_rows=252,
        val_rows=84,
        train_scene_groups=12,
        val_scene_groups=4,
        training_schedule=schedule,
        generation_eval_ids=evaluation,
        seed=132,
        updates=400,
        lr_first200=2e-4,
        lr_last200=5e-5,
        fresh_optimizer_at200=True,
        rank=8,
        alpha=32,
        contract="direct_velocity_heading_frd_v2",
        external_rows=0,
        index_sha256=hashlib.sha256((out / "index.jsonl").read_bytes()).hexdigest(),
        limits=(
            "Mixed local diagnostic only; no real/external-domain transfer or broad task coverage"
        ),
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(build(a.out)["index_sha256"])
