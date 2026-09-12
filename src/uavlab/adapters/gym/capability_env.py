"""Eight opt-in capability scenarios; shared physics, private task evaluation.

This is a scenario adapter, not a policy. No route, class answer, task progress,
or evaluator state enters normal observations. Scripted/oracle checks are fixtures.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from uavlab.adapters.gym.deterministic_env import DeterministicEnv, Landmark, Obstacle
from uavlab.contracts import ControlCommand, MissionSpec, ObservationPacket, ns_to_s
from uavlab.contracts.env_status import EnvironmentStatus
from uavlab.core.registry import register

SCENARIOS = (
    "known_goal",
    "visible_target",
    "turn_search",
    "overturned_vehicle",
    "conditional_gate",
    "ordered_visit",
    "closing_passage",
    "follow_target",
)
RED = (206, 44, 44)
BLUE = (40, 85, 220)


def point(x: float, y: float = 0.0, z: float = 3.0) -> np.ndarray:
    return np.array([x, y, z], dtype=float)


@register("environment", "capability_grid3d")
class CapabilityEnv(DeterministicEnv):
    """Deterministic screening fixtures for eight different capability regimes."""

    def __init__(self, **params: Any) -> None:
        self.scenario = str(params.get("scenario", "known_goal"))
        if self.scenario not in SCENARIOS:
            raise ValueError(f"Unknown capability scenario: {self.scenario}")
        if params.get("failures") or params.get("coarse_goal_direction"):
            raise ValueError("Capability fixtures define their own events and hide goal hints")
        settings = dict(params)
        settings.update(
            scene="empty",
            n_obstacles=0,
            distractors=0,
            subgoals=0,
            render=True,
            render_depth=True,
            depth_renderer="box_ray_v2",
            detection_noise_m=0.0,
        )
        settings.setdefault("max_speed_mps", 2.0)
        settings.setdefault("sensor_range_m", 45.0)
        settings.setdefault("image_size", 224)
        settings.setdefault("camera_pitch_rad", -0.10)
        super().__init__(**settings)
        self.task_events: list[dict] = []
        self._branch_ok = False
        self._wrong_branch = False
        self._blocked = False
        self._seen = False
        self._tracking_good_s = 0.0
        self._tracking_total_s = 0.0
        self._tracking_streak_s = 0.0
        self._dwell_s = 0.0
        self._visit_dwell_s = 0.0
        self._tracking_passed: bool | None = None
        self._task_complete = False
        self._vehicle_truth: list[dict] = []

    @property
    def name(self) -> str:
        return "capability_grid3d"

    async def reset(self, mission: MissionSpec, seed: int) -> ObservationPacket:
        await super().reset(mission, seed)
        self._mission_constraints = mission.constraints
        self.vehicle.position = point(0)
        self.vehicle.velocity[:] = 0
        self.vehicle.yaw = 0.0
        self._start = point(0)
        self.goal = point(12)
        self.landmarks = []
        self.obstacles = []
        self.subgoals = []
        self._subgoals_done = 0
        self.task_events = []
        self._vehicle_truth = []
        self._branch_ok = self._wrong_branch = self._blocked = self._seen = False
        self._task_complete = False
        self._tracking_passed = None
        self._tracking_good_s = self._tracking_total_s = self._tracking_streak_s = 0.0
        self._dwell_s = self._visit_dwell_s = 0.0
        # Explicit variants enable matched branch tests; otherwise seed controls them.
        self.left_blocked = bool(self.params.get("left_blocked", seed % 2 == 1))
        self.target_side = 1 if seed % 2 else -1
        self.target_label = "red pillar"
        if self.scenario == "turn_search":
            self.goal = point(-8, 8 * self.target_side)
        elif self.scenario == "overturned_vehicle":
            for side in (-1, 1):
                upside_down = side == self.target_side
                self._car(12, side * 4, upside_down)
            self.goal = point(12, self.target_side * 4, 3.2)
        elif self.scenario == "conditional_gate":
            self.goal = point(16)
            for y, half_y in [(-12, 4), (0, 2), (12, 4)]:
                self._box(point(8, y, 4), point(0.6, half_y, 4))
            if self.left_blocked:
                self._box(point(8, 5, 4), point(0.6, 3, 4))
        elif self.scenario == "ordered_visit":
            self.subgoals = [point(8, 4)]
            self.goal = point(16, -4)
            self.landmarks = [
                Landmark(self.subgoals[0].copy(), "red pillar", color=RED),
                Landmark(self.goal.copy(), "blue pillar", is_target=True, color=BLUE),
            ]
            self.target_label = "blue pillar"
        elif self.scenario == "closing_passage":
            self.goal = point(24)
            for side in (-1, 1):
                self._box(point(14, side * 8, 4), point(0.6, 3, 4))
        elif self.scenario == "follow_target":
            self.goal = point(8)
        if not self.landmarks and self.scenario != "overturned_vehicle":
            self.landmarks = [
                Landmark(self.goal.copy(), self.target_label, is_target=True, color=RED)
            ]
        self._shortest = float(np.linalg.norm(self.goal - self._start))
        if self.scenario in {
            "ordered_visit",
            "conditional_gate",
            "closing_passage",
            "follow_target",
        }:
            self._shortest = 0.0  # no certified shortest path for these objectives
        self._rebuild_obstacle_arrays()
        self._fan_cache = None
        self._fan_cache_seq = -1
        self._seq = 0
        return await self.observe()

    def _box(self, center: np.ndarray, half: np.ndarray, color=None) -> None:
        self.obstacles.append(Obstacle(center, half, color=color))

    def _car(self, x: float, y: float, inverted: bool) -> None:
        # Same neutral color/shape for both cars; orientation is the only class cue.
        self._box(point(x, y, 0.9), point(1.6, 0.85, 0.3), (180, 160, 60))
        roof_z, wheel_z = (0.35, 1.4) if inverted else (1.45, 0.3)
        self._box(point(x, y, roof_z), point(0.8, 0.65, 0.3), (80, 120, 160))
        for dx in (-1.05, 1.05):
            for dy in (-0.95, 0.95):
                self._box(point(x + dx, y + dy, wheel_z), point(0.32, 0.22, 0.28), (25, 25, 28))
        self._vehicle_truth.append({"position": [x, y, 0.9], "inverted": inverted})

    async def observe(self) -> ObservationPacket:
        packet = await super().observe()
        # The parent uses visibility-filtered hits to render. Do not expose them:
        # they contain simulator-authored class labels and metric target positions.
        return packet.model_copy(update={"semantic_hits": (), "coarse_goal_direction": None})

    def _update_subgoals(self) -> None:
        # Ordered visits use dwell and are updated once per physical step below.
        return None

    def _visible_goal(self) -> bool:
        p = self.vehicle.position
        target = (
            self.goal if self.scenario != "overturned_vehicle" else self.goal - point(0, 0, 1.7)
        )
        pixels, depth = self._camera.project(np.array([target]), p, self.vehicle.yaw)
        u, v = pixels[0]
        return bool(
            depth[0] > 0.2
            and 0 <= u < self._camera.width
            and 0 <= v < self._camera.height
            and np.linalg.norm(target - p) <= self.sensor_range_m
            and not self._segment_blocked(np.array([target]))[0]
        )

    async def step(self, command: ControlCommand, dt_ns: int) -> None:
        if dt_ns <= 0:
            return
        previous = self.vehicle.position.copy()
        old_t = ns_to_s(self._t_ns)
        # A fixed-time gate closure. The 2 m/s fixture leaves >=7 m reaction room.
        if self.scenario == "closing_passage" and not self._blocked and old_t >= 3.0:
            self._blocked = True
            self._box(point(14, 0, 4), point(0.6, 5, 4))
            self._rebuild_obstacle_arrays()
            self._fan_cache = None
            self.task_events.append({"t": old_t, "kind": "passage_closed"})
        await super().step(command, dt_ns)
        dt = ns_to_s(dt_ns)
        t = ns_to_s(self._t_ns)
        p = self.vehicle.position
        limits = self._mission_constraints
        if (
            p[2] < limits.min_altitude_m
            or p[2] > limits.max_altitude_m
            or np.linalg.norm(p[:2] - self._start[:2]) > limits.geofence_radius_m
        ):
            self._out_of_bounds = True
        if self.scenario == "follow_target":
            self.goal = point(8 + 0.7 * t)
            self.landmarks[0].position = self.goal.copy()
        self._seen |= self._visible_goal()
        distance = float(np.linalg.norm(self.goal - p))
        if self.scenario == "conditional_gate" and previous[0] < 8 <= p[0]:
            fraction = (8 - previous[0]) / (p[0] - previous[0])
            crossing = previous + fraction * (p - previous)
            desired_y = -5 if self.left_blocked else 5
            correct = abs(crossing[1] - desired_y) <= 2.6 and 1 <= crossing[2] <= 7
            self._branch_ok |= correct
            self._wrong_branch |= not correct
            self.task_events.append({"t": t, "kind": "gate_crossed", "correct": bool(correct)})
        if self.scenario == "ordered_visit" and self._subgoals_done == 0:
            near = np.linalg.norm(p - self.subgoals[0]) <= self.goal_radius_m
            self._visit_dwell_s = self._visit_dwell_s + dt if near else 0.0
            if self._visit_dwell_s >= 0.5:
                self._subgoals_done = 1
                self.task_events.append({"t": t, "kind": "first_visit_completed"})
        near = distance <= self.goal_radius_m
        self._dwell_s = self._dwell_s + dt if near else 0.0
        complete = near
        if self.scenario == "turn_search":
            complete &= self._seen
        elif self.scenario == "conditional_gate":
            complete &= self._branch_ok and not self._wrong_branch
        elif self.scenario == "ordered_visit":
            complete &= self._subgoals_done == 1
        elif self.scenario == "closing_passage":
            complete &= self._blocked
        elif self.scenario == "follow_target":
            # Five seconds to acquire, then a fixed 15-second scoring window.
            overlap = max(0.0, min(t, 20.0) - max(old_t, 5.0))
            delta = self.goal - p
            bearing = math.atan2(delta[1], delta[0]) - self.vehicle.yaw
            angle = abs(math.atan2(math.sin(bearing), math.cos(bearing)))
            good = 4 <= distance <= 6 and angle <= math.radians(20) and self._visible_goal()
            self._tracking_total_s += overlap
            self._tracking_good_s += overlap if good else 0
            self._tracking_streak_s = self._tracking_streak_s + dt if good else 0.0
            if t >= 20 and self._tracking_passed is None:
                self._tracking_passed = (
                    self._tracking_good_s >= 13.5 and self._tracking_streak_s >= 2
                )
            complete = bool(self._tracking_passed)
        self._task_complete = bool(complete and not self._collided and not self._out_of_bounds)

    def status(self) -> EnvironmentStatus:
        state = super().status()
        extras = dict(state.extras)
        extras.update(
            task_complete=float(self._task_complete),
            target_ever_visible=float(self._seen),
            branch_correct=float(self._branch_ok),
            wrong_branch=float(self._wrong_branch),
            passage_closed=float(self._blocked),
            tracking_good_s=self._tracking_good_s,
            tracking_total_s=self._tracking_total_s,
            tracking_fraction=self._tracking_good_s / max(self._tracking_total_s, 1e-9),
            shortest_path_valid=float(
                self.scenario
                in {"known_goal", "visible_target", "turn_search", "overturned_vehicle"}
            ),
        )
        return state.model_copy(
            update={
                "task_complete": self._task_complete,
                "goal_visible": self._visible_goal(),
                "extras": extras,
            }
        )

    def debug_scene(self) -> dict:
        """Privileged evaluator/dashboard channel, never attached to observations."""
        return {
            "obstacles": [
                {"center": o.center.tolist(), "half": o.half.tolist(), "color": o.color}
                for o in self.obstacles
            ],
            "landmarks": [
                {
                    "position": m.position.tolist(),
                    "label": m.label,
                    "target": m.is_target,
                    "color": m.color,
                }
                for m in self.landmarks
            ],
            "goal": self.goal.tolist(),
            "scenario": self.scenario,
            "vehicles": self._vehicle_truth,
            "task_events": list(self.task_events),
            "task_status": self.status().model_dump(mode="json"),
        }
