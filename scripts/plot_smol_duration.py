"""Comparable full-split loss curves for D137 (never online TRAIN versus VAL)."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

p = argparse.ArgumentParser()
p.add_argument("--reports", type=Path, required=True)
a = p.parse_args()
models = [
    (n, json.loads((a.reports / f"{n}_duration_report.json").read_text()))
    for n in ("smol256", "smol500")
    if (a.reports / f"{n}_duration_report.json").exists()
]
assert models
for filename, minimum_step in (
    ("duration_loss_curves.png", 400),
    ("duration_full_loss_curves.png", 0),
):
    fig, axes = plt.subplots(
        len(models), 2, figsize=(12, 4 * len(models)), squeeze=False, constrained_layout=True
    )
    for i, (name, r) in enumerate(models):
        for col, (metric, label) in enumerate(
            (
                ("weighted_action_loss", "Weighted action loss"),
                ("answer_ce", "Ordinary answer-token CE"),
            )
        ):
            ax = axes[i, col]
            for split, color in (("train", "#246eaa"), ("val", "#b45b2e")):
                points = [
                    (v["step"], m[metric])
                    for v in r["comparable_losses"]
                    for m in v["measurements"]
                    if m["split"] == split and m["group"] == "all" and v["step"] >= minimum_step
                ]
                ax.plot(*zip(*points, strict=False), marker="o", color=color, label=split.upper())
            ax.set(title=f"{name}: {label}", xlabel="Total optimizer updates", ylabel=label)
            ax.grid(alpha=0.2)
            ax.legend()
    fig.suptitle(
        "Same loss definition, evaluation mode, all 252 TRAIN / 84 VAL examples\n"
        "Fixed data and recipe; 256M continues its preserved step-400 adapter"
    )
    fig.savefig(a.reports / filename, dpi=150)
    plt.close(fig)
fig, axes = plt.subplots(
    len(models), 4, figsize=(16, 4 * len(models)), squeeze=False, constrained_layout=True
)
for i, (name, r) in enumerate(models):
    for col, group in enumerate(("visual", "motion", "hold", "stop")):
        ax = axes[i, col]
        for split, color in (("train", "#246eaa"), ("val", "#b45b2e")):
            points = [
                (v["step"], m["weighted_action_loss"])
                for v in r["comparable_losses"]
                for m in v["measurements"]
                if m["split"] == split and m["group"] == group
            ]
            ax.plot(*zip(*points, strict=False), marker="o", color=color, label=split.upper())
        sizes = {
            m["split"]: m["n"]
            for m in r["comparable_losses"][0]["measurements"]
            if m["group"] == group
        }
        ax.set(
            title=f"{name}: {group} ({sizes['train']} train / {sizes['val']} val)",
            xlabel="Updates",
            ylabel="Weighted action loss",
        )
        ax.grid(alpha=0.2)
        ax.legend()
fig.suptitle("Separate task losses (same evaluation-mode objective for TRAIN and VAL)")
fig.savefig(a.reports / "duration_task_losses.png", dpi=150)
