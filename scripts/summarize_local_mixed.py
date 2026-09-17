"""Summarize fixed mixed-local predictions without selecting checkpoints or tuning."""

import argparse
import json
import statistics
from pathlib import Path

from run_local_mixed_vla import metrics


def summarize(report, expected_updates=400):
    assert report["status"] == "complete" and report["updates"] == expected_updates
    after = report["after"]
    visual = [r for r in after if r["task_group"] == "visual"]
    by_id = {r["decision_id"]: r for r in visual}

    def credit(r):
        p = r["parsed"]
        return bool(
            r["valid"]
            and not p["stop"]
            and all(p[k] == 32 for k in ("forward_bin", "right_bin", "down_bin"))
            and (p["yaw_cw_bin"] - 32) * (r["target"]["yaw_cw_bin"] - 32) > 0
        )

    instruction_pairs = image_pairs = 0
    for seed in (1410, 1415):
        for layout in range(4):
            instruction_pairs += all(
                credit(by_id[f"visible_yaw_s{seed}_l{layout}_{c}"]) for c in ("red", "blue")
            )
        for layout in (0, 2):
            for c in ("red", "blue"):
                image_pairs += all(
                    credit(by_id[f"visible_yaw_s{seed}_l{layout_index}_{c}"])
                    for layout_index in (layout, layout + 1)
                )
    interventions = {}
    for kind in ("blank_image", "blank_instruction"):
        rows = [
            {**r, "task_group": "visual"}
            for r in report["interventions"]
            if r["intervention"] == kind
        ]
        interventions[kind] = metrics(rows)["visual"]
        interventions[kind]["predictions_changed"] = sum(
            r["parsed"] != by_id[r["decision_id"]]["parsed"] for r in rows
        )
    return dict(
        model=report["model"],
        before=report["before_metrics"],
        after=report["after_metrics"],
        criteria_passed=report["pilot_criteria_passed"],
        both_instructions_correct_pairs=f"{instruction_pairs}/8",
        both_color_swaps_correct_pairs=f"{image_pairs}/8",
        interventions=interventions,
        median_after_latency_s=statistics.median(r["latency_s"] for r in after),
        optimization_seconds=sum(report["optimization_seconds"]),
        peak_allocated_bytes=report["peak_allocated_bytes"],
        reload_spot_identical=report["reload_spot_identical"],
        validation_loss=report["validation_loss"],
        limits=(
            "28 fixed generation examples; all84 validation rows for CE. "
            "2visual+2coordinate validation scene groups; no real-world transfer claim."
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = summarize(json.loads(a.report.read_text()))
    a.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
