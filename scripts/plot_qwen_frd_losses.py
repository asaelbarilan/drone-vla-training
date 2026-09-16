"""Plot successive bounded retries; weighted objective is distinct from ordinary CE."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

root = Path("reports/vla_frd_followup_20260916")
rows = []
for attempt in ("b", "c"):
    rows += json.loads((root / f"frd_attempt_{attempt}_losses.json").read_text())
x = np.arange(1, len(rows) + 1)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
for ax, key, title in zip(
    axes,
    ("loss", "unweighted_token_loss"),
    ("Value-weighted training objective", "Ordinary answer-token cross entropy"),
    strict=True,
):
    y = np.array([r[key] for r in rows])
    ax.plot(x, y, alpha=0.25, color="#2464ac", label="Single example")
    smooth = np.convolve(y, np.ones(16) / 16, mode="valid")
    ax.plot(x[15:], smooth, color="#123f76", label="16-update rolling mean")
    ax.axvline(200.5, color="#c15c19", ls="--", label="Resume; LR 2e-4 to 5e-5")
    ax.set_yscale("log")
    ax.set(xlabel="Cumulative FRD update", ylabel="Loss (log scale)", title=title)
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
fig.suptitle(
    "16 fixed TRAIN examples | 13/16 exact at 200 updates; 16/16 at 400\n"
    "Training memorization only; no validation loss shown",
    fontsize=12,
)
fig.savefig(root / "frd_losses.png", dpi=150)
fig.savefig(root / "frd_losses.svg")
