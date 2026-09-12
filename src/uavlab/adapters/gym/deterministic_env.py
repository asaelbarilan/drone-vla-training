"""A deterministic, in-process 3-D environment.

This is the fast screening substrate.  It has no renderer, no physics engine and
no dependencies beyond NumPy, so architecture logic can be exercised thousands
of times without CUDA, ROS, Gazebo or a network connection.  Fidelity is
deliberately low: it exists to make *architectural* differences visible —
timing, staleness, stopping correctness, safety interventions, recovery — not
to model aerodynamics.  Anything that survives here gets promoted to PX4/Gazebo
and Project AirSim, where the same architecture config runs unchanged.

The sensing model is the part that matters.  Field of view, range and occlusion
are enforced, so an architecture cannot succeed by knowing something it never
observed.  Ground truth exists only in :meth:`status`, which scores the episode
and is never visible to a policy.
"""

from __future__ import annotations

import hashlib
import itertools
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from uavlab.contracts import (
    CameraIntrinsics,
    ControlCommand,
    Frame,
    MissionSpec,
    ObservationPacket,
    SemanticHit,
    SensorRef,
    TaskFamily,
    Vec3,
    ns_to_s,
)
from uavlab.contracts.env_status import EnvironmentStatus
from uavlab.core.registry import register

_FRAME_NAMESPACE = itertools.count()


def _next_frame_namespace() -> int:
    """A namespace for this episode's frames that no later episode can reuse."""
    return next(_FRAME_NAMESPACE)


@dataclass(slots=True)
class Obstacle:
    """An axis-aligned box. Cheap to test, and enough to force real detours."""

    center: np.ndarray
    half: np.ndarray
    label: str = "obstacle"
    color: tuple[int, int, int] | None = None

    def distance(self, p: np.ndarray) -> float:
        delta = np.abs(p - self.center) - self.half
        outside = np.linalg.norm(np.maximum(delta, 0.0))
        inside = min(float(np.max(delta)), 0.0)
        return float(outside + inside)

    def intersects_segment(self, a: np.ndarray, b: np.ndarray, samples: int = 12) -> bool:
        return any(
            self.distance(a + (b - a) * t) <= 0.0
            for t in np.linspace(0.0, 1.0, samples)
        )


@dataclass(slots=True)
class Landmark:
    position: np.ndarray
    label: str
    is_target: bool = False
    is_lure: bool = False
    color: tuple[int, int, int] | None = None


@dataclass(slots=True)
class _Vehicle:
    position: np.ndarray
    velocity: np.ndarray
    yaw: float = 0.0


@dataclass(slots=True)
class _Injected:
    kind: str
    at_s: float
    params: dict[str, float] = field(default_factory=dict)
    fired: bool = False


@register("environment", "grid3d")
class DeterministicEnv:
    """Deterministic 3-D flight environment with FOV-limited semantic sensing."""

    def __init__(self, **params: Any) -> None:
        self.params = params
        self.world_size = np.array(params.get("world_size", [160.0, 160.0, 30.0]), dtype=float)
        """Kept comfortably larger than the mission geofence.

        Otherwise leaving the world would fire before leaving the geofence, and
        an architecture that a verifier or shield *should* have contained would
        be scored as an environment failure instead.
        """
        self.scene = str(params.get("scene", "clutter"))
        self.goal_distance_m = float(params.get("goal_distance_m", 35.0))
        self.n_obstacles = int(params.get("n_obstacles", 10))
        self.obstacle_span = tuple(params.get("obstacle_size_m", (2.0, 5.0)))
        self.drone_radius_m = float(params.get("drone_radius_m", 0.4))
        self.sensor_range_m = float(params.get("sensor_range_m", 18.0))
        self.fov_deg = float(params.get("fov_deg", 90.0))
        self.max_speed_mps = float(params.get("max_speed_mps", 5.0))
        self.accel_tau_s = float(params.get("accel_tau_s", 0.35))
        self.n_subgoals = int(params.get("subgoals", 0))
        self.n_lures = int(params.get("lures", 0))
        self.n_distractors = int(params.get("distractors", 3))
        self.target_label = str(params.get("target_label", "target"))
        self.occlusion_period_s = float(params.get("occlusion_period_s", 0.0))
        self.occlusion_duty = float(params.get("occlusion_duty", 0.4))
        self.detection_noise_m = float(params.get("detection_noise_m", 0.25))
        self.gate_gap_m = float(params.get("gate_gap_m", 3.0))
        self.n_rays = int(params.get("n_rays", 24))
        self.wind_mps = float(params.get("wind_mps", 0.0))
        self.allow_privileged = bool(params.get("allow_privileged", False))
        self._frame_ns = _next_frame_namespace()
        self.goal_radius_m = float(params.get("goal_radius_m", 2.0))
        self.subgoal_radius_m = float(params.get("subgoal_radius_m", 3.0))
        self.injections = [
            _Injected(
                kind=str(f.get("kind", "")),
                at_s=float(f.get("at_s", 0.0)),
                params={k: float(v) for k, v in dict(f.get("params", {})).items()},
            )
            for f in params.get("failures", [])
        ]

        self._rng = np.random.default_rng(0)
        self._t_ns = 0
        self._seq = 0
        self.vehicle = _Vehicle(np.zeros(3), np.zeros(3))
        self.obstacles: list[Obstacle] = []
        self.landmarks: list[Landmark] = []
        self.goal = np.zeros(3)
        self.subgoals: list[np.ndarray] = []
        self._subgoals_done = 0
        self._collided = False
        self._collision_count = 0
        self._out_of_bounds = False
        self._path_length = 0.0
        self._shortest = 0.0
        self._min_clearance = float("inf")
        self._constraint_violations = 0
        self._dropout_until_s = -1.0
        self._wind = np.zeros(3)
        self._task_family = TaskFamily.LONG_HORIZON_NAV
        self._start = np.zeros(3)
        self._lure_dwell_s = 0.0
        self._lure_radius_m = float(params.get("lure_radius_m", 3.0))
        self.block_lead_m = float(params.get("block_lead_m", 14.0))
        """How far ahead an injected blockage is staged. Must leave reaction room."""
        self.block_reaction_s = float(params.get("block_reaction_s", 1.2))
        self.block_margin_m = float(params.get("block_margin_m", 2.0))
        self._skipped_injections = 0
        self._injected_block_clearances: list[float] = []
        self.render = bool(params.get("render", False))
        """Produce real camera frames. Off by default: it costs ~1 ms/frame and
        the scripted-policy sweeps never look at an image."""
        self.render_depth = bool(params.get("render_depth", False))
        """Expose a calibrated depth-camera channel alongside RGB when enabled."""
        self.depth_renderer = str(params.get("depth_renderer", "legacy_corner"))
        if self.depth_renderer not in {"legacy_corner", "box_ray_v2"}:
            raise ValueError(f"Unknown depth renderer: {self.depth_renderer!r}")
        self.render_down = bool(params.get("render_down", False))
        """Render the ordinary downward RGB camera used by AeroVLA profiles."""
        self.coarse_goal_direction = bool(params.get("coarse_goal_direction", False))
        """Expose only a seven-way target-bearing bucket when the task declares it."""
        from uavlab.adapters.gym.render import Camera

        self._camera = Camera(
            width=int(params.get("image_size", 224)),
            height=int(params.get("image_size", 224)),
            fov_deg=float(params.get("fov_deg", 90.0)),
            pitch_rad=float(params.get("camera_pitch_rad", -0.15)),
        )
        self._down_camera = Camera(
            width=self._camera.width,
            height=self._camera.height,
            fov_deg=float(params.get("down_camera_fov_deg", 90.0)),
            pitch_rad=-math.pi / 2.0,
        )
        self._obs_centers = np.zeros((0, 3))
        self._obs_halves = np.zeros((0, 3))
        self._fan_cache: tuple[tuple[float, ...], tuple[float, ...]] | None = None
        self._fan_cache_seq = -1
        self._last_hits: tuple[SemanticHit, ...] = ()

    @property
    def name(self) -> str:
        return "grid3d"

    # -- scene construction -------------------------------------------------

    async def reset(self, mission: MissionSpec, seed: int) -> ObservationPacket:
        from uavlab.core.frame_store import global_store

        # A fresh namespace per episode, and an empty store to go with it.
        #
        # The URI used to be keyed on `id(self)`, an object address CPython
        # recycles as soon as the previous environment is collected. The store is
        # process-global and was never cleared, so a new episode could be handed
        # the *previous* episode's frame at the same URI - and the `_seq - 1`
        # lookups at the start of an episode are exactly where that bites.
        # It reproduced as a 1.4 mm divergence in c2g between two runs of the
        # same seed: deterministic, not noise. A monotonic counter cannot be
        # recycled, and clearing removes the stale entries either way.
        global_store().clear()
        self._frame_ns = _next_frame_namespace()
        self._rng = np.random.default_rng(seed)
        self._t_ns = 0
        self._seq = 0
        self._task_family = mission.task_family
        self.goal_radius_m = mission.success.goal_radius_m
        self._collided = False
        self._collision_count = 0
        self._out_of_bounds = False
        self._path_length = 0.0
        self._min_clearance = float("inf")
        self._constraint_violations = 0
        self._subgoals_done = 0
        self._dropout_until_s = -1.0
        self._wind = np.zeros(3)
        self._lure_dwell_s = 0.0
        self._skipped_injections = 0
        self._injected_block_clearances = []
        for inj in self.injections:
            inj.fired = False

        start = np.array([0.0, 0.0, 3.0])
        heading = float(self._rng.uniform(-math.pi, math.pi))
        self.goal = start + np.array(
            [
                self.goal_distance_m * math.cos(heading),
                self.goal_distance_m * math.sin(heading),
                float(self._rng.uniform(-1.0, 3.0)),
            ]
        )
        self.goal[2] = float(np.clip(self.goal[2], 2.0, self.world_size[2] - 2.0))
        self._start = start.copy()
        self._shortest = float(np.linalg.norm(self.goal - start))

        self.vehicle = _Vehicle(start.copy(), np.zeros(3), yaw=heading)
        self.obstacles = self._build_obstacles(start)
        self.landmarks = self._build_landmarks()
        self.subgoals = self._build_subgoals(start)
        self._rebuild_obstacle_arrays()
        self._fan_cache = None
        self._fan_cache_seq = -1
        self._last_hits = ()

        return await self.observe()

    def _build_obstacles(self, start: np.ndarray) -> list[Obstacle]:
        obstacles: list[Obstacle] = []
        direction = self.goal - start
        length = float(np.linalg.norm(direction))
        unit = direction / max(length, 1e-6)
        perp = np.array([-unit[1], unit[0], 0.0])

        if self.scene == "gate":
            # A narrow gap that only a high-rate controller threads cleanly.
            mid = start + unit * (length * 0.5)
            wall_half = np.array([1.2, 9.0, 8.0])
            offset = self.gate_gap_m / 2.0 + wall_half[1]
            for sign in (-1.0, 1.0):
                center = mid + perp * (sign * offset)
                center[2] = start[2]
                obstacles.append(Obstacle(center=center, half=wall_half.copy(), label="gate_wall"))

        if self.scene == "corridor":
            for i in range(1, 6):
                frac = i / 6.0
                center = start + unit * (length * frac)
                side = 1.0 if i % 2 == 0 else -1.0
                center = center + perp * (side * 4.5)
                center[2] = start[2]
                obstacles.append(
                    Obstacle(center=center, half=np.array([3.0, 3.0, 6.0]), label="corridor_wall")
                )

        n = (
            self.n_obstacles
            if self.scene in ("clutter", "corridor")
            else max(0, self.n_obstacles // 3)
        )
        attempts = 0
        while (
            len(obstacles) < n + (len(obstacles) if self.scene != "clutter" else 0)
            and attempts < 400
        ):
            attempts += 1
            along = float(self._rng.uniform(0.15, 0.9)) * length
            lateral = float(self._rng.normal(0.0, 6.0))
            center = start + unit * along + perp * lateral
            # Consume the historical height draw so existing seeds retain the
            # same horizontal layout and obstacle sizes.  The normalized local
            # sensor/planner stack is 2.5-D and its fidelity record declares
            # these boxes to be ground-attached vertical columns.  Letting a
            # random box float above the horizontal range fan created an
            # unsensed "ceiling" that a vertical waypoint could collide with.
            self._rng.uniform(1.5, min(8.0, self.world_size[2] - 2.0))
            size = float(self._rng.uniform(*self.obstacle_span))
            half = np.array([size / 2.0, size / 2.0, size])
            center[2] = half[2]
            candidate = Obstacle(center=center, half=half)
            if candidate.distance(start) < 6.0 or candidate.distance(self.goal) < 5.0:
                continue
            obstacles.append(candidate)
            if len(obstacles) >= n:
                break
        return obstacles

    def _build_landmarks(self) -> list[Landmark]:
        marks = [Landmark(position=self.goal.copy(), label=self.target_label, is_target=True)]
        for _ in range(self.n_lures):
            offset = self._rng.normal(0.0, 10.0, size=3)
            offset[2] = float(self._rng.uniform(-1.0, 2.0))
            marks.append(
                Landmark(
                    position=self.goal + offset,
                    label=self.target_label,
                    is_lure=True,
                )
            )
        for i in range(self.n_distractors):
            pos = self._rng.uniform(-1.0, 1.0, size=3) * np.array([25.0, 25.0, 3.0])
            pos[2] = abs(pos[2]) + 2.0
            marks.append(Landmark(position=pos, label=f"distractor_{i}"))
        return marks

    def _build_subgoals(self, start: np.ndarray) -> list[np.ndarray]:
        if self.n_subgoals <= 0:
            return []
        out = []
        for i in range(1, self.n_subgoals + 1):
            frac = i / (self.n_subgoals + 1)
            point = start + (self.goal - start) * frac
            point = point + np.array([0.0, 0.0, float(self._rng.uniform(-1.0, 1.0))])
            out.append(point)
        return out

    # -- sensing ------------------------------------------------------------

    async def observe(self) -> ObservationPacket:
        p = self.vehicle.position
        t_s = ns_to_s(self._t_ns)
        hits = tuple(self._visible_hits(t_s))
        self._last_hits = hits
        # The renderer is shown exactly what the sensor model admits, so a
        # scheduled dropout or an occlusion is absent from the image too. Any
        # other choice would let a vision policy see what the architecture was
        # supposed to have lost.
        visible = {h.label for h in hits} if self.render else None
        rays, bearings = self._range_fan()
        packet = ObservationPacket(
            seq=self._seq,
            t_sim_ns=self._t_ns,
            t_wall_ns=self._t_ns,
            position=Vec3(x=float(p[0]), y=float(p[1]), z=float(p[2])),
            velocity=Vec3(
                x=float(self.vehicle.velocity[0]),
                y=float(self.vehicle.velocity[1]),
                z=float(self.vehicle.velocity[2]),
            ),
            yaw_rad=self.vehicle.yaw,
            frame=Frame.ENU,
            rgb=self._sensor_ref("rgb", visible),
            rgb_down=self._sensor_ref(
                "rgb_down",
                set() if t_s < self._dropout_until_s else None,
            ),
            depth=self._sensor_ref("depth", visible),
            intrinsics=CameraIntrinsics(
                width=self._camera.width,
                height=self._camera.height,
                fx=self._camera.focal_px,
                fy=self._camera.focal_px,
                cx=self._camera.width / 2.0,
                cy=self._camera.height / 2.0,
            ),
            semantic_hits=hits,
            free_range_m=self._free_range(),
            range_rays=rays,
            ray_bearings_rad=bearings,
            vertical_clearance_m=self._vertical_clearance(),
            battery_frac=max(0.0, 1.0 - t_s / 600.0),
            coarse_goal_direction=self._coarse_goal_direction(),
            privileged=self._privileged() if self.allow_privileged else None,
        )
        self._seq += 1
        return packet

    def _sensor_ref(self, kind: str, visible_labels: set[str] | None = None) -> SensorRef:
        """Reference to a frame. Real pixels when rendering is on, none when off.

        Rendering is opt-in (``render: true``) because it costs roughly a
        millisecond per frame, and the fake-policy sweeps that never look at an
        image would pay it for nothing. When it is off the reference resolves to
        nothing and ``shape`` is ``None`` — an earlier version reported
        ``(224, 224)`` unconditionally, which made log inspection look like
        imagery was flowing through a system that had never produced a pixel.
        """
        p = self.vehicle.position
        raw = f"{kind}|{self._seq}|{p[0]:.3f}|{p[1]:.3f}|{p[2]:.3f}|{self.vehicle.yaw:.3f}"
        if kind == "depth" and self.depth_renderer != "legacy_corner":
            raw += f"|{self.depth_renderer}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]

        if (
            not self.render
            or (kind == "depth" and not self.render_depth)
            or (kind == "rgb_down" and not self.render_down)
        ):
            return SensorRef(
                kind=kind, uri=f"stub://grid3d/{kind}/{self._seq}", digest=digest, shape=None
            )

        from uavlab.adapters.gym.render import render_depth_frame, render_down_frame, render_frame
        from uavlab.core.frame_store import global_store

        if kind == "rgb":
            image = render_frame(
                self.vehicle.position,
                self.vehicle.yaw,
                self.obstacles,
                self.landmarks,
                self.target_label,
                camera=self._camera,
                visible_labels=visible_labels,
            )
            shape = (image.height, image.width)
        elif kind == "rgb_down":
            image = render_down_frame(
                self.vehicle.position,
                self.vehicle.yaw,
                self.obstacles,
                self.landmarks,
                self.target_label,
                camera=self._down_camera,
                visible_labels=visible_labels,
            )
            shape = (image.height, image.width)
        else:
            image = render_depth_frame(
                self.vehicle.position,
                self.vehicle.yaw,
                self.obstacles,
                self.landmarks,
                self.target_label,
                camera=self._camera,
                visible_labels=visible_labels,
                renderer=self.depth_renderer,
            )
            shape = tuple(int(x) for x in image.shape)
        uri = f"frame://{self._frame_ns}/{kind}/{self._seq}"
        global_store().put(uri, image)
        return SensorRef(kind=kind, uri=uri, digest=digest, shape=shape)

    def _coarse_goal_direction(self) -> str | None:
        """AeroVLA's seven-way localization hint, with no coordinate leakage."""
        if not self.coarse_goal_direction:
            return None
        delta = self.goal - self.vehicle.position
        if float(np.linalg.norm(delta[:2])) < 1e-9:
            return "straight ahead"
        world_bearing = math.atan2(float(delta[1]), float(delta[0]))
        relative = math.atan2(
            math.sin(world_bearing - self.vehicle.yaw),
            math.cos(world_bearing - self.vehicle.yaw),
        )
        degrees = math.degrees(relative)
        magnitude = abs(degrees)
        if magnitude <= 15.0:
            return "straight ahead"
        if magnitude <= 60.0:
            return "forward-left" if degrees > 0.0 else "forward-right"
        if magnitude <= 120.0:
            return "to your left" if degrees > 0.0 else "to your right"
        return "to your left rear" if degrees > 0.0 else "to your right rear"

    def _visible_hits(self, t_s: float) -> list[SemanticHit]:
        """Detections that survive range, field of view and occlusion.

        Everything the vehicle cannot actually see is filtered out here.  That
        filtering is what stops an architecture from succeeding on information
        it never observed, and it is why memory matters at all.
        """
        if t_s < self._dropout_until_s or not self.landmarks:
            return []
        p = self.vehicle.position
        half_fov = math.radians(self.fov_deg) / 2.0

        positions = np.stack([m.position for m in self.landmarks])  # (M,3)
        deltas = positions - p
        distances = np.linalg.norm(deltas, axis=-1)
        bearings = np.arctan2(deltas[:, 1], deltas[:, 0]) - self.vehicle.yaw
        bearings = np.arctan2(np.sin(bearings), np.cos(bearings))

        candidate = (distances <= self.sensor_range_m) & (np.abs(bearings) <= half_fov)
        if not candidate.any():
            return []
        indices = np.flatnonzero(candidate)
        blocked = self._segment_blocked(positions[indices])
        schedule_occluded = self._occluded_by_schedule(t_s)

        out: list[SemanticHit] = []
        for local, idx in enumerate(indices):
            if blocked[local]:
                continue
            mark = self.landmarks[idx]
            if mark.is_target and schedule_occluded:
                continue
            noise = (
                self._rng.normal(0.0, self.detection_noise_m, size=3)
                if self.detection_noise_m
                else np.zeros(3)
            )
            observed = mark.position + noise
            distance = float(distances[idx])
            score = float(np.clip(1.0 - distance / (self.sensor_range_m * 1.4), 0.05, 0.99))
            if mark.is_lure:
                score *= 0.85
            out.append(
                SemanticHit(
                    label=mark.label,
                    score=score,
                    position=Vec3(x=float(observed[0]), y=float(observed[1]), z=float(observed[2])),
                    distance_m=distance,
                    bearing_rad=float(bearings[idx]),
                )
            )
        return out

    def _occluded_by_schedule(self, t_s: float) -> bool:
        if self.occlusion_period_s <= 0.0:
            return False
        phase = (t_s % self.occlusion_period_s) / self.occlusion_period_s
        return phase < self.occlusion_duty

    # Ray casting runs on every control tick, so it is vectorised over all
    # rays, all range steps and all obstacles at once.  The scalar version was
    # ~1.7 M distance evaluations per episode and dominated the whole runtime,
    # which would have made large sweeps impossible.

    def _rebuild_obstacle_arrays(self) -> None:
        if self.obstacles:
            self._obs_centers = np.stack([o.center for o in self.obstacles])
            self._obs_halves = np.stack([o.half for o in self.obstacles])
        else:
            self._obs_centers = np.zeros((0, 3))
            self._obs_halves = np.zeros((0, 3))

    def _distance_to_obstacles(self, points: np.ndarray) -> np.ndarray:
        """Box distances for a batch of points. ``points`` is (..., 3) -> (..., N)."""
        if self._obs_centers.shape[0] == 0:
            return np.full((*points.shape[:-1], 0), np.inf)
        delta = np.abs(points[..., None, :] - self._obs_centers) - self._obs_halves
        outside = np.linalg.norm(np.maximum(delta, 0.0), axis=-1)
        inside = np.minimum(delta.max(axis=-1), 0.0)
        return outside + inside

    def _free_range(self) -> float:
        """Forward clearance along the current heading."""
        rays, bearings = self._range_fan()
        idx = min(range(len(bearings)), key=lambda i: abs(bearings[i]))
        return rays[idx]

    def _range_fan(
        self, max_range: float = 25.0, step_m: float = 0.5
    ) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """A horizontal depth fan: the planner's only geometric evidence."""
        if self._fan_cache_seq == self._seq and self._fan_cache is not None:
            return self._fan_cache
        bearings = np.linspace(-math.pi, math.pi, self.n_rays, endpoint=False)
        angles = bearings + self.vehicle.yaw
        directions = np.stack(
            [np.cos(angles), np.sin(angles), np.zeros_like(angles)], axis=-1
        )  # (R, 3)
        steps = np.arange(step_m, max_range, step_m)  # (S,)
        points = self.vehicle.position + directions[:, None, :] * steps[None, :, None]  # (R,S,3)
        hit = (self._distance_to_obstacles(points) <= self.drone_radius_m).any(axis=-1)  # (R,S)
        any_hit = hit.any(axis=-1)
        first = np.where(any_hit, steps[hit.argmax(axis=-1)], max_range)
        result = (
            tuple(float(v) for v in first),
            tuple(float(b) for b in bearings),
        )
        self._fan_cache = result
        self._fan_cache_seq = self._seq
        return result

    def _vertical_clearance(self, max_range: float = 10.0, step_m: float = 0.5) -> float:
        steps = np.arange(step_m, max_range, step_m)
        points = self.vehicle.position - np.stack(
            [np.zeros_like(steps), np.zeros_like(steps), steps], axis=-1
        )
        hit = (self._distance_to_obstacles(points) <= self.drone_radius_m).any(axis=-1)
        if hit.any():
            return float(steps[hit.argmax()])
        return float(max(0.0, self.vehicle.position[2]))

    def _segment_blocked(self, targets: np.ndarray, samples: int = 10) -> np.ndarray:
        """Occlusion test from the vehicle to each of ``targets`` (M, 3) -> (M,)."""
        if targets.shape[0] == 0 or self._obs_centers.shape[0] == 0:
            return np.zeros(targets.shape[0], dtype=bool)
        fractions = np.linspace(0.0, 1.0, samples)  # (K,)
        origin = self.vehicle.position
        points = origin + (targets - origin)[:, None, :] * fractions[None, :, None]  # (M,K,3)
        return (self._distance_to_obstacles(points) <= 0.0).any(axis=(1, 2))

    def _privileged(self) -> dict[str, object]:
        """Ground truth, exposed only to the declared oracle configuration."""
        return {
            "goal": [float(x) for x in self.goal],
            "goal_distance_m": float(np.linalg.norm(self.goal - self.vehicle.position)),
            "subgoals": [[float(x) for x in s] for s in self.subgoals],
            "subgoals_done": self._subgoals_done,
            "obstacles": [
                {"center": [float(x) for x in o.center], "half": [float(x) for x in o.half]}
                for o in self.obstacles
            ],
        }

    # -- dynamics -----------------------------------------------------------

    async def step(self, command: ControlCommand, dt_ns: int) -> None:
        dt = ns_to_s(dt_ns)
        if dt <= 0:
            return
        self._fan_cache = None
        self._apply_injections(ns_to_s(self._t_ns))

        target_v = np.array([command.velocity.x, command.velocity.y, command.velocity.z])
        speed = float(np.linalg.norm(target_v))
        if speed > self.max_speed_mps:
            target_v = target_v / speed * self.max_speed_mps
            self._constraint_violations += 1

        # First-order velocity lag, so control rate genuinely matters: a slow
        # loop cannot track a tight gap as well as a fast one.
        alpha = min(1.0, dt / max(self.accel_tau_s, 1e-3))
        self.vehicle.velocity += (target_v - self.vehicle.velocity) * alpha
        effective = self.vehicle.velocity + self._wind

        previous = self.vehicle.position.copy()
        self.vehicle.position = previous + effective * dt
        self.vehicle.yaw = math.atan2(
            math.sin(self.vehicle.yaw + command.yaw_rate_rps * dt),
            math.cos(self.vehicle.yaw + command.yaw_rate_rps * dt),
        )
        self._path_length += float(np.linalg.norm(self.vehicle.position - previous))
        self._t_ns += dt_ns

        self._update_collisions(previous)
        self._update_subgoals()
        self._update_lure_dwell(dt)

    def _update_lure_dwell(self, dt: float) -> None:
        """Time spent loitering at a decoy, measured from true geometry.

        Whether an architecture committed to the wrong target is a fact about
        where the vehicle actually flew, not about what it claimed to believe.
        """
        for mark in self.landmarks:
            if not mark.is_lure:
                continue
            if float(np.linalg.norm(self.vehicle.position - mark.position)) <= self._lure_radius_m:
                self._lure_dwell_s += dt
                return

    def _update_collisions(self, previous: np.ndarray) -> None:
        p = self.vehicle.position
        if self._obs_centers.shape[0]:
            # Test the swept segment, not just the endpoint: a fast vehicle can
            # otherwise tunnel through a thin wall between two control ticks.
            probes = np.stack([p, (p + previous) / 2.0, previous])
            distances = self._distance_to_obstacles(probes)  # (3, N)
            clearance = float(distances.min())
            self._min_clearance = min(self._min_clearance, clearance)
            hits = int((distances.min(axis=0) <= self.drone_radius_m).sum())
            if hits:
                self._collided = True
                self._collision_count += hits

        limits = self.world_size / 2.0
        if (
            abs(p[0]) > limits[0]
            or abs(p[1]) > limits[1]
            or p[2] < 0.2
            or p[2] > self.world_size[2]
        ):
            self._out_of_bounds = True

    def _update_subgoals(self) -> None:
        if self._subgoals_done >= len(self.subgoals):
            return
        target = self.subgoals[self._subgoals_done]
        if float(np.linalg.norm(self.vehicle.position - target)) <= self.subgoal_radius_m:
            self._subgoals_done += 1

    def _apply_injections(self, t_s: float) -> None:
        for inj in self.injections:
            if inj.fired or t_s < inj.at_s:
                continue
            inj.fired = True
            match inj.kind:
                case "block_path":
                    self._inject_block(inj)
                case "lure_target":
                    offset = np.array(
                        [
                            inj.params.get("dx", 8.0),
                            inj.params.get("dy", -6.0),
                            inj.params.get("dz", 0.0),
                        ]
                    )
                    self.landmarks.append(
                        Landmark(
                            position=self.vehicle.position + offset,
                            label=self.target_label,
                            is_lure=True,
                        )
                    )
                case "sensor_dropout":
                    self._dropout_until_s = t_s + inj.params.get("duration_s", 3.0)
                case "wind_gust":
                    angle = inj.params.get("bearing_rad", 1.2)
                    speed = inj.params.get("speed_mps", 1.5)
                    self._wind = np.array(
                        [speed * math.cos(angle), speed * math.sin(angle), 0.0]
                    )

    def _inject_block(self, inj: _Injected) -> None:
        """Drop an obstacle across the route, far enough ahead to be avoidable.

        The obstacle is placed along the current direction of travel at a
        distance that leaves room to react, never at the midpoint to the goal.
        Placing it at the midpoint was a harness bug: by the time the failure
        fired the vehicle was often already past that point, so the box
        materialised on top of a drone travelling at cruise speed. That made
        the regime measure "was the vehicle teleported into a wall" instead of
        "can this architecture recover", and it contaminated every
        architecture's numbers equally, which is what made it hard to spot.

        A recovery scenario is only a recovery scenario if recovery is possible.
        """
        size = inj.params.get("size_m", 4.0)
        half = np.array([size / 2.0, size * 1.5, size])

        position = self.vehicle.position
        speed = float(np.linalg.norm(self.vehicle.velocity))
        to_goal = self.goal - position
        distance_to_goal = float(np.linalg.norm(to_goal))
        if distance_to_goal < 1e-6:
            return
        direction = to_goal / distance_to_goal

        # Reaction room: stopping distance at the current speed, plus the box's
        # own half-depth, plus the vehicle radius and a margin.
        stopping = speed * self.block_reaction_s + self.block_margin_m
        lead = max(float(inj.params.get("lead_m", self.block_lead_m)), stopping + float(half[0]))

        # Never place it beyond the goal, or the route is not blocked at all.
        lead = min(lead, max(distance_to_goal - self.goal_radius_m - float(half[0]), 0.0))
        if lead < stopping:
            # No room between here and the goal to stage a fair blockage.
            self._skipped_injections += 1
            return

        center = position + direction * lead
        center[2] = position[2]
        candidate = Obstacle(center=center, half=half, label="injected_block")
        if candidate.distance(position) <= self.drone_radius_m + self.block_margin_m:
            self._skipped_injections += 1
            return

        self.obstacles.append(candidate)
        self._rebuild_obstacle_arrays()
        self._injected_block_clearances.append(candidate.distance(position))

    # -- scoring ------------------------------------------------------------

    def status(self) -> EnvironmentStatus:
        p = self.vehicle.position
        return EnvironmentStatus(
            t_sim_ns=self._t_ns,
            position=Vec3(x=float(p[0]), y=float(p[1]), z=float(p[2])),
            distance_to_goal_m=float(np.linalg.norm(self.goal - p)),
            # Visibility is read from the last computed observation rather than
            # recomputed here: status() runs on every control tick, and casting
            # rays twice per tick was the single largest cost in the harness.
            goal_visible=any(h.label == self.target_label for h in self._last_hits),
            subgoals_completed=self._subgoals_done,
            subgoals_total=len(self.subgoals),
            collided=self._collided,
            collision_count=self._collision_count,
            min_obstacle_distance_m=self._min_clearance,
            out_of_bounds=self._out_of_bounds,
            constraint_violations=self._constraint_violations,
            path_length_m=self._path_length,
            shortest_path_m=self._shortest,
            speed_mps=float(np.linalg.norm(self.vehicle.velocity)),
            extras={
                "goal_radius_m": self.goal_radius_m,
                "lure_dwell_s": self._lure_dwell_s,
                "landmarks": float(len(self.landmarks)),
                "obstacles": float(len(self.obstacles)),
                "skipped_injections": float(self._skipped_injections),
                "min_injected_block_clearance_m": (
                    min(self._injected_block_clearances)
                    if self._injected_block_clearances
                    else -1.0
                ),
            },
        )

    async def close(self) -> None:
        return None

    def reset_plugin_state(self) -> None:
        return None
