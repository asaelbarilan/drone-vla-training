"""Convert audited FLU fixture labels to FRD without changing physical actions."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from uavlab.contracts import ControlCommand
from uavlab.training import direct_vla_contract as flu
from uavlab.training import direct_vla_frd as frd


def convert(source: Path, out: Path, report: Path):
    source = source.resolve()
    out = out.resolve()
    if out.exists() or out == source:
        raise FileExistsError("new dataset directory required")
    manifest = json.loads((source / "manifest.json").read_text())
    assert manifest["contract"] == flu.CONTRACT_ID
    source_hash = hashlib.sha256((source / "index.jsonl").read_bytes()).hexdigest()
    pinned = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "reports/vla_local_pilot_20260916/fixture_hashes.json"
        ).read_text()
    )
    assert source_hash == pinned["index.jsonl"], "source differs from audited fixture"
    rows = [json.loads(x) for x in (source / "index.jsonl").read_text().splitlines()]
    assert {r["seed"] for r in rows} == set(range(1400, 1408))
    out.mkdir(parents=True)
    converted, checks = [], 0
    for row in rows:
        assert row["split"] == ("val" if row["seed"] % 5 == 0 else "train")
        old = flu.parse_target(json.dumps(row["target"]))
        new = frd.target_from_command(
            ControlCommand.model_validate(row["teacher_command"]),
            row["state"]["yaw_enu_rad"],
            terminal=old.stop,
        )
        assert new == frd.from_flu(old)
        assert frd.action_from_target(
            new, row["state"]["yaw_enu_rad"], duration_s=0.2
        ) == flu.action_from_target(old, row["state"]["yaw_enu_rad"], duration_s=0.2)
        for camera, relative in row["images"].items():
            original, target = source / relative, out / relative
            assert original.resolve().is_relative_to(source) and target.resolve().is_relative_to(
                out
            )
            assert hashlib.sha256(original.read_bytes()).hexdigest() == row["image_sha256"][camera]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            assert hashlib.sha256(target.read_bytes()).hexdigest() == row["image_sha256"][camera]
            checks += 1
        converted.append(
            {
                **row,
                "contract": frd.CONTRACT_ID,
                "source_target_flu": row["target"],
                "target": json.loads(frd.target_json(new)),
                "prompt": frd.student_prompt(row["instruction"], row["state"]),
            }
        )
    (out / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in converted))
    result = {
        "source": str(source),
        "source_contract": flu.CONTRACT_ID,
        "contract": frd.CONTRACT_ID,
        "source_index_sha256": source_hash,
        "index_sha256": hashlib.sha256((out / "index.jsonl").read_bytes()).hexdigest(),
        "samples": len(rows),
        "exact_action_equivalence_checks": len(rows),
        "unchanged_image_checks": checks,
        "samples_by_split": manifest["samples_by_split"],
        "source_run_logs": "Original dataset/runs: FLU provenance, not FRD execution logs",
        "seed_split_unchanged": True,
        "training_gate": "tiny overfit only; not general training data",
    }
    manifest.pop("episodes", None)
    manifest.pop("swift_image_root", None)
    manifest.update(
        format="direct_velocity_public_goal_fixture_frd_v2",
        contract=frd.CONTRACT_ID,
        source_dataset=str(source),
        source_index_sha256=source_hash,
        conversion=result,
        training_ready=False,
        pending=["FRD overfit gate", "visual/multi-task/real/sim expansion"],
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    assert hashlib.sha256((source / "index.jsonl").read_bytes()).hexdigest() == source_hash
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    convert(args.source, args.out, args.report)
