"""Plot recorded pilot training loss, without inventing validation measurements."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/vla_local_pilot_20260916"
rows = [json.loads(x) for x in (REPORT / "qwen_losses.jsonl").read_text().splitlines()]
steps = np.array([r["step"] for r in rows])
loss = np.array([r["loss"] for r in rows])
assert len(rows) == 200 and np.array_equal(steps, np.arange(1, 201))
assert np.isfinite(loss).all()
# Trainer repeats four STOP, four HOLD, eight motion examples in fixed order.
cycles = loss[:192].reshape(12, 16)
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 5.3), gridspec_kw={"width_ratios": [1.5, 1]})
fig.patch.set_facecolor("#f8fafc")
for axis in (ax, bx):
    axis.set_facecolor("#ffffff")
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(alpha=0.17)
    axis.set_ylabel("Mean answer-token cross-entropy (lower is better)", fontsize=9)
ax.plot(
    steps, loss, color="#94a3b8", alpha=0.65, linewidth=1, label="Each update: one training example"
)
rolling = np.convolve(loss, np.ones(16) / 16, mode="valid")
ax.plot(steps[15:], rolling, color="#0369a1", linewidth=2.5, label="Trailing 16-update average")
ax.set(xlabel="Optimizer update", title="Recorded training loss", xlim=(1, 200), ylim=(0, None))
ax.legend(frameon=False, fontsize=9)
for label, span, color in [
    ("STOP (4 examples)", slice(0, 4), "#dc2626"),
    ("HOLD (4 examples)", slice(4, 8), "#0d9488"),
    ("Motion (8 examples)", slice(8, 16), "#7c3aed"),
]:
    bx.plot(
        np.arange(1, 13),
        cycles[:, span].mean(axis=1),
        marker="o",
        markersize=3,
        color=color,
        label=label,
    )
bx.set(
    xlabel="Complete pass through the same 16 examples",
    title="Training loss by example category",
    xlim=(1, 12),
    ylim=(0, None),
)
bx.legend(frameon=False, fontsize=9)
fig.suptitle(
    "Qwen 4B QLoRA · tiny overfit test · 16 examples, 200 updates",
    fontsize=15,
    fontweight="bold",
    y=0.98,
)
fig.text(
    0.05,
    0.065,
    "First / last 16-update means: 0.229 → 0.058. No validation-loss curve was recorded.",
    fontsize=11,
)
fig.text(
    0.05,
    0.025,
    "Final generated actions: 9/16 exact · STOP 0/4 · HOLD 4/4 · motion 5/8. "
    "Low token loss is not flight success.",
    fontsize=10,
    color="#9f1239",
)
fig.tight_layout(rect=(0, 0.11, 1, 0.93))
fig.savefig(REPORT / "loss_curves.png", dpi=150, facecolor=fig.get_facecolor())
fig.savefig(REPORT / "loss_curves.svg", facecolor=fig.get_facecolor())
plt.close(fig)
print(
    json.dumps(
        {
            "points": len(rows),
            "first_16_mean": float(loss[:16].mean()),
            "last_16_mean": float(loss[-16:].mean()),
            "complete_cycles": 12,
            "partial_final_cycle": 8,
            "validation_loss_available": False,
        }
    )
)
