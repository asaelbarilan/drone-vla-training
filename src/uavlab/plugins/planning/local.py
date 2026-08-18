"""Classical local planners.

The planner is the component OnFly's ablation showed to be load-bearing:
removing it hurts far more than removing a semantic verifier.  So it stays
deliberately simple and deliberately *fixed* across the waypoint architectures —
if the planner varied, a waypoint-family comparison would be measuring planner
quality rather than where semantic authority sits.
"""

from __future__ import annotations

import math
from typing import Any

from uavlab.contracts import (
    MissionSpec,
    Trajectory,
    TrajectoryPoint,
    Vec3,
    WaypointGoal,
    s_to_ns,
)
from uavlab.core.registry import register
from uavlab.core.sensing import min_clearance, widest_free_bearing
from uavlab.interfaces import DecisionContext


@register("planner", "fixed_local")
class FixedLocalPlanner:
    """Receding-horizon steering: head for the goal, deflect around blockage.

    Bearings are searched outward from the direct line, so the detour is the
    smallest one the depth fan supports.  When every bearing is blocked the
    planner reports infeasibility rather than inventing a path — an unexecutable
    plan must be visible in the executable-plan rate, not hidden by a fallback.
    """

    def __init__(self, **params: Any) -> None:
        self.step_m = float(params.get("step_m", 2.5))
        self.horizon_steps = int(params.get("horizon_steps", 4))
        self.clearance_m = float(params.get("clearance_m", 1.6))
        self.brake_reserve_s = float(params.get("brake_reserve_s", 0.45))
        """Reaction time the plan reserves for whatever shield sits downstream.

        This must be at least the shield's own reaction time.  If the planner
        commits to a bearing that the shield then considers unsafe, the two
        fight: the planner keeps steering into a gap it thinks is fine, the
        shield keeps braking, and the vehicle wedges in place while the
        intervention count explodes.  That livelock looks like an architecture
        result and is really two components disagreeing about one number.
        """
        self.max_deflection_rad = float(params.get("max_deflection_rad", math.radians(110.0)))
        self.deflection_step_rad = float(params.get("deflection_step_rad", math.radians(12.0)))
        self.climb_when_blocked = bool(params.get("climb_when_blocked", True))
        self._min_alt = 0.5
        self._max_alt = 30.0
        self._required_clearance_m = self.clearance_m

    @property
    def name(self) -> str:
        return "fixed_local"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._min_alt = mission.constraints.min_altitude_m
        self._max_alt = mission.constraints.max_altitude_m
        base = max(self.clearance_m, mission.constraints.min_obstacle_clearance_m * 2.0)
        # Plan for the speed this mission actually permits, not for standing still.
        self._required_clearance_m = base + mission.constraints.max_speed_mps * self.brake_reserve_s

    def plan(self, goal: WaypointGoal, ctx: DecisionContext) -> Trajectory:
        position = ctx.observation.position
        delta = Vec3(
            x=goal.target.x - position.x,
            y=goal.target.y - position.y,
            z=goal.target.z - position.z,
        )
        distance = delta.norm()
        if distance < 1e-6:
            return Trajectory(
                start_t_sim_ns=ctx.t_sim_ns,
                points=(TrajectoryPoint(t_offset_ns=0, position=goal.target),),
                planner_name=self.name,
                feasible=True,
            )

        desired_bearing = math.atan2(delta.y, delta.x)
        bearing = self._free_bearing(desired_bearing, ctx)
        if bearing is None:
            climb = self._climb_escape(ctx)
            if climb is None:
                return Trajectory(
                    start_t_sim_ns=ctx.t_sim_ns,
                    points=(),
                    planner_name=self.name,
                    feasible=False,
                    reason="every bearing within the deflection limit is blocked",
                    source_decision_id=None,
                )
            return climb

        # How far the plan may commit along the chosen bearing. Capping the
        # horizon by the available room is what makes the planner slow down in
        # clutter: the controller's speed is proportional to how far ahead the
        # trajectory reaches, so a short plan is a slow plan. Without this the
        # vehicle drives at full speed into a corridor it planned through
        # nearly a second earlier, and only a downstream shield saves it —
        # which would credit the shield for work the planner should be doing.
        clearance = self._clearance_at(bearing, ctx)
        committed = max(self.step_m * 0.4, min(distance, clearance - self.clearance_m))

        points: list[TrajectoryPoint] = []
        step_time_ns = s_to_ns(self.step_m / 2.0)
        cursor = position
        travelled = 0.0
        for i in range(1, self.horizon_steps + 1):
            remaining = max(0.0, min(distance, committed) - travelled)
            advance = min(self.step_m, remaining)
            if advance <= 1e-6:
                break
            travelled += advance
            climb = (goal.target.z - position.z) * (advance / max(distance, 1e-6))
            cursor = Vec3(
                x=cursor.x + advance * math.cos(bearing),
                y=cursor.y + advance * math.sin(bearing),
                z=min(self._max_alt, max(self._min_alt, cursor.z + climb)),
            )
            points.append(TrajectoryPoint(t_offset_ns=step_time_ns * i, position=cursor))

        if not points:
            points.append(TrajectoryPoint(t_offset_ns=0, position=goal.target))

        return Trajectory(
            start_t_sim_ns=ctx.t_sim_ns,
            points=tuple(points),
            planner_name=self.name,
            feasible=True,
        )

    def _free_bearing(self, desired_world_bearing: float, ctx: DecisionContext) -> float | None:
        """Smallest deflection from the desired bearing with adequate clearance."""
        if not ctx.observation.range_rays:
            return desired_world_bearing
        return widest_free_bearing(
            ctx.observation,
            desired_world_bearing,
            required_clearance_m=self._required_clearance_m,
            max_deflection_rad=self.max_deflection_rad,
            step_rad=self.deflection_step_rad,
        )

    @staticmethod
    def _clearance_at(world_bearing: float, ctx: DecisionContext) -> float:
        return min_clearance(ctx.observation, world_bearing)

    def _climb_escape(self, ctx: DecisionContext) -> Trajectory | None:
        """Vertical escape when the horizontal fan is fully blocked."""
        if not self.climb_when_blocked:
            return None
        position = ctx.observation.position
        target_z = min(self._max_alt, position.z + 3.0)
        if target_z - position.z < 0.5:
            return None
        return Trajectory(
            start_t_sim_ns=ctx.t_sim_ns,
            points=(
                TrajectoryPoint(
                    t_offset_ns=s_to_ns(1.0),
                    position=Vec3(x=position.x, y=position.y, z=target_z),
                ),
            ),
            planner_name=f"{self.name}(climb_escape)",
            feasible=True,
            reason="horizontal fan blocked; climbing",
        )


@register("planner", "straight_line")
class StraightLinePlanner:
    """No obstacle reasoning at all.

    Exists as the planner-ablation control: pairing it with a waypoint policy
    isolates how much of a waypoint architecture's safety comes from the planner
    rather than from the semantic model.
    """

    def __init__(self, **params: Any) -> None:
        self.step_m = float(params.get("step_m", 3.0))

    @property
    def name(self) -> str:
        return "straight_line"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        return None

    def plan(self, goal: WaypointGoal, ctx: DecisionContext) -> Trajectory:
        return Trajectory(
            start_t_sim_ns=ctx.t_sim_ns,
            points=(TrajectoryPoint(t_offset_ns=s_to_ns(1.0), position=goal.target),),
            planner_name=self.name,
            feasible=True,
        )
