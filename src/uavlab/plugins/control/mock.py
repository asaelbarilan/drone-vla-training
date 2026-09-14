"""Controller adapters.

One canonical control representation for the whole benchmark: a velocity
setpoint plus a yaw rate.  Both handoff forms — a planned trajectory and a
learned kinematic action — converge here, which is the only reason a skill agent
and a direct VLA are physically comparable at all.

For a matched direct-VLA comparison this representation is frozen for the entire
experiment.  Comparing a body-rate policy against a collision-checked position
target and calling the difference "architecture" would be a category error.
"""

from __future__ import annotations

import math
from typing import Any

from uavlab.contracts import (
    ControlCommand,
    Frame,
    KinematicAction,
    MissionSpec,
    Trajectory,
    Vec3,
    s_to_ns,
)
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext


@register("controller", "mock_velocity")
class MockVelocityController:
    """Proportional tracker with a fixed velocity/yaw-rate output contract."""

    def __init__(self, **params: Any) -> None:
        self.face_semantic_goal = bool(params.get("face_semantic_goal", False))
        self.yaw_hold_radius_m = float(params.get("yaw_hold_radius_m", 0.0))
        if not math.isfinite(self.yaw_hold_radius_m) or self.yaw_hold_radius_m < 0:
            raise ValueError("yaw_hold_radius_m must be finite and nonnegative")
        self._held_yaw = None
        self.kp = float(params.get("kp", 1.1))
        self.max_speed_mps = float(params.get("max_speed_mps", 5.0))
        self.lookahead_m = float(params.get("lookahead_m", 3.0))
        self.yaw_kp = float(params.get("yaw_kp", 1.5))
        self.max_yaw_rate_rps = float(params.get("max_yaw_rate_rps", 1.5))
        self.command_ttl_s = float(params.get("command_ttl_s", 1.0))
        self._max_speed_from_mission: float | None = None

    @property
    def name(self) -> str:
        return "mock_velocity"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._max_speed_from_mission = mission.constraints.max_speed_mps
        self._held_yaw = None

    @property
    def _speed_limit(self) -> float:
        return min(self.max_speed_mps, self._max_speed_from_mission or self.max_speed_mps)

    def track(self, trajectory: Trajectory, ctx: DecisionContext) -> ControlCommand:
        target = self._carrot(trajectory, ctx)
        position = ctx.observation.position
        error = Vec3(x=target.x - position.x, y=target.y - position.y, z=target.z - position.z)
        velocity = self._clamp(Vec3(x=error.x * self.kp, y=error.y * self.kp, z=error.z * self.kp))
        yaw_error = error
        if self.face_semantic_goal:
            # Opt-in D-86: camera heading is independent of avoidance translation.
            # This metadata is the planner's requested goal, never simulator truth.
            raw_goal = trajectory.metadata.get("semantic_goal_xyz")
            if raw_goal is None:
                raise ValueError("goal-facing yaw requires semantic_goal_xyz metadata")
            goal = [float(value) for value in raw_goal.split(",")]
            if len(goal) != 3 or not all(math.isfinite(value) for value in goal):
                raise ValueError("invalid semantic_goal_xyz metadata")
            yaw_error = Vec3(x=goal[0] - position.x, y=goal[1] - position.y, z=0.0)
        return ControlCommand(
            t_sim_ns=ctx.t_sim_ns,
            velocity=velocity,
            yaw_rate_rps=self._yaw_rate_toward(yaw_error, ctx),
            frame=Frame.ENU,
            expires_t_sim_ns=ctx.t_sim_ns + s_to_ns(self.command_ttl_s),
            source_decision_id=trajectory.source_decision_id,
        )

    def _carrot(self, trajectory: Trajectory, ctx: DecisionContext) -> Vec3:
        """Pick the first trajectory point beyond the lookahead distance."""
        position = ctx.observation.position
        for point in trajectory.points:
            if position.distance_to(point.position) >= self.lookahead_m:
                return point.position
        return trajectory.points[-1].position

    def from_action(
        self, action: KinematicAction, ctx: DecisionContext, decision_id: str
    ) -> ControlCommand:
        return ControlCommand(
            t_sim_ns=ctx.t_sim_ns,
            velocity=self._clamp(action.velocity),
            yaw_rate_rps=max(
                -self.max_yaw_rate_rps, min(self.max_yaw_rate_rps, action.yaw_rate_rps)
            ),
            frame=Frame.ENU,
            expires_t_sim_ns=ctx.t_sim_ns + s_to_ns(max(action.duration_s, 0.05)),
            source_decision_id=decision_id,
        )

    def hold(self, ctx: DecisionContext) -> ControlCommand:
        return ControlCommand(
            t_sim_ns=ctx.t_sim_ns,
            velocity=Vec3(x=0.0, y=0.0, z=0.0),
            frame=Frame.ENU,
            expires_t_sim_ns=ctx.t_sim_ns + s_to_ns(self.command_ttl_s),
        )

    def _clamp(self, velocity: Vec3) -> Vec3:
        speed = velocity.norm()
        limit = self._speed_limit
        if speed <= limit or speed < 1e-9:
            return velocity
        scale = limit / speed
        return Vec3(x=velocity.x * scale, y=velocity.y * scale, z=velocity.z * scale)

    def _yaw_rate_toward(self, error: Vec3, ctx: DecisionContext) -> float:
        if self.yaw_hold_radius_m > 0:
            # D-110: a near-zero translation vector has no useful heading.
            # Retain the last approach bearing until a meaningful move is requested.
            if math.hypot(error.x, error.y) >= self.yaw_hold_radius_m:
                self._held_yaw = math.atan2(error.y, error.x)
            elif self._held_yaw is None:
                self._held_yaw = ctx.observation.yaw_rad
            desired = self._held_yaw
        else:
            if abs(error.x) < 1e-6 and abs(error.y) < 1e-6:
                return 0.0
            desired = math.atan2(error.y, error.x)
        delta = math.atan2(
            math.sin(desired - ctx.observation.yaw_rad), math.cos(desired - ctx.observation.yaw_rad)
        )
        return max(-self.max_yaw_rate_rps, min(self.max_yaw_rate_rps, delta * self.yaw_kp))
