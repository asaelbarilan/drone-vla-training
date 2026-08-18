"""Look at the data before believing anything trained on it.

Every failure of the first behaviour-cloned policy was visible in the dataset
and invisible in the training curve: the velocity shortcut, the frames with no
target in them, the action distribution piled into a few bins. A loss going down
tells you the network fits the labels; it cannot tell you the labels were worth
fitting.

Produces two artefacts:

* a **contact sheet** — sampled frames with the expert's commanded action drawn
  on them, so "what did the teacher see and what did it do" is one glance;
* a **summary** — per-dimension action histograms, the correlation between the
  student's own state and the label (the copycat check), and the fraction of
  frames with no visible target.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ACTION_DIMS = ("vx", "vy", "vz", "yaw_rate")


def load(data_dir: Path) -> dict:
    data_dir = Path(data_dir)
    out = {
        "frames": np.load(data_dir / "frames.npy", mmap_mode="r"),
        "states": np.load(data_dir / "states.npy"),
        "actions": np.load(data_dir / "actions.npy"),
        "terminates": np.load(data_dir / "terminates.npy"),
    }
    manifest_path = data_dir / "manifest.json"
    out["manifest"] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return out


def contact_sheet(data_dir: Path, out_path: Path, rows: int = 6, cols: int = 8) -> Path:
    """Evenly spaced samples across the whole dataset, action drawn on each.

    Evenly spaced rather than random: a random sample of a dataset built from
    concatenated episodes over-represents whichever episodes are longest, which
    are the ones that meandered.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = load(data_dir)
    frames, states, actions = d["frames"], d["states"], d["actions"]
    n = rows * cols
    idx = np.linspace(0, len(frames) - 1, n).astype(int)

    fig, axes = plt.subplots(rows, cols, figsize=(cols * 1.7, rows * 1.9))
    fig.patch.set_facecolor("#111318")
    for ax, i in zip(axes.ravel(), idx, strict=True):
        ax.imshow(np.asarray(frames[i]))
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color("#3a3f4b")

        vx, vy, vz, yaw_rate = (float(v) for v in actions[i])
        h, w = frames[i].shape[:2]
        # The commanded horizontal velocity is in world ENU; rotate it into the
        # body frame so the arrow means "where the vehicle was told to go
        # relative to what the camera is looking at", which is the thing the
        # student has to learn. states[:, 3:5] are cos(yaw), sin(yaw).
        c, s = float(states[i][3]), float(states[i][4])
        fwd, left = vx * c + vy * s, -vx * s + vy * c
        scale = 22.0 / 5.0  # pixels per m/s, at 5 m/s cap
        ax.arrow(
            w / 2, h / 2, -left * scale, -fwd * scale,
            color="#ffd24a", width=1.4, head_width=5, length_includes_head=True,
        )
        speed = float(np.hypot(vx, vy))
        stop = " STOP" if d["terminates"][i] else ""
        ax.set_title(
            f"{speed:.1f} m/s  vz{vz:+.1f}  yr{yaw_rate:+.1f}{stop}",
            fontsize=6, color="#e6e8ee", pad=2,
        )
    fig.suptitle(
        f"{data_dir.name}  -  expert {d['manifest']['expert']}  -  "
        f"{d['manifest']['samples']} samples from {d['manifest']['episodes_kept']} episodes "
        f"(seeds {d['manifest']['seeds'][0]}-{d['manifest']['seeds'][1]})",
        color="#e6e8ee", fontsize=10,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def summary(data_dir: Path, out_path: Path | None = None) -> dict:
    """The numbers that decide whether this dataset can be cloned at all."""
    d = load(data_dir)
    states, actions, terminates = d["states"], d["actions"], d["terminates"]

    # The copycat check. If the student's own velocity predicts the label, a
    # network given that velocity will learn the shortcut and ignore the image.
    copycat = {}
    for j, dim in enumerate(ACTION_DIMS[:3]):
        a, b = states[:, j], actions[:, j]
        copycat[dim] = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0

    speeds = np.hypot(actions[:, 0], actions[:, 1])
    report = {
        "dataset": str(data_dir),
        "expert": d["manifest"]["expert"],
        "samples": int(len(actions)),
        "episodes": d["manifest"]["episodes_kept"],
        "seeds": d["manifest"]["seeds"],
        "own_velocity_vs_label_corr": copycat,
        "terminate_positive_rate": float(terminates.mean()),
        "horizontal_speed": {
            "mean": float(speeds.mean()),
            "p05": float(np.percentile(speeds, 5)),
            "p95": float(np.percentile(speeds, 95)),
            "frac_below_0.5_mps": float((speeds < 0.5).mean()),
        },
        "action_range": {
            dim: [float(actions[:, j].min()), float(actions[:, j].max())]
            for j, dim in enumerate(ACTION_DIMS)
        },
    }
    if out_path is not None:
        Path(out_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
