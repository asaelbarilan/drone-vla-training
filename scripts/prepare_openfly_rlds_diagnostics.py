"""Audit packed training observations and freeze explicit reproduction controls."""

import hashlib
import json
from pathlib import Path

import numpy as np

from uavlab.training.openfly_codec import CODEBOOK, OpenFlyCodec

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_routes_20260919"


def main():
    config = json.loads(Path("D:/drone_vla_pilot/models/openfly-agent-7b/config.json").read_text())
    annotations = {}
    for name in ["train", "seen", "unseen"]:
        folder = "openfly_train_pilot_20260917" if name == "train" else "openfly_eval_20260917"
        rows = json.loads(
            Path(f"D:/drone_vla_pilot/data/{folder}/Annotation/{name}.json").read_text()
        )
        annotations[name] = {r["image_path"]: r for r in rows}
    audits, inputs = [], []
    for subset in ["vlnv1", "vlnv11"]:
        record = json.loads((OUT / (subset + "_record.json")).read_text())
        f = record["fields"]
        path = f["episode_metadata/file_path"][0].split("/uav_vln_data/")[1]
        assert path not in annotations["seen"] and path not in annotations["unseen"]
        raw_annotation = annotations["train"].get(path)
        current = f["steps/observation/image_1"]
        current_hashes = [x["sha256"] for x in current]
        codec = OpenFlyCodec(config, subset)
        stat_equal = [
            all(
                value == config["norm_stats"][subset]["action"][key]
                for key, value in r["data"]["action"].items()
            )
            for r in record["statistics"]
        ]
        assert all(config["norm_stats"][subset]["action"]["mask"])
        assert any(stat_equal), "Must use source-proven subset statistics"
        codec.require_source_statistics(
            record["statistics"][stat_equal.index(True)]["data"]["action"]
        )
        future, unknown, steps = [], [], []
        for i in range(len(current)):
            action = np.asarray(f["steps/action"][8 * i : 8 * (i + 1)])
            matches = np.flatnonzero(np.all(action == CODEBOOK, axis=1))
            assert len(matches) == 1
            a = int(matches[0])
            codec.require_coverage([a])
            triplet = [f["steps/observation/" + k][i] for k in ["image_3", "image_2", "image_1"]]
            mapped = [
                [j for j, h in enumerate(current_hashes) if h == x["sha256"]] for x in triplet
            ]
            if any(not ids for ids in mapped):
                unknown.append(i)
            leaks = [j for j, ids in enumerate(mapped[:2]) if ids and min(ids) > i]
            if leaks:
                future.append(dict(step=i, slots=leaks, current_matches=mapped))
            for variant in ["rlds_stored_raw", "rlds_stored_training", "rlds_causal_training"]:
                images = list(triplet)
                if variant == "rlds_causal_training":
                    for j in leaks:
                        images[j] = current[max(0, i - (2 - j))]
                inputs.append(
                    dict(
                        id=f"{variant}:{subset}:{i}",
                        source_id=f"{subset}:{i}",
                        variant=variant,
                        trajectory=path,
                        norm_key=subset,
                        frame_index=i,
                        action_id=a,
                        direction_id=1 if a in (8, 9) else a,
                        instruction=f["steps/language_instruction"][i],
                        images=[x["path"] for x in images],
                        image_sha256=[x["sha256"] for x in images],
                        image_indices=mapped,
                        future_history_slots=leaks if variant != "rlds_causal_training" else [],
                        max_image_edge=None,
                        prompt_style="model_card" if variant == "rlds_stored_raw" else "training",
                        history_pooling="released" if variant == "rlds_stored_raw" else "training",
                        training_pipeline_keeps_step=i > 0,
                    )
                )
            steps.append(dict(index=i, action_id=a, history_indices=mapped))
        audits.append(
            dict(
                subset=subset,
                trajectory=path,
                steps=steps,
                future_history=future,
                unknown_history=unknown,
                source_stats_equal=stat_equal,
                train_annotation_found=raw_annotation is not None,
                current_instruction_equal=raw_annotation["gpt_instruction"]
                == f["steps/language_instruction"][0]
                if raw_annotation
                else None,
                current_annotation_instruction=raw_annotation["gpt_instruction"]
                if raw_annotation
                else None,
                official_eval_route_overlap=False,
                duplicate_current_images=len(current) - len(set(current_hashes)),
            )
        )
    (OUT / "rlds_inputs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in inputs))
    (OUT / "rlds_audit.json").write_text(json.dumps(audits, indent=2))
    combined = (OUT / "route_inputs.jsonl").read_bytes() + (OUT / "rlds_inputs.jsonl").read_bytes()
    (OUT / "all_inputs.jsonl").write_bytes(combined)
    print(
        json.dumps(
            dict(
                total_calls=len(combined.splitlines()),
                sha256=hashlib.sha256(combined).hexdigest(),
                rlds=[
                    {
                        k: v
                        for k, v in a.items()
                        if k not in ["steps", "current_annotation_instruction"]
                    }
                    for a in audits
                ],
            )
        )
    )


if __name__ == "__main__":
    main()
