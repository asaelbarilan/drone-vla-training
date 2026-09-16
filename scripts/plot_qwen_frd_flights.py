"""Matched per-scene goal error; descriptive diagnostics, no population inference."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path("D:/drone_vla_pilot/runs/qwen_frd_comparison_20260916_a")
fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained", sharey=True)
for ax, seed in zip(axes, (1400, 1405), strict=True):
    for mode, color in [("zero_shot", "#687789"), ("trained", "#1660ad")]:
        folder = root / f"qwen_frd_{mode}_s{seed}"
        calls = [json.loads(p.read_text()) for p in sorted((folder / "debug/calls").glob("*.json"))]
        result = json.loads((folder / "result.json").read_text())
        times = [c["requested_t_sim_ns"] / 1e9 for c in calls] + [result["sim_duration_s"]]
        errors = [c["evaluation_only"]["public_goal_error_m"] for c in calls] + [
            result["metrics"]["distance_to_goal_m"]
        ]
        ax.plot(times, errors, label=mode.replace("_", " "), color=color)
        ax.scatter(
            times[-1],
            errors[-1],
            marker="*" if result["success"] else "x",
            s=65,
            color=color,
            zorder=5,
        )
    ax.axhline(0.35, color="#b56626", ls=":", label="Goal radius (STOP also needs low speed)")
    ax.set(
        xlabel="Simulated seconds (inference paused)",
        ylabel="Distance to goal (m)",
        title=f"Validation scene {seed}",
        xlim=(0, 10),
        ylim=(0, 10),
    )
    ax.grid(alpha=0.2)
axes[0].legend(fontsize=7)
fig.suptitle(
    "Two-scene diagnostic: zero-shot 0/2 completed; tiny adapter 1/2\n"
    "Not a reliability estimate or real-time flight result",
    fontsize=11,
)
fig.savefig("reports/vla_frd_followup_20260916/flight_comparison.png", dpi=150)
fig.savefig("reports/vla_frd_followup_20260916/flight_comparison.svg")
