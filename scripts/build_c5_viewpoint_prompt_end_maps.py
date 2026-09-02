"""Build static end maps for the C5 prompt-only viewpoint experiment."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from export_end_map_data import _scene, _trajectory
from matplotlib.patches import Circle, Rectangle

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    1060: ROOT / "runs/c5_shared_qwen_s1060_viewpoint_prompt_v1",
    1061: ROOT / "runs/c5_shared_qwen_s1061_viewpoint_prompt_v1",
    1062: ROOT / "runs/c5_shared_qwen_s1062_viewpoint_prompt_v1",
    1063: ROOT / "runs/c5_shared_qwen_s1063_viewpoint_prompt_v1",
}
OUTPUT = ROOT / "reports/paper_implementation/c5_viewpoint_prompt_end_maps.png"


def _last_sim_time(events_path: Path) -> float:
    last = 0
    for line in events_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        last = max(last, int(event["t_sim_ns"]))
    return last / 1e9


def _record(seed: int, run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    scene = _scene(manifest, seed)
    path = _trajectory(run_dir / "events.jsonl", stride=10)
    result_path = run_dir / "result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        end = [
            float(result["status"]["position"]["x"]),
            float(result["status"]["position"]["y"]),
        ]
        if not path or math.dist(path[-1], end) > 1e-3:
            path.append(end)
        analysis_path = (
            ROOT
            / f"reports/paper_implementation/c5_s{seed}_viewpoint_prompt_v1_analysis.json"
        )
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        return {
            "seed": seed,
            "scene": scene,
            "path": path,
            "end": end,
            "status": "SUCCESS" if result["success"] else "TIMEOUT",
            "valid": True,
            "distance": float(result["metrics"]["distance_to_goal_m"]),
            "visible": int(analysis["visible_decision_frames"]),
            "frames": int(analysis["decision_frames"]),
            "sim_time": float(result["sim_duration_s"]),
        }
    end = path[-1]
    return {
        "seed": seed,
        "scene": scene,
        "path": path,
        "end": end,
        "status": "INTERRUPTED — INVALID",
        "valid": False,
        "distance": math.dist(end, scene["goal"]),
        "visible": None,
        "frames": None,
        "sim_time": _last_sim_time(run_dir / "events.jsonl"),
    }


def _bounds(record: dict) -> tuple[float, float, float, float]:
    scene = record["scene"]
    points = [[0.0, 0.0], scene["goal"], record["end"], *record["path"]]
    for obstacle in scene["obstacles"]:
        x, y = obstacle["center"]
        hx, hy = obstacle["half"]
        points.extend(([x - hx, y - hy], [x + hx, y + hy]))
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    pad = max(3.0, 0.08 * max(max(xs) - min(xs), max(ys) - min(ys)))
    return min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad


def main() -> None:
    records = [_record(seed, run_dir) for seed, run_dir in RUNS.items()]
    fig, axes = plt.subplots(2, 2, figsize=(12, 10), constrained_layout=True)
    fig.suptitle(
        "C5 OnFly — prompt-only best-viewpoint experiment",
        fontsize=16,
        fontweight="bold",
    )
    for ax, record in zip(axes.flat, records, strict=True):
        scene = record["scene"]
        for obstacle in scene["obstacles"]:
            center = obstacle["center"]
            half = obstacle["half"]
            ax.add_patch(
                Rectangle(
                    (center[0] - half[0], center[1] - half[1]),
                    2 * half[0],
                    2 * half[1],
                    facecolor="#d1d5db",
                    edgecolor="#6b7280",
                    linewidth=0.8,
                )
            )
        ax.add_patch(
            Circle(
                scene["goal"],
                scene["goalRadius"],
                facecolor="#dcfce7",
                edgecolor="#16a34a",
                linewidth=1.8,
            )
        )
        xs = [point[0] for point in record["path"]]
        ys = [point[1] for point in record["path"]]
        colour = "#16a34a" if record["status"] == "SUCCESS" else "#dc2626"
        if not record["valid"]:
            colour = "#d97706"
        ax.plot(xs, ys, color=colour, linewidth=2.2, zorder=3)
        ax.scatter([0], [0], color="#111827", s=35, zorder=5)
        ax.annotate("start", (0, 0), xytext=(5, 5), textcoords="offset points")
        ax.scatter(
            [scene["goal"][0]],
            [scene["goal"][1]],
            color="#16a34a",
            s=35,
            zorder=5,
        )
        ax.annotate(
            "goal",
            scene["goal"],
            xytext=(5, 5),
            textcoords="offset points",
        )
        ax.scatter(record["end"][0], record["end"][1], color=colour, s=48, zorder=5)
        visible = (
            "visibility unavailable"
            if record["visible"] is None
            else f"target visible {record['visible']}/{record['frames']} frames"
        )
        ax.set_title(f"Seed {record['seed']} — {record['status']}", fontweight="bold")
        ax.text(
            0.0,
            -0.17,
            (
                f"final {record['distance']:.1f} m · sim {record['sim_time']:.2f} s · "
                f"{visible}"
            ),
            transform=ax.transAxes,
            fontsize=9,
        )
        xmin, xmax, ymin, ymax = _bounds(record)
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("ENU x (m)")
        ax.set_ylabel("ENU y (m)")
        ax.grid(True, color="#e5e7eb", linewidth=0.6)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(OUTPUT)


if __name__ == "__main__":
    main()
