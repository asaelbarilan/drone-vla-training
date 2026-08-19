"""Render an episode to video, so a run can be judged by eye.

Every number this repository reports is a summary. "Success 0.33" does not say
whether the vehicle flew a sensible route and stopped a metre short, or spiralled
into a wall and got lucky twice. A person should be able to look at a run and
disagree with the label, and until this existed they could not.

Two panels, because neither alone is enough:

* **Left, plan view** — where the vehicle actually went. Obstacles, the target,
  the distractors, the geofence, and the path so far. This is the view that
  makes "it never went near the goal" or "it circled the wrong tower" obvious.
* **Right, what the policy saw** — the rendered camera frame, for the vision
  configurations. A drone that flies past a target which was never in frame is a
  perception result; one that flies past a target filling the frame is a policy
  result, and the plan view alone cannot tell them apart.

The overlay carries the numbers that decide the verdict — distance to goal,
speed, elapsed time, and the termination reason once known — so nothing has to
be cross-referenced against a table while watching.

Deliberately not part of the metrics path. This module is for looking at, and
nothing that scores a run may import it.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

PANEL = 560
"""Side of each panel in pixels. Two panels plus a margin gives a 1140x600 frame."""

MARGIN = 20
BAR_H = 62

# Colours are BGR, because that is what OpenCV writes.
BG = (24, 22, 20)
INK = (232, 230, 226)
DIM = (120, 116, 110)
PATH = (70, 190, 250)   # amber
TARGET = (60, 60, 220)
DISTRACTOR = (90, 180, 90)
OBSTACLE = (78, 74, 70)
DRONE = (120, 220, 255)  # pale amber
FENCE = (60, 58, 56)
GOOD = (110, 200, 110)
BAD = (90, 90, 235)


@dataclass(slots=True)
class Sample:
    """One captured instant. Everything the plan view needs, and nothing else."""

    t_s: float
    position: np.ndarray
    yaw: float
    speed: float
    distance_to_goal: float
    collided: bool
    frame: Any | None = None


@dataclass(slots=True)
class Scene:
    """The static parts of the episode, captured once at reset."""

    obstacles: list[tuple[np.ndarray, np.ndarray]] = field(default_factory=list)
    landmarks: list[tuple[np.ndarray, str, bool]] = field(default_factory=list)
    goal: np.ndarray = field(default_factory=lambda: np.zeros(3))
    geofence_m: float = 60.0
    goal_radius_m: float = 2.0


class _Projector:
    """World metres -> panel pixels, with a fixed scale for the whole episode.

    Fixed rather than auto-fitted per frame: a view that rescales as the vehicle
    moves makes a straight line look curved and a stall look like progress.
    """

    def __init__(self, scene: Scene, samples: list[Sample]) -> None:
        points = [s.position[:2] for s in samples] + [scene.goal[:2]]
        points += [c[:2] for c, _ in scene.obstacles]
        points += [p[:2] for p, _, _ in scene.landmarks]
        stack = np.array(points, dtype=float)
        lo, hi = stack.min(axis=0), stack.max(axis=0)
        centre = (lo + hi) / 2.0
        # 1.35 rather than a snug fit: at 1.15 a target at the extreme of the
        # travelled area landed on the panel border and was half cut off.
        span = float(max((hi - lo).max(), 20.0)) * 1.35
        self.centre = centre
        self.scale = (PANEL - 2 * MARGIN) / span

    def __call__(self, xy: np.ndarray) -> tuple[int, int]:
        dx, dy = (np.asarray(xy, dtype=float)[:2] - self.centre) * self.scale
        # y is negated: world y grows north, image rows grow downward.
        return int(PANEL / 2 + dx), int(PANEL / 2 - dy)


def capture(arch, env_cfg, seed: int, stride: int = 4):
    """Run one episode, capturing what the plan view and the camera panel need.

    ``stride`` samples every Nth control tick. At 20 Hz control a stride of 4
    gives 5 samples per simulated second, which is smooth enough to watch and
    keeps a 90 s episode under 500 frames.
    """
    from uavlab.adapters.gym.deterministic_env import DeterministicEnv
    from uavlab.core.config import EpisodeSpec
    from uavlab.core.frame_store import global_store
    from uavlab.core.orchestrator import Orchestrator

    samples: list[Sample] = []
    scene = Scene()
    original_step = DeterministicEnv.step
    original_reset = DeterministicEnv.reset
    tick = 0

    async def capturing_reset(self, mission, seed_):
        packet = await original_reset(self, mission, seed_)
        scene.obstacles = [(o.center.copy(), o.half.copy()) for o in self.obstacles]
        scene.landmarks = [
            (lm.position.copy(), lm.label, bool(lm.is_target)) for lm in self.landmarks
        ]
        scene.goal = np.asarray(self.goal, dtype=float).copy()
        # From the mission, not the environment: the env bounds a rectangular
        # world, while the circle the vehicle is actually judged against is the
        # mission's geofence constraint.
        scene.geofence_m = float(mission.constraints.geofence_radius_m)
        scene.goal_radius_m = float(getattr(self, "goal_radius_m", 2.0))
        return packet

    async def capturing_step(self, command, dt_ns):
        nonlocal tick
        await original_step(self, command, dt_ns)
        if tick % stride == 0:
            status = self.status()
            image = None
            if getattr(self, "render", False):
                image = global_store().get(f"frame://{self._frame_ns}/rgb/{max(self._seq - 1, 0)}")
            samples.append(
                Sample(
                    t_s=self._t_ns / 1e9,
                    position=self.vehicle.position.copy(),
                    yaw=float(self.vehicle.yaw),
                    speed=float(np.linalg.norm(self.vehicle.velocity)),
                    distance_to_goal=float(status.distance_to_goal_m),
                    collided=bool(status.collided),
                    frame=image.copy() if image is not None else None,
                )
            )
        tick += 1

    DeterministicEnv.step = capturing_step
    DeterministicEnv.reset = capturing_reset
    try:
        result = asyncio.run(
            Orchestrator(
                arch, env_cfg, EpisodeSpec(episode_id=f"video_{arch.id}_{seed}", seed=seed)
            ).run()
        )
    finally:
        DeterministicEnv.step = original_step
        DeterministicEnv.reset = original_reset
    return result, scene, samples


def _plan_panel(scene: Scene, samples: list[Sample], upto: int, project: _Projector):
    import cv2

    panel = np.full((PANEL, PANEL, 3), BG, dtype=np.uint8)

    centre = project(np.zeros(2))
    cv2.circle(panel, centre, int(scene.geofence_m * project.scale), FENCE, 1)

    for c, h in scene.obstacles:
        a = project(c[:2] - h[:2])
        b = project(c[:2] + h[:2])
        cv2.rectangle(panel, (min(a[0], b[0]), min(a[1], b[1])),
                      (max(a[0], b[0]), max(a[1], b[1])), OBSTACLE, -1)

    for position, _, is_target in scene.landmarks:
        colour = TARGET if is_target else DISTRACTOR
        cv2.circle(panel, project(position[:2]), 7, colour, -1)

    goal_px = project(scene.goal[:2])
    cv2.circle(panel, goal_px, max(int(scene.goal_radius_m * project.scale), 4), TARGET, 2)

    trail = [project(s.position[:2]) for s in samples[: upto + 1]]
    if len(trail) > 1:
        cv2.polylines(panel, [np.array(trail, dtype=np.int32)], False, PATH, 2, cv2.LINE_AA)

    s = samples[upto]
    p = project(s.position[:2])
    nose = (int(p[0] + 15 * math.cos(s.yaw)), int(p[1] - 15 * math.sin(s.yaw)))
    cv2.line(panel, p, nose, DRONE, 2, cv2.LINE_AA)
    cv2.circle(panel, p, 7, BAD if s.collided else DRONE, -1)
    cv2.circle(panel, p, 7, BG, 1)

    cv2.putText(panel, "plan view", (MARGIN, PANEL - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, DIM, 1, cv2.LINE_AA)
    return panel


def _camera_panel(sample: Sample):
    import cv2

    panel = np.full((PANEL, PANEL, 3), BG, dtype=np.uint8)
    if sample.frame is None:
        cv2.putText(panel, "no camera in this configuration",
                    (MARGIN, PANEL // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, DIM, 1, cv2.LINE_AA)
        return panel
    rgb = np.asarray(sample.frame, dtype=np.uint8)
    side = PANEL - 2 * MARGIN
    resized = cv2.resize(rgb[:, :, ::-1], (side, side), interpolation=cv2.INTER_NEAREST)
    panel[MARGIN:MARGIN + side, MARGIN:MARGIN + side] = resized
    cv2.putText(panel, "what the policy saw", (MARGIN, PANEL - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, DIM, 1, cv2.LINE_AA)
    return panel


def render(arch, env_cfg, seed: int, out_path: Path, fps: int = 15, stride: int = 4) -> dict:
    """Run one episode and write it to an mp4. Returns a small summary."""
    import cv2

    result, scene, samples = capture(arch, env_cfg, seed, stride)
    if not samples:
        raise RuntimeError(f"{arch.id} produced no samples; did the episode start?")

    project = _Projector(scene, samples)
    width, height = PANEL * 2 + MARGIN, PANEL + BAR_H
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"could not open a video writer for {out_path}")

    verdict = "SUCCESS" if result.success else "FAILED"
    verdict_colour = GOOD if result.success else BAD
    try:
        for i, s in enumerate(samples):
            canvas = np.full((height, width, 3), BG, dtype=np.uint8)
            canvas[BAR_H:, :PANEL] = _plan_panel(scene, samples, i, project)
            canvas[BAR_H:, PANEL + MARGIN:] = _camera_panel(s)

            cv2.putText(canvas, f"{arch.id}  {arch.name}   seed {seed}", (MARGIN, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, INK, 1, cv2.LINE_AA)
            # Stats sit inside the plan panel rather than in the header, so they
            # cannot collide with a long architecture name or the verdict.
            stats = (f"t {s.t_s:5.1f}s    to goal {s.distance_to_goal:5.1f} m    "
                     f"speed {s.speed:4.1f} m/s")
            cv2.putText(canvas, stats, (MARGIN, BAR_H + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                        INK, 1, cv2.LINE_AA)
            # Legend along the header. It used to sit inside the plan panel and
            # covered the target whenever the target was in the bottom-left.
            x = MARGIN
            for colour, text in ((TARGET, "target"), (DISTRACTOR, "distractor"),
                                 (OBSTACLE, "obstacle"), (PATH, "path")):
                cv2.circle(canvas, (x + 5, BAR_H - 10), 5, colour, -1)
                cv2.putText(canvas, text, (x + 16, BAR_H - 6), cv2.FONT_HERSHEY_SIMPLEX,
                            0.38, DIM, 1, cv2.LINE_AA)
                x += 26 + 8 * len(text)
            # The verdict appears only in the closing moment, so the run can be
            # judged on what it did rather than read in the light of its label.
            if i >= len(samples) - 8:
                label = f"{verdict} - {result.termination_reason.value}"
                (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.putText(canvas, label, (width - tw - MARGIN, 26),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, verdict_colour, 2, cv2.LINE_AA)
            writer.write(canvas)
        # Hold the last frame so the verdict is readable rather than a flash.
        for _ in range(fps):
            writer.write(canvas)
    finally:
        writer.release()

    return {
        "architecture": arch.id,
        "seed": seed,
        "success": bool(result.success),
        "termination": result.termination_reason.value,
        "distance_to_goal_m": round(result.metrics.get("distance_to_goal_m", -1.0), 2),
        "path_length_m": round(result.metrics.get("path_length_m", 0.0), 2),
        "collisions": int(result.metrics.get("collisions", 0)),
        "frames": len(samples),
        "video": str(out_path),
    }
