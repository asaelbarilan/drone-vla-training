"""Freeze three complete development routes before model inference."""

import collections
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
from audit_openfly_dataset_full import CACHE, DATA, NAMES, SELECTION
from PIL import Image

from uavlab.training.openfly_history import transition_history

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_routes_20260919"
VIEW = ROOT / "reports/vla_dataset_review_20260916"


def main():
    manifest = [
        json.loads(x)
        for x in (ROOT / "reports/vla_openfly_repair_20260918/aligned_macro_manifest.jsonl")
        .read_text()
        .splitlines()
    ]
    grouped = collections.defaultdict(list)
    for row in manifest:
        if row["split"] == "val":
            grouped[row["trajectory"]].append(row)
    candidates = collections.defaultdict(list)
    for item in SELECTION["episodes"]:
        episode = item["episode"]
        path = episode["image_path"]
        if path not in grouped or len(grouped[path]) != len(episode["action"]):
            continue  # Require a complete route without quarantined decisions.
        category = (
            (
                "airsim_vertical"
                if any(a in (4, 5) for a in episode["action"])
                else "airsim_horizontal"
            )
            if path.startswith("env_airsim")
            else "gs_horizontal"
            if path.startswith("env_gs")
            else None
        )
        if category:
            candidates[category].append(path)
    chosen = {
        k: min(v, key=lambda x: hashlib.sha256(x.encode()).hexdigest())
        for k, v in candidates.items()
    }
    assert len(chosen) == 3
    routes, inputs = [], []
    for category, path in sorted(chosen.items()):
        rows = sorted(grouped[path], key=lambda x: x["frame_index"])
        raw = sorted(
            pq.read_table(CACHE / "traj" / (path + ".parquet")).to_pylist(),
            key=lambda x: x["frame_index"],
        )
        atomic = [NAMES[x["action_type"]] for x in raw]
        frames = []
        for i, record in enumerate(raw):
            file = DATA / "frames" / path / (record["image_id"] + ".png")
            asset = VIEW / "route_assets" / category / f"{i:04}.jpg"
            asset.parent.mkdir(parents=True, exist_ok=True)
            im = Image.open(file).convert("RGB")
            im.thumbnail((960, 540))
            im.save(asset, quality=85)
            frames.append(
                dict(
                    index=i,
                    image=str(file),
                    sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
                    preview=asset.relative_to(VIEW).as_posix(),
                    pos=record["pos"],
                    yaw=record["yaw"],
                    action_id=atomic[i],
                    image_id=record["image_id"],
                )
            )
        for row in rows:
            row = dict(row, route_category=category)
            t = row["frame_index"]
            for variant in [
                "prior_adjacent",
                "native_resize",
                "transition_history",
                "training_interface",
            ]:
                indices = (
                    row["image_indices"]
                    if variant in ["prior_adjacent", "native_resize"]
                    else transition_history(atomic[:t], t)
                )
                inputs.append(
                    dict(
                        row,
                        id=variant + ":" + row["id"],
                        source_id=row["id"],
                        variant=variant,
                        images=[frames[k]["image"] for k in indices],
                        image_indices=indices,
                        image_sha256=[frames[k]["sha256"] for k in indices],
                        norm_key="vlnv11",
                        max_image_edge=256 if variant == "prior_adjacent" else None,
                        prompt_style="training"
                        if variant == "training_interface"
                        else "model_card",
                        history_pooling="training"
                        if variant == "training_interface"
                        else "released",
                    )
                )
        routes.append(
            dict(
                category=category,
                trajectory=path,
                instruction=rows[0]["instruction"],
                frames=frames,
                decisions=rows,
                selection_sha256=hashlib.sha256(path.encode()).hexdigest(),
            )
        )
    (OUT / "routes.json").write_text(json.dumps(routes, indent=2))
    (OUT / "route_inputs.jsonl").write_text("".join(json.dumps(x) + "\n" for x in inputs))
    summary = dict(
        routes=chosen,
        raw_frames=sum(len(x["frames"]) for x in routes),
        decisions=sum(len(x["decisions"]) for x in routes),
        inference_calls=len(inputs),
        inputs_sha256=hashlib.sha256((OUT / "route_inputs.jsonl").read_bytes()).hexdigest(),
        training_index_sha256=hashlib.sha256((DATA / "index.jsonl").read_bytes()).hexdigest(),
    )
    (OUT / "selection.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
