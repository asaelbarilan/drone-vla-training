"""D155: plot training and held-out loss for a UAV-Flow run.

Held-out loss is the point of the plot. Training loss alone cannot show
overfitting, and with 308 training episodes overfitting is the expected failure,
so a run whose report carries no held-out series is labelled as such on the figure
rather than quietly plotted as if it were complete.
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def smooth(values, window=20):
    out, run = [], []
    for v in values:
        run.append(v)
        if len(run) > window:
            run.pop(0)
        out.append(sum(run) / len(run))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads((args.run / "report.json").read_text(encoding="utf-8"))
    losses = report["losses"]
    held = report.get("held_out") or []

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(range(1, len(losses) + 1), losses, color="#b5d4f4", linewidth=0.8, label="train (raw)")
    ax.plot(
        range(1, len(losses) + 1),
        smooth(losses),
        color="#2a78d6",
        linewidth=2,
        label="train (20-update mean)",
    )
    if held:
        ax.plot(
            [h["step"] for h in held],
            [h["loss"] for h in held],
            color="#eb6834",
            linewidth=2,
            marker="o",
            markersize=4,
            label=f"held out ({report.get('held_out_examples', '?')} chunks)",
        )
    else:
        ax.text(
            0.5,
            0.92,
            "no held-out series in this run",
            transform=ax.transAxes,
            ha="center",
            color="#a32d2d",
            fontsize=11,
        )

    ax.set_xlabel("update")
    ax.set_ylabel("cross-entropy on action tokens")
    split = report.get("split", "?")
    ax.set_title(
        f"UAV-Flow action-token training - {split}\n"
        f"{report.get('train_examples', '?')} train chunks, "
        f"LoRA rank {report.get('recipe', {}).get('lora_rank', '?')}, "
        f"lr {report.get('recipe', {}).get('learning_rate', '?')}",
        fontsize=11,
    )
    ax.grid(alpha=0.25, linewidth=0.6)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=140)
    print(
        json.dumps(
            dict(
                updates=len(losses),
                first_loss=losses[0],
                last_loss=losses[-1],
                held_out_points=len(held),
                saved=str(args.out),
            )
        )
    )


if __name__ == "__main__":
    main()
