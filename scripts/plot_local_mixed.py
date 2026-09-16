"""Separate per-model weighted TRAIN objective and unweighted validation CE plots."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("--reports", type=Path, required=True)
a = p.parse_args()
fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
for index, model in enumerate(("smol256", "qwen")):
    report = json.loads((a.reports / f"{model}_mixed_report.json").read_text())
    losses = json.loads((a.reports / f"{model}_mixed_losses.json").read_text())
    y = np.array([r["loss"] for r in losses])
    x = np.arange(1, len(y) + 1)
    ax = axes[index, 0]
    ax.plot(x, y, color="#2963a5", alpha=0.25, label="Single example")
    ax.plot(
        x[31:],
        np.convolve(y, np.ones(32) / 32, mode="valid"),
        color="#164b8c",
        label="32-update mean",
    )
    ax.axvline(200.5, color="#b66a24", ls="--")
    ax.set(
        title=f"{model}: weighted TRAIN objective",
        xlabel="Optimizer updates",
        ylabel="Loss (log scale)",
        yscale="log",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    ax = axes[index, 1]
    v = report["validation_loss"]
    ax.plot([r["step"] for r in v], [r["mean_answer_ce"] for r in v], marker="o", color="#9651a0")
    ax.set(
        title=f"{model}: held-out answer-token CE (84 examples)",
        xlabel="Optimizer updates",
        ylabel="Mean per-example CE",
    )
    ax.grid(alpha=0.2)
fig.suptitle(
    "Same252TRAIN examples and400-update schedule | 84VAL examples\n"
    "Native tokenizers and BF16/NF4 differ; loss values are not a model-ranking score.",
    fontsize=12,
)
fig.savefig(a.reports / "mixed_loss_curves.png", dpi=150)
fig.savefig(a.reports / "mixed_loss_curves.svg")
