"""D139 sequential saved-action and matched-flight evaluation of completed runs."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path("D:/drone_vla_pilot")
REPORTS = Path("reports/vla_balanced_comparison_20260917")
VIEWER = Path("reports/vla_dataset_review_20260916")
CONDITIONS = {
    "existing_control": "smol256_balanced_control_20260917_a",
    "expanded": "smol256_balanced_expanded_20260917_a",
}


def run(script, *args):
    env = dict(os.environ, PYTHONPATH="src", USE_TF="0")
    subprocess.run([sys.executable, "scripts/" + script, *map(str, args)], env=env, check=True)


def main():
    reports = {
        k: json.loads((BASE / "runs" / v / "report.json").read_text())
        for k, v in CONDITIONS.items()
    }
    assert all(r["status"] == "complete" and r["reload_spot_identical"] for r in reports.values())
    assert len({r["initial_adapter_sha256"] for r in reports.values()}) == 1
    for name, folder in CONDITIONS.items():
        report = BASE / "runs" / folder / "report.json"
        visual = BASE / "runs" / f"{folder}_visual"
        run(
            "execute_saved_visual_predictions.py",
            "--report",
            report,
            "--data",
            BASE / "data/visible_yaw_pairs_20260916_v3",
            "--out",
            visual,
        )
        raw = visual / "execution.json"
        augmented = json.loads(raw.read_text())
        augmented.update(
            output_root=str(visual),
            raw_execution_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        )
        target = REPORTS / f"{name}_visual_execution.json"
        target.write_text(json.dumps(augmented, indent=2))
        run(
            "audit_saved_visual_execution.py",
            "--report",
            target,
            "--out",
            REPORTS / f"{name}_visual_audit.json",
        )
        flights = BASE / "runs" / f"{folder}_flights"
        run(
            "evaluate_local_vla_pair.py",
            "--model",
            "smol256",
            "--label",
            "mixed",
            "--data",
            BASE / "data/public_goal_fixture_20260916_v1",
            "--adapter",
            BASE / "runs" / folder / "adapter_s400",
            "--out",
            flights,
        )
        run(
            "audit_local_vla_pair.py",
            "--runs",
            flights,
            "--out",
            REPORTS / f"{name}_flight_audit.json",
        )
        shutil.copyfile(flights / "summary.json", REPORTS / f"{name}_flight_summary.json")
        page = (
            "balanced_control_flights.html"
            if name == "existing_control"
            else "balanced_expanded_flights.html"
        )
        shutil.copyfile(flights / "model_flights.html", VIEWER / page)
        print(json.dumps(dict(condition=name, status="flights_audited", page=page)), flush=True)
    run(
        "summarize_balanced_comparison.py",
        "--data",
        BASE / "data/local_expanded_20260917_v4",
        "--control",
        BASE / "runs" / CONDITIONS["existing_control"],
        "--expanded",
        BASE / "runs" / CONDITIONS["expanded"],
        "--out",
        REPORTS,
    )
    run(
        "build_balanced_comparison_review.py",
        "--data",
        BASE / "data/local_expanded_20260917_v4",
        "--reports",
        REPORTS,
        "--out",
        VIEWER / "balanced_comparison.html",
    )


if __name__ == "__main__":
    main()
