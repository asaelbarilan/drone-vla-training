# ruff: noqa: E501
"""D144: enlarge official TRAIN routes and mix verified atomic labels with local FRD."""

import collections
import concurrent.futures
import hashlib
import json
import math
import random
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

from uavlab.training.mixed_batches import balanced_schedule, task_class

BASE = Path("D:/drone_vla_pilot")
CACHE = BASE / "data/openfly_train_pilot_20260917"
ROOT = BASE / "data/joint_openfly_local_20260917_v1"
REPORT = Path("reports/vla_joint_openfly_20260917")
REV = "a12316d56a4e35a32ad626fb725ed7089937a1c4"
NATIVE = {"stop": 0, "go straight": 1, "turn left": 2, "turn right": 3, "go up": 4, "go down": 5}
PROMPT = (
    "OpenFly atomic navigation mode. Three front images are oldest to newest, ending with "
    "the current observation. Follow the route and choose the next atomic action. "
    "Return exactly one digit: 0=mission stop, 1=forward 3 metres, 2=turn left 30 degrees, "
    "3=turn right 30 degrees, 4=ascend 3 metres, 5=descend 3 metres. These are navigation "
    "primitives, not velocities. No odometry or downward image is provided. Route: "
)


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def prepare(item):
    e = item["episode"]
    p = Path(
        hf_hub_download(
            "IPEC-COMMUNITY/OpenFly",
            "traj/" + e["image_path"] + ".parquet",
            repo_type="dataset",
            revision=REV,
            local_dir=CACHE,
        )
    )
    records = sorted(pq.read_table(p).to_pylist(), key=lambda r: r["frame_index"])
    assert len({r["traj_id"] for r in records}) == 1
    assert [r["frame_index"] for r in records] == list(range(len(records)))
    paths, hashes = [], []
    for r in records:
        data = r["image"]["bytes"]
        destination = ROOT / "frames" / e["image_path"] / (r["image_id"] + ".png")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        paths.append(str(destination))
        hashes.append(hashlib.sha256(data).hexdigest())
    rows, excluded = [], []
    for i, r in enumerate(records):
        action = NATIVE.get(r["action_type"])
        reason = None
        if action is None:
            reason = "unsupported raw action"
        elif action == 0:
            if (
                i != len(records) - 1
                or e["action"][-1] != 0
                or r["image_id"] != e["index_list"][-1]
            ):
                reason = "terminal action not supported by final annotation"
        elif i == len(records) - 1:
            reason = "nonterminal without next pose"
        else:
            nxt = records[i + 1]
            dx, dy, dz = [b - a for a, b in zip(r["pos"], nxt["pos"], strict=True)]
            yaw = (nxt["yaw"] - r["yaw"] + math.pi) % (2 * math.pi) - math.pi
            actual = (
                dx * math.cos(r["yaw"]) + dy * math.sin(r["yaw"]),
                -dx * math.sin(r["yaw"]) + dy * math.cos(r["yaw"]),
                dz,
                math.degrees(yaw),
            )
            expected = {
                1: (3, 0, 0, 0),
                2: (0, 0, 0, 30),
                3: (0, 0, 0, -30),
                4: (0, 0, 3, 0),
                5: (0, 0, -3, 0),
            }[action]
            if max(abs(a - b) for a, b in zip(actual, expected, strict=True)) > 0.01:
                reason = "raw action disagrees with next pose"
        if reason:
            excluded.append(
                dict(trajectory=e["image_path"], frame=i, action=r["action_type"], reason=reason)
            )
            continue
        history = [max(0, i - 2), max(0, i - 1), i]
        rows.append(
            dict(
                id="openfly:" + e["image_path"] + ":" + str(i),
                source="openfly",
                split=item["split"],
                trajectory=e["image_path"],
                environment=item["environment"],
                frame_index=i,
                contract="openfly_atomic_primitive_v1",
                action_id=action,
                action_name=r["action_type"],
                instruction=e["gpt_instruction"],
                prompt=PROMPT + e["gpt_instruction"],
                images=[paths[j] for j in history],
                image_sha256=[hashes[j] for j in history],
                group=str(action),
                next_pose_verified=action != 0,
            )
        )
    return rows, excluded, p.stat().st_size


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(exist_ok=True)
    episodes = json.loads((CACHE / "Annotation/train.json").read_text())
    old = json.loads(Path("reports/vla_openfly_train_20260917/selection.json").read_text())[
        "episodes"
    ]
    held = {
        e["image_path"]
        for s in ("seen", "unseen")
        for e in json.loads((BASE / f"data/openfly_eval_20260917/Annotation/{s}.json").read_text())
    }
    groups = collections.defaultdict(list)
    for e in episodes:
        if (
            e["image_path"] not in held
            and 3 <= len(e["action"]) <= 80
            and all(a in range(10) for a in e["action"])
        ):
            groups[e["image_path"].split("/")[0]].append(e)
    selected = []
    for env, candidates in sorted(groups.items()):
        ordered = sorted(candidates, key=lambda e: digest(e["image_path"]))
        old_train = next(
            x["episode"] for x in old if x["environment"] == env and x["split"] == "train"
        )
        old_dev = next(x["episode"] for x in old if x["environment"] == env and x["split"] == "dev")
        reserved = {old_train["image_path"], old_dev["image_path"]}
        extra_dev = next(
            e
            for e in ordered
            if e["image_path"] not in reserved
            and (
                any(a in (4, 5) for a in e["action"])
                or not any(any(a in (4, 5) for a in c["action"]) for c in ordered)
            )
        )
        reserved.add(extra_dev["image_path"])
        train = [old_train, *[e for e in ordered if e["image_path"] not in reserved][:7]]
        selected += [dict(split="train", environment=env, episode=e) for e in train]
        selected += [dict(split="val", environment=env, episode=e) for e in (old_dev, extra_dev)]
    selection = dict(
        revision=REV,
        selection="Per environment: old TRAIN plus seven lowest-hash unused TRAIN routes; old dev plus one lowest-hash vertical dev where available. All from official TRAIN; all official evaluation identities excluded.",
        episodes=selected,
    )
    if (REPORT / "selection.json").exists():
        assert json.loads((REPORT / "selection.json").read_text()) == selection
    dump(REPORT / "selection.json", selection)
    assert len(selected) == 110 and len({x["episode"]["image_path"] for x in selected}) == 110
    assert not {x["episode"]["image_path"] for x in selected} & held
    rows = []
    excluded = []
    size = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i, (new, bad, nbytes) in enumerate(pool.map(prepare, selected)):
            rows.extend(new)
            excluded.extend(bad)
            size += nbytes
            assert size < 10 * 1024**3, "10GiB source download cap"
            print(
                json.dumps(
                    dict(
                        trajectories=i + 1,
                        rows=len(rows),
                        excluded=len(excluded),
                        source_bytes=size,
                    )
                ),
                flush=True,
            )
    train_hashes = {h for r in rows if r["split"] == "train" for h in r["image_sha256"]}
    val_hashes = {h for r in rows if r["split"] == "val" for h in r["image_sha256"]}
    official_hashes = {
        h
        for line in (BASE / "data/openfly_eval_20260917/eval.jsonl").read_text().splitlines()
        for h in json.loads(line)["image_sha256"]
    }
    assert not train_hashes & val_hashes and not train_hashes & official_hashes
    local_path = BASE / "data/local_expanded_20260917_v4/index.jsonl"
    local = [json.loads(x) for x in local_path.read_text().splitlines()]
    local_manifest = json.loads(local_path.with_name("manifest.json").read_text())
    assert hashlib.sha256(local_path.read_bytes()).hexdigest() == local_manifest["index_sha256"]
    for r in local:
        assert r["seed"] not in range(1, 41) and r["seed"] not in range(1060, 1065)
        rows.append(dict(r, id="local:" + r["decision_id"], source="local", group=task_class(r)))
    by = {r["id"]: r for r in rows}
    assert len(by) == len(rows)
    rng = random.Random(144)
    schedule = []
    local_schedule = balanced_schedule(local, 400, seed=144)
    pools = {
        str(a): [
            r["id"]
            for r in rows
            if r["source"] == "openfly" and r["split"] == "train" and r["action_id"] == a
        ]
        for a in range(6)
    }
    assert all(pools.values())
    queues = {k: [] for k in pools}
    # Four original local classes plus four OpenFly examples per effective batch.
    for step in range(400):
        batch = ["local:" + x for x in local_schedule[step]]
        for j in range(4):
            key = str((step * 4 + j) % 6)
            if not queues[key]:
                queues[key] = list(pools[key])
                rng.shuffle(queues[key])
            batch.append(queues[key].pop())
        rng.shuffle(batch)
        assert all(by[k]["split"] == "train" for k in batch)
        schedule.append(batch)
    local_eval = ["local:" + x for x in local_manifest["generation_eval_ids"]]
    native_eval = []
    for a in range(6):
        group = sorted(
            [
                r
                for r in rows
                if r["source"] == "openfly" and r["split"] == "val" and r["action_id"] == a
            ],
            key=lambda r: digest(r["id"]),
        )
        native_eval += [r["id"] for r in group[:12]]
    assert all(by[k]["split"] == "val" for k in local_eval + native_eval)
    payload = "".join(json.dumps(r) + "\n" for r in rows).encode()
    (ROOT / "index.jsonl").write_bytes(payload)
    manifest = dict(
        index_sha256=hashlib.sha256(payload).hexdigest(),
        local_source_sha256=local_manifest["index_sha256"],
        schedules=schedule,
        evaluation_ids=local_eval + native_eval,
        counts=dict(collections.Counter(r["source"] + ":" + r["split"] for r in rows)),
        native_actions={
            s: dict(
                collections.Counter(
                    r["action_name"] for r in rows if r["source"] == "openfly" and r["split"] == s
                )
            )
            for s in ("train", "val")
        },
        source_bytes=size,
        excluded=excluded,
        official_eval_trajectory_overlap=0,
        train_dev_image_overlap=0,
        official_downloaded_eval_image_overlap=0,
        limits="Official full-image duplicate search unavailable; all official eval trajectory identities excluded. Dual explicit output contracts; no inferred OpenFly velocities. STOP checked against annotation, not independently verified goal geometry.",
    )
    dump(ROOT / "manifest.json", manifest)
    dump(REPORT / "data_audit.json", manifest)
    print(json.dumps(manifest["counts"]), flush=True)


if __name__ == "__main__":
    main()
