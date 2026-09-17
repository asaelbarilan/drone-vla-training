# ruff: noqa: E501
"""D142 bounded official TRAIN subset, complete trajectories and causal image history."""

import collections
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

ROOT = Path("D:/drone_vla_pilot/data/openfly_train_pilot_20260917")
EVAL = Path("D:/drone_vla_pilot/data/openfly_eval_20260917")
OUT = Path("reports/vla_openfly_train_20260917")
REV = "a12316d56a4e35a32ad626fb725ed7089937a1c4"
NAMES = {
    0: "stop",
    1: "forward",
    2: "left_turn",
    3: "right_turn",
    4: "up",
    5: "down",
    6: "left",
    7: "right",
    8: "forward",
    9: "forward",
}
SOURCE = {
    "stop": "stop",
    "go straight": "forward",
    "turn left": "left_turn",
    "turn right": "right_turn",
    "go up": "up",
    "go down": "down",
    "move left": "left",
    "move right": "right",
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    raw = ROOT / "Annotation/train.json"
    episodes = json.loads(raw.read_text())
    held = {
        e["image_path"]
        for split in ("seen", "unseen")
        for e in json.loads((EVAL / f"Annotation/{split}.json").read_text())
    }
    assert not any(e["image_path"] in held for e in episodes)
    groups = collections.defaultdict(list)
    for e in episodes:
        n = len(e["action"])
        if not (3 <= n <= 80 and all(a in NAMES for a in e["action"])):
            continue
        assert all(len(e[k]) == n for k in ("index_list", "pos", "yaw"))
        groups[e["image_path"].split("/")[0]].append(e)
    selected = []
    for environment, candidates in sorted(groups.items()):
        ordered = sorted(candidates, key=lambda e: digest(e["image_path"]))
        # Include vertical routes where available, selected only from labels, not model outcomes.
        vertical = [e for e in ordered if any(a in (4, 5) for a in e["action"])]
        train = (vertical or ordered)[0]
        dev = next(e for e in ordered if e["image_path"] != train["image_path"])
        selected += [
            dict(split=split, environment=environment, episode=e)
            for split, e in (("train", train), ("dev", dev))
        ]
    manifest = dict(
        revision=REV,
        source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        official_train_episodes=len(episodes),
        official_eval_episodes=len(held),
        official_trajectory_overlap=0,
        selection="One TRAIN vertical route where available and one disjoint dev route per environment, minimum SHA256 identity; 3..80 decisions; all labels 0..9. Both subsets originate only from official TRAIN.",
        episodes=selected,
    )
    destination = OUT / "selection.json"
    if destination.exists():
        assert json.loads(destination.read_text()) == manifest
    else:
        destination.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    official_hashes = {
        h
        for line in (EVAL / "eval.jsonl").read_text().splitlines()
        for h in json.loads(line)["image_sha256"]
    }
    rows, hashes = [], collections.defaultdict(set)
    for item in selected:
        e = item["episode"]
        file = Path(
            hf_hub_download(
                "IPEC-COMMUNITY/OpenFly",
                "traj/" + e["image_path"] + ".parquet",
                repo_type="dataset",
                revision=REV,
                local_dir=ROOT,
            )
        )
        assert sum(p.stat().st_size for p in (ROOT / "traj").rglob("*.parquet")) < 2_000_000_000, (
            "2GB pilot download cap"
        )
        records = {r["image_id"]: r for r in pq.read_table(file).to_pylist()}
        frames, sha = [], []
        for i, image_id in enumerate(e["index_list"]):
            r = records[image_id]
            assert SOURCE[r["action_type"]] == NAMES[e["action"][i]]
            assert max(abs(a - b) for a, b in zip(r["pos"], e["pos"][i], strict=True)) < 1e-8
            assert abs(r["yaw"] - e["yaw"][i]) < 1e-8
            data = r["image"]["bytes"]
            h = hashlib.sha256(data).hexdigest()
            assert h not in official_hashes, "Selected official evaluation image overlap"
            hashes[item["split"]].add(h)
            dest = ROOT / "frames" / e["image_path"] / (image_id + ".png")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            frames.append(str(dest))
            sha.append(h)
        for i, action in enumerate(e["action"]):
            indices = [max(0, i - 2), max(0, i - 1), i]
            rows.append(
                dict(
                    id=e["image_path"] + ":" + str(i),
                    trajectory=e["image_path"],
                    split=item["split"],
                    environment=item["environment"],
                    instruction=e["gpt_instruction"],
                    index=i,
                    action_id=action,
                    action_name=NAMES[action],
                    images=[frames[j] for j in indices],
                    image_sha256=[sha[j] for j in indices],
                    position=e["pos"][i],
                    yaw=e["yaw"][i],
                )
            )
        print(
            json.dumps(
                dict(trajectory=e["image_path"], split=item["split"], rows=len(e["action"]))
            ),
            flush=True,
        )
    assert not hashes["train"] & hashes["dev"], "Train/dev image duplicate"
    index = ROOT / "index.jsonl"
    index.write_bytes(("".join(json.dumps(r) + "\n" for r in rows)).encode())
    audit = dict(
        status="ready",
        revision=REV,
        index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(),
        rows={s: sum(r["split"] == s for r in rows) for s in ("train", "dev")},
        actions={
            s: dict(collections.Counter(r["action_id"] for r in rows if r["split"] == s))
            for s in ("train", "dev")
        },
        trajectory_overlap=0,
        image_overlap=0,
        official_eval_selected_image_overlap=0,
        full_official_eval_image_overlap="Not fully checked: only downloaded official diagnostic image hashes available; all official trajectory identities excluded.",
        history="Only previous two and current annotation frames; repeat first at start. No pose or future labels supplied to model.",
        contract="openfly_native_action_id_v1: exact released IDs; no conversion to velocity or physical execution. IDs 6/7 absent in manifest; negative labels excluded as unresolved.",
        parquet_bytes=sum(p.stat().st_size for p in (ROOT / "traj").rglob("*.parquet")),
    )
    (OUT / "data_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
