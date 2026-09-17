"""Freeze one trajectory per official seen/unseen environment; evaluation only."""

import collections
import concurrent.futures
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

ROOT = Path("D:/drone_vla_pilot/data/openfly_eval_20260917")
OUT = Path("reports/vla_expanded_models_20260917")
REV = "a12316d56a4e35a32ad626fb725ed7089937a1c4"
selected = []
excluded = []
for split in ("seen", "unseen"):
    episodes = json.loads((ROOT / "Annotation" / f"{split}.json").read_text())
    groups = collections.defaultdict(list)
    for episode in episodes:
        groups[episode["image_path"].split("/")[0]].append(episode)
    for env, group in sorted(groups.items()):
        episode = min(group, key=lambda e: hashlib.sha256(e["image_path"].encode()).hexdigest())
        actions = episode["action"]
        first_turn = next((i for i, a in enumerate(actions) if a in (2, 3)), len(actions) // 3)
        indices = sorted({0, first_turn, len(actions) // 2, len(actions) - 1})
        selected.append(
            dict(split=split, environment=env, episode=episode, selected_indices=indices)
        )
manifest = dict(
    revision=REV,
    selection=(
        "one minimum-SHA256 image_path episode per official split/environment; "
        "first, first turn (or third), middle, last action"
    ),
    evaluation_only=True,
    episodes=selected,
)
path = OUT / "openfly_selection.json"
if path.exists():
    assert json.loads(path.read_text()) == manifest
else:
    path.write_text(json.dumps(manifest, indent=2))

names = {
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
source_names = {
    "stop": "stop",
    "go straight": "forward",
    "turn left": "left_turn",
    "turn right": "right_turn",
    "go up": "up",
    "go down": "down",
    "move left": "left",
    "move right": "right",
}


def prepare(item):
    episode = item["episode"]
    rel = "traj/" + episode["image_path"] + ".parquet"
    file = Path(
        hf_hub_download(
            "IPEC-COMMUNITY/OpenFly", rel, repo_type="dataset", revision=REV, local_dir=ROOT
        )
    )
    records = pq.read_table(file).to_pylist()
    by_id = {r["image_id"]: r for r in records}
    results = []
    for at in item["selected_indices"]:
        if episode["action"][at] not in names:
            excluded.append(
                dict(
                    trajectory=episode["image_path"],
                    index=at,
                    action=episode["action"][at],
                    reason="outside official evaluator 0..9 action dictionary",
                )
            )
            continue
        ids = [max(0, at - 2), max(0, at - 1), at]
        images = []
        hashes = []
        for i in ids:
            r = by_id[episode["index_list"][i]]
            assert max(abs(a - b) for a, b in zip(r["pos"], episode["pos"][i], strict=True)) < 1e-9
            assert abs(r["yaw"] - episode["yaw"][i]) < 1e-9
            destination = ROOT / "frames" / episode["image_path"] / (r["image_id"] + ".png")
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = r["image"]["bytes"]
            destination.write_bytes(data)
            images.append(str(destination))
            hashes.append(hashlib.sha256(data).hexdigest())
        current = by_id[episode["index_list"][at]]
        target = names[episode["action"][at]]
        assert source_names[current["action_type"]] == target, (target, current["action_type"])
        identity = item["split"] + ":" + episode["image_path"] + ":" + str(at)
        results.append(
            dict(
                id=identity,
                split=item["split"],
                environment=item["environment"],
                trajectory=episode["image_path"],
                index=at,
                instruction=episode["gpt_instruction"],
                images=images,
                image_sha256=hashes,
                target_id=episode["action"][at],
                target_class=target,
                parquet_action_type=current["action_type"],
                parquet_action_value=current["action_value"],
                source_position=current["pos"],
                source_yaw=current["yaw"],
                source_parquet=rel,
                velocity_available=False,
                down_camera_available=False,
            )
        )
    return results


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    rows = [r for group in pool.map(prepare, selected) for r in group]
blob = "".join(json.dumps(r) + "\n" for r in rows)
(ROOT / "eval.jsonl").write_bytes(blob.encode("utf-8"))
audit = dict(
    rows=len(rows),
    episodes=len(selected),
    split_counts=dict(collections.Counter(r["split"] for r in rows)),
    target_counts=dict(collections.Counter(r["target_class"] for r in rows)),
    sha256=hashlib.sha256(blob.encode()).hexdigest(),
    source_revision=REV,
    pose_yaw_and_coarse_action_agree=True,
    pose_tolerance=1e-9,
    training_rows_admitted=0,
    excluded=sorted(excluded, key=lambda x: (x["trajectory"], x["index"])),
)
(OUT / "openfly_data_audit.json").write_text(json.dumps(audit, indent=2))
print(json.dumps(audit, indent=2))
