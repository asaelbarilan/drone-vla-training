"""Audit new public-goal fixture inputs, teacher labels and exact simulator replay."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from PIL import Image

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.analysis.flight_debugger import html_document, load_run
from uavlab.contracts import ControlCommand, MissionSpec
from uavlab.core.frame_store import global_store
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.reasoning.aerovla import make_dual_view_mosaic
from uavlab.training.direct_vla_contract import (
    action_from_target,
    parse_target,
    target_from_command,
    target_json,
)
from uavlab.training.direct_vla_fixture import (
    DT_NS,
    HORIZON_S,
    KINDS,
    context,
    public_teacher,
    student_prompt,
    student_state,
)
from uavlab.training.qwen_vla_preflight import PILOT_EVALUATION_SEEDS
from uavlab.training.splits import TRAIN_SEEDS


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def image_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def audit(root: Path, report_dir: Path):
    root = root.resolve()
    manifest = read(root / "manifest.json")
    rows = [
        json.loads(line) for line in (root / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    seeds = {r["seed"] for r in rows}
    if seeds != set(manifest["seeds"]) or seeds & PILOT_EVALUATION_SEEDS:
        raise ValueError("seed manifest mismatch or pilot evaluation leakage")
    if not seeds <= set(TRAIN_SEEDS):
        raise ValueError("forbidden collection seed")
    if len(rows) != manifest["samples"]:
        raise ValueError("sample count mismatch")
    teacher_checks = source_checks = pose_checks = execution_checks = 0
    image_splits, holds, stops = {}, Counter(), Counter()
    for row in rows:
        expected_split = "val" if row["seed"] % 5 == 0 else "train"
        if row["split"] != expected_split:
            raise ValueError("split differs from frozen seed assignment")
        if set(row["state"]) != {"position_enu_m", "velocity_enu_mps", "yaw_enu_rad"}:
            raise ValueError("undeclared state fields")
        expected_prompt = student_prompt(row["instruction"], row["state"])
        if row["prompt"] != expected_prompt:
            raise ValueError("prompt mismatch")
        command, terminal, evidence = public_teacher(
            row["instruction"], row["state"], row["t_sim_ns"]
        )
        target = target_from_command(command, row["state"]["yaw_enu_rad"], terminal=terminal)
        if row["teacher_command"] != command.model_dump(mode="json"):
            raise ValueError("teacher command cannot be recovered from public student inputs")
        if parse_target(json.dumps(row["target"])) != target:
            raise ValueError("target differs from observable teacher")
        if row["terminal_evidence"] != evidence:
            raise ValueError("terminal evidence mismatch")
        stops[row["seed"]] += int(terminal)
        holds[row["seed"]] += int(command.is_hold and not terminal)
        teacher_checks += 1
        for camera, relative in row["images"].items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError("image path escapes dataset")
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest != row["image_sha256"][camera]:
                raise ValueError("image bytes changed")
            with Image.open(io.BytesIO(raw)) as im:
                if im.size != (224, 224) or im.mode != "RGB":
                    raise ValueError("wrong camera format")
                im.verify()
            if camera == "mosaic":
                image_splits.setdefault(digest, set()).add(row["split"])
    if any(stops[s] != 1 for s in seeds):
        raise ValueError("each completed fixture must record exactly one terminal sample")
    if any(not holds[s] for s in seeds):
        raise ValueError("fixture did not record nonterminal braking hold")

    for split in ("train", "val"):
        annotated = [
            json.loads(x)
            for x in (root / f"{split}_swift.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        expected = [
            {
                "images": [r["images"]["mosaic"]],
                "messages": [
                    {"role": "user", "content": "<image>\n" + r["prompt"]},
                    {
                        "role": "assistant",
                        "content": target_json(parse_target(json.dumps(r["target"]))),
                    },
                ],
            }
            for r in rows
            if r["split"] == split
        ]
        if annotated != expected:
            raise ValueError("training annotation does not match audited original record")

    runs = []
    for episode in manifest["episodes"]:
        folder = root / episode["run"]
        run_manifest = read(folder / "manifest.json")
        config = run_manifest["environment_config"]
        seed = run_manifest["seeds"][0]
        selected = {r["observation_seq"]: r for r in rows if r["seed"] == seed}
        if len(selected) != sum(r["seed"] == seed for r in rows):
            raise ValueError("duplicate observation in episode")
        events = [
            json.loads(x)
            for x in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        mission = MissionSpec(
            mission_id="audit",
            instruction=config["instruction"],
            task_family=config["task_family"],
            success=config["params"]["success"],
        )
        env = DeterministicEnv(**config["params"])
        await env.reset(mission, seed)
        found = set()
        controller = MockVelocityController()
        controller.reset(mission, seed)
        current_sample = None
        for event in events:
            if event["event_type"] != "control":
                continue
            obs = await env.observe()
            control = event["payload"]
            if obs.t_sim_ns != event["t_sim_ns"] or obs.seq != control["observation_seq"]:
                raise ValueError("control/source observation time mismatch")
            if [control["position_" + a] for a in "xyz"] != list(obs.position.as_tuple()):
                raise ValueError("replay pose mismatch")
            if control["observed_velocity"] != list(obs.velocity.as_tuple()):
                raise ValueError("replay measured velocity mismatch")
            if control["yaw_rad"] != obs.yaw_rad:
                raise ValueError("replay yaw mismatch")
            pose_checks += 1
            if obs.seq in selected:
                row = selected[obs.seq]
                current_sample = row
                if control["setup_only"]:
                    raise ValueError("setup motion leaked into labels")
                if row["state"] != student_state(obs) or row["t_sim_ns"] != obs.t_sim_ns:
                    raise ValueError("training odometry/source alignment mismatch")
                actual = {
                    "front": global_store().get(obs.rgb.uri),
                    "down": global_store().get(obs.rgb_down.uri),
                }
                actual["mosaic"] = make_dual_view_mosaic(actual["front"], actual["down"], 224)
                for camera, img in actual.items():
                    if image_bytes(img) != (root / row["images"][camera]).read_bytes():
                        raise ValueError(
                            f"re-rendered original camera mismatch {seed}/{obs.seq}/{camera}"
                        )
                    source_checks += 1
                found.add(obs.seq)
            raw = ControlCommand.model_validate(control["command"])
            if raw.velocity.as_tuple() != tuple(control["v" + a] for a in "xyz"):
                raise ValueError("recorded executed command mismatch")
            if raw.yaw_rate_rps != control["yaw_rate"] or raw.t_sim_ns != obs.t_sim_ns:
                raise ValueError("command timing/yaw mismatch")
            if not control["setup_only"]:
                if current_sample is None:
                    raise ValueError("executed control has no label source")
                elapsed = obs.t_sim_ns - current_sample["t_sim_ns"]
                if not 0 <= elapsed < int(HORIZON_S * 1e9):
                    raise ValueError("control continued past label horizon")
                decoded = action_from_target(
                    parse_target(json.dumps(current_sample["target"])),
                    current_sample["state"]["yaw_enu_rad"],
                    duration_s=HORIZON_S,
                )
                ctx = context(mission, obs, "audit")
                expected = (
                    controller.hold(ctx)
                    if decoded is None
                    else controller.from_action(
                        decoded,
                        ctx,
                        current_sample["decision_id"],
                    )
                )
                if (
                    decoded is not None
                    and decoded.model_dump(mode="json") != current_sample["decoded_action"]
                ):
                    raise ValueError("saved decoder output differs from target")
                if expected.velocity != raw.velocity or expected.yaw_rate_rps != raw.yaw_rate_rps:
                    raise ValueError("executed action differs from training label")
                if expected.expires_t_sim_ns != raw.expires_t_sim_ns:
                    raise ValueError("executed command lifetime differs")
                execution_checks += 1
            await env.step(raw, DT_NS)
        if found != set(selected):
            raise ValueError("indexed sample has no corresponding recorded control")
        await env.close()
        run = await load_run(folder)
        if run["provenance"]["missing_source_frames"]:
            raise ValueError("debugger decision lost source frame")
        # Standard debugger labels these images as replay-rendered. Its RGB sources
        # were just verified against all captured front/down/mosaic PNG bytes.
        run["provenance"]["original_camera_byte_checks"] = len(found) * 3
        indexed = {r["decision_id"]: r for r in rows if r["seed"] == seed}
        for decision in run["decisions"]:
            row = indexed[decision["id"]]
            decision["payload"]["evidence"] = json.dumps({
                "producer": "public-coordinate teacher; NOT a model prediction",
                "training_target": row["target"],
                "decoded_action": row["decoded_action"],
                "raw_teacher_command": row["teacher_command"],
                "terminal_evidence": row["terminal_evidence"],
                "student_prompt": row["prompt"],
            }, indent=2)
        runs.append(run)

    report_dir.mkdir(parents=True, exist_ok=True)
    data = {"schema": 1, "runs": runs, "sources": {}}
    (report_dir / "teacher_flights.html").write_text(html_document(data), encoding="utf-8")
    summary = {
        "kind": KINDS,
        "dataset": str(root),
        "seeds": sorted(seeds),
        "samples": len(rows),
        "teacher_labels_recomputed_from_public_inputs": teacher_checks,
        "exact_replayed_controls_and_poses": pose_checks,
        "labels_to_executed_control_checks": execution_checks,
        "exact_original_image_checks": source_checks,
        "hold_samples": dict(holds),
        "terminal_samples": dict(stops),
        "identical_mosaic_hashes_across_splits": sum(len(s) > 1 for s in image_splits.values()),
        "samples_by_split": manifest["samples_by_split"],
        "model_predictions": 0,
        "training_runs": 0,
        "no_held_out_or_pilot_eval_seeds": True,
        "source_image_and_control_alignment_passed": True,
        "overfit_fixture_eligible": True,
        "general_vla_training_ready": False,
        "limits": [
            "public-coordinate task solvable from odometry alone",
            "no semantic/visual/language generalization evidence",
            "simulator-only, no real or external-simulator data",
        ],
        "horizon_s": HORIZON_S,
        "per_episode": [
            {"name": r["name"], "success": r["result"]["success"], "replay": r["provenance"]}
            for r in runs
        ],
    }
    (report_dir / "fixture_audit.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(audit(args.data, args.out))
    print(json.dumps({k: v for k, v in result.items() if k != "per_episode"}, indent=2))
