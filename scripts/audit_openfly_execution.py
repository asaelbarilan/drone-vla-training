"""Reconstruct existing diagnostic routes without rendering or changing data.

This is an action/pose alignment gate. It does not run a model or a simulator.
"""

import ast
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from uavlab.training.openfly_codec import CODEBOOK
from uavlab.training.openfly_execution import advance_pose, navigation_metrics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_execution_20260919"
PREVIOUS = ROOT / "reports/vla_openfly_routes_20260919"
DATA = Path("D:/drone_vla_pilot/data")
SOURCE = Path("D:/drone_vla_pilot/models/OpenFly-Platform/train/eval.py")
RAW_ACTIONS = {
    "stop": 0,
    "go straight": 1,
    "turn left": 2,
    "turn right": 3,
    "go up": 4,
    "go down": 5,
    "up": 4,
    "down": 5,
    "move left": 6,
    "move right": 7,
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def trace(actions, indices, raw):
    observed = [(*raw[i]["pos"], raw[i]["yaw"]) for i in indices]
    pose = observed[0]
    steps = []
    first_stop = None
    invalid_label = False
    for i, (action, ref) in enumerate(zip(actions, observed, strict=True)):
        after = advance_pose(pose, action) if action is not None else pose
        steps.append(
            {
                "step": i,
                "raw_frame": indices[i],
                "action_id": action,
                "observed_pose": ref,
                "integrated_pose": pose,
                "after_action": after,
                "position_error": math.dist(pose[:3], ref[:3]),
                "yaw_error_degrees": abs(
                    math.degrees((pose[3] - ref[3] + math.pi) % (2 * math.pi) - math.pi)
                ),
                "after_first_stop": first_stop is not None,
            }
        )
        if action == 0 and first_stop is None:
            first_stop = i
        pose = after
        if action is None:
            invalid_label = True
            break
    stop_index = first_stop if first_stop is not None else len(steps) - 1
    replay = [s["integrated_pose"] for s in steps[: stop_index + 1]]
    replay.append(steps[stop_index]["after_action"])
    return {
        "steps": steps,
        "invalid_data_label": invalid_label,
        "max_position_error": max(s["position_error"] for s in steps),
        "max_yaw_error_degrees": max(s["yaw_error_degrees"] for s in steps),
        "first_stop_step": first_stop,
        "commands_after_first_stop": len(steps) - first_stop - 1 if first_stop is not None else 0,
        "metrics_at_first_stop_against_last_raw_pose": navigation_metrics(
            replay,
            raw[-1]["pos"],
            "stop"
            if first_stop is not None
            else "invalid_data_label"
            if invalid_label
            else "timeout",
        ),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    selections = read_json(PREVIOUS / "selection.json")
    annotation_path = DATA / "openfly_train_pilot_20260917/Annotation/train.json"
    annotations = {x["image_path"]: x for x in read_json(annotation_path)}
    protected = set()
    for split in ("seen", "unseen"):
        protected.update(
            r["image_path"]
            for r in read_json(DATA / "openfly_eval_20260917/Annotation" / (split + ".json"))
        )
    index = DATA / "joint_openfly_local_20260917_v1/index.jsonl"
    index_hash = hashlib.sha256(index.read_bytes()).hexdigest()
    assert index_hash == selections["training_index_sha256"], "Frozen training data changed"
    routes = [
        (k, v, DATA / "openfly_train_pilot_20260917/traj" / (v + ".parquet"))
        for k, v in selections["routes"].items()
    ]
    packed_matches = {x["subset"]: x for x in read_json(PREVIOUS / "packed_vs_current_raw.json")}
    for subset in ("vlnv1", "vlnv11"):
        routes.append(
            (
                subset,
                packed_matches[subset]["trajectory"],
                DATA / "openfly_rlds_diagnostic_20260919" / (subset + "_raw.parquet"),
            )
        )
    corrected = {r["trajectory"]: r for r in read_json(PREVIOUS / "routes.json")}
    result = []
    for name, route, path in routes:
        assert route not in protected, "Official evaluation route cannot enter development"
        assert route in annotations, "Only previously selected official TRAIN routes allowed"
        raw = sorted(pq.read_table(path).to_pylist(), key=lambda x: x["frame_index"])
        raw_ids = [RAW_ACTIONS.get(r["action_type"]) for r in raw]
        unknown = [
            {k: v for k, v in r.items() if k != "image"}
            for r, a in zip(raw, raw_ids, strict=True)
            if a is None
        ]
        by_image = {r["image_id"]: i for i, r in enumerate(raw)}
        ann = annotations[route]
        variants = {"raw_atomic": trace(raw_ids, list(range(len(raw))), raw)}
        if unknown and all(r["action_type"] == "donw" for r in unknown):
            variants["counterfactual_donw_means_down_NOT_adopted"] = trace(
                [5 if a is None else a for a in raw_ids], list(range(len(raw))), raw
            )
        # Explicit phase aliases from the source builder; no duration/velocity inference.
        ids = [{-1: 4, -2: 5}.get(a, a) for a in ann["action"]]
        indices = [by_image[i] for i in ann["index_list"]]
        variants["current_annotation"] = trace(ids, indices, raw)
        if route in corrected:
            rows = corrected[route]["decisions"]
            variants["corrected_macro"] = trace(
                [r["action_id"] for r in rows], [r["frame_index"] for r in rows], raw
            )
        if name in packed_matches:
            match = packed_matches[name]
            packed_ids = []
            for vector in match["packed_action_vectors"]:
                matches = np.flatnonzero(np.all(vector == CODEBOOK, axis=1))
                assert len(matches) == 1, "Packed vector is not a supported native code"
                packed_ids.append(int(matches[0]))
            variants["original_packed"] = trace(
                packed_ids, [m["nearest_raw_frame"] for m in match["image_matches"]], raw
            )
        atomic = variants["raw_atomic"]
        result.append(
            {
                "name": name,
                "trajectory": route,
                "raw_frames": len(raw),
                "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "unknown_raw_labels": unknown,
                "raw_stop_values": [r["action_value"] for r in raw if r["action_type"] == "stop"],
                "units": "metres" if route.startswith("env_airsim") else "unverified source units",
                "atomic_gate_passed": not unknown
                and atomic["max_position_error"] < 1e-6
                and atomic["max_yaw_error_degrees"] < 1e-6,
                "variants": variants,
            }
        )
    # Extract only a pure function; never import or run the upstream simulator launcher.
    source = SOURCE.read_text(encoding="utf-8")
    function = next(
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.FunctionDef) and n.name == "getPoseAfterMakeAction"
    )
    scope = {"math": math}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), scope)
    parity_checks = 0
    for pose in (
        [0, 0, 0, 0],
        [4, -5, 7, math.pi / 2],
        [3, 8, -9, math.pi],
        [0, 0, 0, -math.pi / 3],
    ):
        for action in range(10):
            assert np.allclose(advance_pose(pose, action), scope[function.name](pose, action))
            parity_checks += 1
    report = {
        "renderer_used": False,
        "model_used": False,
        "flight_success_claim": False,
        "training_index_sha256": index_hash,
        "upstream_eval_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "upstream_pose_parity_checks": parity_checks,
        "routes": result,
    }
    (OUT / "expert_reconstruction.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "source_parity": parity_checks,
                "routes": [
                    {
                        "name": r["name"],
                        "atomic_gate": r["atomic_gate_passed"],
                        "errors": {
                            k: {
                                "position": v["max_position_error"],
                                "yaw": v["max_yaw_error_degrees"],
                                "post_stop_commands": v["commands_after_first_stop"],
                            }
                            for k, v in r["variants"].items()
                        },
                    }
                    for r in result
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
