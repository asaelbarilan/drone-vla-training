"""D139 reproducible matched schedules, behavior metrics and comparable loss plots."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from run_smol_duration import metrics

from uavlab.training.mixed_batches import balanced_schedule, task_class


def summarize(report, rows):
    assert report["status"] == "complete" and report["updates"] == 400
    assert report["sample_exposures"] == 1600 and report["reload_spot_identical"]
    by_id = {r["decision_id"]: r for r in rows}
    condition_rows = (
        rows if report["condition"] == "expanded" else [r for r in rows if r["seed"] < 1450]
    )
    assert report["training_schedule"] == balanced_schedule(condition_rows, 400)
    assert len(report["losses"]) == 400
    for i, entry in enumerate(report["losses"]):
        assert entry["sample_ids"] == report["training_schedule"][i]
        assert set(entry["task_classes"]) == {"motion", "visual", "hold", "stop"}
        assert entry["gradient_norm"] > 0
        assert all(by_id[k]["split"] == "train" for k in entry["sample_ids"])
    assert [r["decision_id"] for r in report["after"]] == report["generation_eval_ids"]
    assert [r["decision_id"] for r in report["before"]] == report["generation_eval_ids"]
    assert [r["decision_id"] for r in report["extra_after"]] == report["extra_eval_ids"]
    original = metrics(report["after"])
    extra = report["extra_after"]
    new = [r for r in extra if r["seed"] >= 1450]
    all_predictions = report["after"] + extra
    assert len(set(r["decision_id"] for r in all_predictions)) == len(all_predictions)
    assert all(by_id[r["decision_id"]]["split"] == "val" for r in all_predictions)

    def correct(r):
        return (
            r["valid"]
            and not r["parsed"]["stop"]
            and all(r["parsed"][k] == 32 for k in ("forward_bin", "right_bin", "down_bin"))
            and (r["parsed"]["yaw_cw_bin"] - 32) * (r["target"]["yaw_cw_bin"] - 32) > 0
        )

    pairs = {}
    for name, preds in (("original", report["after"]), ("new", new)):
        visual = {r["decision_id"]: r for r in preds if r["task_group"] == "visual"}
        instruction = []
        swap = []
        for identity, r in visual.items():
            row = by_id[identity]
            if row["instruction_colour"] == "red":
                other = f"visible_yaw_s{row['seed']}_l{row['layout']}_blue"
                instruction.append(correct(r) and correct(visual[other]))
            if row["layout"] % 2 == 0:
                other = (
                    f"visible_yaw_s{row['seed']}_l{row['layout'] + 1}_{row['instruction_colour']}"
                )
                swap.append(correct(r) and correct(visual[other]))
        pairs[name] = dict(
            instruction_correct=sum(instruction),
            instruction_total=len(instruction),
            color_swap_correct=sum(swap),
            color_swap_total=len(swap),
        )
    boundaries = {}
    for group in ("stop", "hold", "motion", "visual"):
        selected = [r for r in all_predictions if task_class(by_id[r["decision_id"]]) == group]
        boundaries[group] = dict(
            n=len(selected),
            valid=sum(r["valid"] for r in selected),
            exact=sum(r["exact"] for r in selected),
            predicted_stop=sum(r["valid"] and r["parsed"]["stop"] for r in selected),
        )
    perturb = {}
    reference = {r["decision_id"]: r for r in report["after"]}
    for kind in ("blank_image", "blank_instruction"):
        items = [r for r in report["interventions"] if r["intervention"] == kind]
        assert len(items) == 16
        perturb[kind] = dict(
            constrained_correct=sum(correct(r) for r in items),
            raw_changed=sum(r["raw"] != reference[r["decision_id"]]["raw"] for r in items),
        )
    terminal = [r for r in report["after"] if r["target"]["stop"]]
    assert len(terminal) == 2
    before = metrics(report["before"])
    old_gate = (
        sum(r["valid"] for r in report["after"]) >= 27
        and original["visual"]["correct_yaw_without_translation_or_stop"] >= 12
        and all(r["exact"] for r in terminal)
        and original["coordinate"]["mean_bin_error"] <= 0.8 * before["coordinate"]["mean_bin_error"]
    )
    new_metrics = metrics(new)
    return dict(
        condition=report["condition"],
        original=original,
        new=new_metrics,
        pairs=pairs,
        boundaries=boundaries,
        interventions=perturb,
        old_pilot_gate=old_gate,
        combined_pilot_gate=old_gate
        and new_metrics["visual"]["correct_yaw_without_translation_or_stop"] >= 48,
        wall_seconds=report["wall_seconds"],
        peak_allocated_bytes=report["peak_allocated_bytes"],
        unique_training_exposures=len(set(k for b in report["training_schedule"] for k in b)),
        schedules_checked=True,
        reload_spot_identical=True,
    )


def loss_points(report, cohort, split, group="all"):
    points = [dict(step=0, measurements=report["initial_losses"]), *report["comparable_losses"]]
    return [
        (
            p["step"],
            next(
                v for v in p["measurements"][cohort] if v["split"] == split and v["group"] == group
            ),
        )
        for p in points
    ]


def main(args):
    args.out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(s) for s in (args.data / "index.jsonl").read_text().splitlines()]
    reports = {
        name: json.loads((path / "report.json").read_text())
        for name, path in (("existing_control", args.control), ("expanded", args.expanded))
    }
    a, b = reports.values()
    manifest = json.loads((args.data / "manifest.json").read_text())
    assert a["generation_eval_ids"] == manifest["generation_eval_ids"]
    assert a["initial_adapter_sha256"] == b["initial_adapter_sha256"]
    assert a["data_sha256"] == b["data_sha256"]
    assert a["generation_eval_ids"] == b["generation_eval_ids"]
    assert a["extra_eval_ids"] == b["extra_eval_ids"]
    assert [r["raw"] for r in a["before"]] == [r["raw"] for r in b["before"]]
    summary = {name: summarize(report, rows) for name, report in reports.items()}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    for name, report in reports.items():
        (args.out / f"{name}_report.json").write_text(json.dumps(report, indent=2))
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for col, cohort in enumerate(("original", "new_scenes")):
        for row, field in enumerate(("weighted_action_loss", "answer_ce")):
            ax = axes[row, col]
            for name, report in reports.items():
                pts = loss_points(report, cohort, "val")
                ax.plot([p[0] for p in pts], [p[1][field] for p in pts], marker="o", label=name)
            ax.set(
                title=f"{cohort} VAL: {field}",
                xlabel="Optimizer updates (4 examples each)",
                ylabel="Loss",
            )
            ax.grid(alpha=0.25)
            ax.legend()
    fig.suptitle("Matched batch balance: original versus expanded data | fixed step400 endpoint")
    fig.savefig(args.out / "validation_loss_curves.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(2, 4, figsize=(16, 7), layout="constrained")
    for i, cohort in enumerate(("original", "new_scenes")):
        for j, group in enumerate(("visual", "motion", "hold", "stop")):
            ax = axes[i, j]
            for name, report in reports.items():
                pts = loss_points(report, cohort, "val", group)
                ax.plot(
                    [p[0] for p in pts],
                    [p[1]["weighted_action_loss"] for p in pts],
                    marker="o",
                    label=name,
                )
            ax.set(
                title=f"{cohort} VAL {group} (n={pts[0][1]['n']})",
                xlabel="Updates",
                ylabel="Weighted loss",
            )
            ax.grid(alpha=0.25)
    axes[0, 0].legend()
    fig.savefig(args.out / "task_loss_curves.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    for name, report in reports.items():
        pts = loss_points(report, "original", "train")
        if name == "expanded":
            other = loss_points(report, "new_scenes", "train")
            ys = [
                (
                    a[1]["weighted_action_loss"] * a[1]["n"]
                    + b[1]["weighted_action_loss"] * b[1]["n"]
                )
                / (a[1]["n"] + b[1]["n"])
                for a, b in zip(pts, other, strict=True)
            ]
        else:
            ys = [p[1]["weighted_action_loss"] for p in pts]
        ax.plot([p[0] for p in pts], ys, marker="o", label=name)
    ax.set(
        title="Eval-mode loss on each condition's own TRAIN set (different populations)",
        xlabel="Optimizer updates",
        ylabel="Weighted action loss",
    )
    ax.grid(alpha=0.25)
    ax.legend()
    fig.savefig(args.out / "training_loss_curves.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("data", "control", "expanded", "out"):
        p.add_argument("--" + key, type=Path, required=True)
    main(p.parse_args())
