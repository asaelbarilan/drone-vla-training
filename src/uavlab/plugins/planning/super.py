"""SUPER-derived safety-assured local planning.

This independently reproduces the planning mechanism in Ren et al., Science
Robotics 2025 behind the testbed's existing planner interface. The local range
fan replaces a 3-D LiDAR cloud and the shared controller replaces OMMPC, while
the defining contract remains: unknown-permissive exploratory planning, a
known-free stopping backup, and preservation of the previous safe commitment
when replanning fails.
"""

from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass
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
from uavlab.core.sensing import min_clearance
from uavlab.interfaces import DecisionContext

Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class SuperDiagnostics:
    """Inspectable evidence for one replan; never consumed by the controller."""

    replan_index: int
    exploratory_points: int
    committed_points: int
    backup_points: int
    backup_required: bool
    backup_known_free: bool
    backup_terminal_speed_mps: float
    path_search_succeeded: bool
    retained_previous_commitment: bool
    reason: str


@register("planner", "super_local")
class SuperLocalPlanner:
    """Point-evidence A* with a known-free stopping commitment.

    Map evidence comes exclusively from ``ObservationPacket.range_rays``.
    Unknown cells are traversable by the exploratory A*, matching SUPER's
    default front end. Only the committed prefix and backup must be visibly
    known-free. The privileged observation channel is deliberately never read.
    """

    def __init__(self, **params: Any) -> None:
        self.resolution_m = float(params.get("resolution_m", 0.5))
        self.planning_horizon_m = float(params.get("planning_horizon_m", 16.0))
        self.sensing_horizon_m = float(params.get("sensing_horizon_m", 25.0))
        self.path_step_m = float(params.get("path_step_m", 1.0))
        self.commit_horizon_m = float(params.get("commit_horizon_m", 2.5))
        self.line_seed_max_m = float(params.get("line_seed_max_m", 3.0))
        self.temporal_window_s = float(params.get("temporal_window_s", 12.0))
        self.max_acc_mps2 = float(params.get("max_acc_mps2", 4.0))
        self.braking_margin_m = float(params.get("braking_margin_m", 1.0))
        self.clearance_margin_m = float(params.get("clearance_margin_m", 0.25))
        self.max_search_nodes = int(params.get("max_search_nodes", 25_000))
        self.path_deviation_cost = float(params.get("path_deviation_cost", 0.35))
        self.new_goal_threshold_m = float(params.get("new_goal_threshold_m", 4.0))
        if self.resolution_m <= 0 or self.planning_horizon_m <= 0:
            raise ValueError("SUPER resolution and planning horizon must be positive")

        self._min_alt = 0.5
        self._max_alt = 30.0
        self._max_speed = 5.0
        self._required_clearance = 0.85
        self._visibility_clearance = 0.85
        self._free: dict[Cell, int] = {}
        self._occupied: dict[Cell, int] = {}
        self._replan_index = 0
        self._last_committed: Trajectory | None = None
        self._guide_cells: set[Cell] = set()
        self._last_goal: Vec3 | None = None
        self.last_diagnostics = self._diagnostics("not run")

    @property
    def name(self) -> str:
        return "super_local"

    @property
    def last_committed(self) -> Trajectory | None:
        """The safe commitment retained across a failed replan."""
        return self._last_committed

    def reset(self, mission: MissionSpec, seed: int) -> None:
        del seed
        self._min_alt = mission.constraints.min_altitude_m
        self._max_alt = mission.constraints.max_altitude_m
        self._max_speed = mission.constraints.max_speed_mps
        self._required_clearance = (
            mission.constraints.min_obstacle_clearance_m + self.clearance_margin_m
        )
        self._visibility_clearance = (
            mission.constraints.min_obstacle_clearance_m + self.clearance_margin_m * 0.2
        )
        self._free.clear()
        self._occupied.clear()
        self._replan_index = 0
        self._last_committed = None
        self._guide_cells.clear()
        self._last_goal = None
        self.last_diagnostics = self._diagnostics("reset")

    def plan(self, goal: WaypointGoal, ctx: DecisionContext) -> Trajectory:
        self._replan_index += 1
        new_semantic_goal = (
            self._last_goal is None
            or self._last_goal.distance_to(goal.target) > self.new_goal_threshold_m
        )
        if new_semantic_goal:
            # The official API distinguishes replanning one goal from receiving
            # a new mission goal. Hot-start continuity is correct only for the
            # former; carrying it into a new semantic/search waypoint can make
            # the local planner resist the architecture's new intent.
            self._guide_cells.clear()
        self._last_goal = goal.target
        obs = ctx.observation
        if not obs.range_rays or len(obs.range_rays) != len(obs.ray_bearings_rad):
            return self._failed(ctx, "no valid geometric range observation")

        self._update_evidence(ctx)
        start = obs.position
        local_goal = self._bounded_goal(start, goal.target)
        cells = self._astar(self._cell(start.x, start.y), self._cell(local_goal.x, local_goal.y))
        if not cells:
            return self._failed(ctx, "exploratory A* found no collision-free path")

        if len(cells) == 1:
            # The 2-D A* quite correctly returns one cell for a pure altitude
            # change.  Preserve that vertical segment explicitly; assigning
            # both endpoints into a one-element list used to collapse it to a
            # zero-length path and made every same-XY climb infeasible.
            raw_path = (
                [start, local_goal]
                if start.distance_to(local_goal) > 1e-6
                else [start]
            )
        else:
            raw_path = [
                Vec3(
                    x=cell[0] * self.resolution_m,
                    y=cell[1] * self.resolution_m,
                    z=self._interpolated_altitude(start, local_goal, i, len(cells)),
                )
                for i, cell in enumerate(cells)
            ]
            raw_path[0] = start
            raw_path[-1] = local_goal
        exploratory = self._resample(self._shorten(raw_path))
        if len(exploratory) < 2:
            return self._failed(ctx, "exploratory corridor contains no executable segment")

        visible_end = self._known_free_prefix(exploratory, ctx)
        if visible_end < 1:
            return self._failed(ctx, "no known-free prefix is long enough to commit")

        all_known_free = visible_end == len(exploratory) - 1
        if all_known_free:
            branch_index = visible_end
            backup_points = 0
        else:
            branch_index = self._backup_switch_index(exploratory, visible_end, obs.velocity.norm())
            if branch_index >= visible_end:
                branch_index = max(0, visible_end - 1)
            backup_points = visible_end - branch_index + 1

        committed = exploratory[: visible_end + 1]
        backup_known_free = all(
            self._visible_and_clear(point, ctx) for point in committed[branch_index:]
        )
        if not backup_known_free:
            return self._failed(ctx, "backup branch is not wholly known-free")

        trajectory = self._trajectory(
            committed,
            ctx,
            exploratory_points=len(exploratory),
            branch_index=branch_index,
            backup_points=backup_points,
            backup_required=not all_known_free,
            reaches_goal=(all_known_free and local_goal.distance_to(goal.target) < 1e-6),
        )
        trajectory = trajectory.model_copy(
            update={
                "metadata": {
                    **trajectory.metadata,
                    "semantic_goal_xyz": (
                        f"{goal.target.x:.3f},{goal.target.y:.3f},{goal.target.z:.3f}"
                    ),
                    "new_semantic_goal": str(new_semantic_goal).lower(),
                }
            }
        )
        self._guide_cells = set(cells)
        self._last_committed = trajectory
        self.last_diagnostics = SuperDiagnostics(
            replan_index=self._replan_index,
            exploratory_points=len(exploratory),
            committed_points=len(committed),
            backup_points=backup_points,
            backup_required=not all_known_free,
            backup_known_free=True,
            backup_terminal_speed_mps=0.0,
            path_search_succeeded=True,
            retained_previous_commitment=False,
            reason="success with backup" if not all_known_free else "success; wholly known-free",
        )
        return trajectory

    def _diagnostics(self, reason: str) -> SuperDiagnostics:
        return SuperDiagnostics(
            replan_index=self._replan_index,
            exploratory_points=0,
            committed_points=0,
            backup_points=0,
            backup_required=False,
            backup_known_free=False,
            backup_terminal_speed_mps=0.0,
            path_search_succeeded=False,
            retained_previous_commitment=False,
            reason=reason,
        )

    def _failed(self, ctx: DecisionContext, reason: str) -> Trajectory:
        retained = self._last_committed is not None
        self.last_diagnostics = SuperDiagnostics(
            replan_index=self._replan_index,
            exploratory_points=0,
            committed_points=len(self._last_committed.points) if self._last_committed else 0,
            backup_points=0,
            backup_required=False,
            backup_known_free=False,
            backup_terminal_speed_mps=0.0,
            path_search_succeeded=False,
            retained_previous_commitment=retained,
            reason=reason,
        )
        return Trajectory(
            start_t_sim_ns=ctx.t_sim_ns,
            points=(),
            planner_name=self.name,
            feasible=False,
            reason=reason,
            metadata={
                "paper": "SUPER",
                "replan_status": "failed",
                "retained_previous_commitment": str(retained).lower(),
            },
        )

    # -- point-evidence map and exploratory front end ---------------------

    def _update_evidence(self, ctx: DecisionContext) -> None:
        obs = ctx.observation
        cutoff = ctx.t_sim_ns - s_to_ns(self.temporal_window_s)
        self._free = {cell: stamp for cell, stamp in self._free.items() if stamp >= cutoff}
        self._occupied = {cell: stamp for cell, stamp in self._occupied.items() if stamp >= cutoff}
        half_step = self.resolution_m * 0.5
        for body_bearing, measured in zip(
            obs.ray_bearings_rad, obs.range_rays, strict=True
        ):
            distance = min(max(0.0, measured), self.sensing_horizon_m)
            bearing = obs.yaw_rad + body_bearing
            cosine, sine = math.cos(bearing), math.sin(bearing)
            d = half_step
            while d < max(0.0, distance - half_step):
                cell = self._cell(obs.position.x + cosine * d, obs.position.y + sine * d)
                self._free[cell] = ctx.t_sim_ns
                d += self.resolution_m
            if measured < self.sensing_horizon_m - half_step:
                hit = self._cell(
                    obs.position.x + cosine * measured,
                    obs.position.y + sine * measured,
                )
                self._occupied[hit] = ctx.t_sim_ns
                self._free.pop(hit, None)

    def _astar(self, start: Cell, goal: Cell) -> list[Cell]:
        escape: list[Cell] = []
        search_start = start
        if self._blocked(start):
            escape = self._escape_path(start, goal)
            if not escape:
                return []
            search_start = escape[-1]
        shifted_goal = self._nearest_unblocked(goal)
        if shifted_goal is None:
            return []
        goal = shifted_goal
        radius = math.ceil(self.planning_horizon_m / self.resolution_m) + 3
        min_x, max_x = start[0] - radius, start[0] + radius
        min_y, max_y = start[1] - radius, start[1] + radius
        neighbours = (
            (-1, -1, math.sqrt(2.0)), (0, -1, 1.0), (1, -1, math.sqrt(2.0)),
            (-1, 0, 1.0), (1, 0, 1.0),
            (-1, 1, math.sqrt(2.0)), (0, 1, 1.0), (1, 1, math.sqrt(2.0)),
        )
        guide_tube = {
            (cell[0] + dx, cell[1] + dy)
            for cell in self._guide_cells
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
        }
        order = itertools.count()
        queue: list[tuple[float, int, Cell]] = [
            (self._heuristic(search_start, goal), next(order), search_start)
        ]
        came_from: dict[Cell, Cell] = {}
        cost = {search_start: 0.0}
        closed: set[Cell] = set()
        while queue and len(closed) < self.max_search_nodes:
            _, _, current = heapq.heappop(queue)
            if current in closed:
                continue
            if current == goal:
                path = self._reconstruct(came_from, current)
                return escape[:-1] + path if escape else path
            closed.add(current)
            for dx, dy, step_cost in neighbours:
                nxt = (current[0] + dx, current[1] + dy)
                if not (min_x <= nxt[0] <= max_x and min_y <= nxt[1] <= max_y):
                    continue
                if self._blocked(nxt):
                    continue
                deviation = (
                    self.path_deviation_cost
                    if guide_tube and nxt not in guide_tube
                    else 0.0
                )
                new_cost = cost[current] + step_cost + deviation
                if new_cost >= cost.get(nxt, float("inf")):
                    continue
                cost[nxt] = new_cost
                came_from[nxt] = current
                heapq.heappush(
                    queue,
                    (new_cost + self._heuristic(nxt, goal), next(order), nxt),
                )
        return []

    def _escape_path(self, start: Cell, goal: Cell) -> list[Cell]:
        """Leave an inflated clearance zone without crossing an observed hit."""
        max_steps = math.ceil(3.0 / self.resolution_m)
        neighbours = (
            (-1, -1), (0, -1), (1, -1),
            (-1, 0), (1, 0),
            (-1, 1), (0, 1), (1, 1),
        )
        queue: list[tuple[int, float, Cell]] = [(0, self._heuristic(start, goal), start)]
        parent: dict[Cell, Cell] = {}
        distance = {start: 0}
        while queue:
            steps, _, current = heapq.heappop(queue)
            if current != start and not self._blocked(current):
                return self._reconstruct(parent, current)
            if steps >= max_steps:
                continue
            for dx, dy in neighbours:
                nxt = (current[0] + dx, current[1] + dy)
                new_steps = steps + 1
                if new_steps >= distance.get(nxt, max_steps + 1):
                    continue
                if nxt in self._occupied:
                    continue
                distance[nxt] = new_steps
                parent[nxt] = current
                heapq.heappush(queue, (new_steps, self._heuristic(nxt, goal), nxt))
        return []

    def _blocked(self, cell: Cell) -> bool:
        radius = math.ceil(self._required_clearance / self.resolution_m)
        limit2 = (self._required_clearance / self.resolution_m) ** 2
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx * dx + dy * dy <= limit2 and (
                    cell[0] + dx,
                    cell[1] + dy,
                ) in self._occupied:
                    return True
        return False

    def _nearest_unblocked(self, goal: Cell) -> Cell | None:
        if not self._blocked(goal):
            return goal
        max_ring = math.ceil(3.0 / self.resolution_m)
        for ring in range(1, max_ring + 1):
            candidates: list[Cell] = []
            for dx in range(-ring, ring + 1):
                candidates.extend(((goal[0] + dx, goal[1] - ring), (goal[0] + dx, goal[1] + ring)))
            for dy in range(-ring + 1, ring):
                candidates.extend(((goal[0] - ring, goal[1] + dy), (goal[0] + ring, goal[1] + dy)))
            for candidate in sorted(set(candidates)):
                if not self._blocked(candidate):
                    return candidate
        return None

    # -- corridor approximation and two-trajectory commitment ------------

    def _shorten(self, path: list[Vec3]) -> list[Vec3]:
        if len(path) <= 2:
            return path
        out = [path[0]]
        index = 0
        while index < len(path) - 1:
            chosen = index + 1
            for candidate in range(index + 1, len(path)):
                if (
                    path[index].distance_to(path[candidate])
                    > self.line_seed_max_m + self.resolution_m
                ):
                    break
                if self._line_clear(path[index], path[candidate]):
                    chosen = candidate
            out.append(path[chosen])
            index = chosen
        return out

    def _resample(self, seeds: list[Vec3]) -> list[Vec3]:
        out = [seeds[0]]
        for a, b in itertools.pairwise(seeds):
            distance = a.distance_to(b)
            parts = max(1, math.ceil(distance / self.path_step_m))
            for index in range(1, parts + 1):
                t = index / parts
                point = Vec3(
                    x=a.x + (b.x - a.x) * t,
                    y=a.y + (b.y - a.y) * t,
                    z=min(self._max_alt, max(self._min_alt, a.z + (b.z - a.z) * t)),
                )
                if out[-1].distance_to(point) > 1e-6:
                    out.append(point)
        return out

    def _known_free_prefix(self, path: list[Vec3], ctx: DecisionContext) -> int:
        last = 0
        travelled = 0.0
        for index, point in enumerate(path[1:], start=1):
            travelled += path[index - 1].distance_to(point)
            if travelled > self.commit_horizon_m + 1e-9:
                break
            if not self._visible_and_clear(point, ctx):
                break
            last = index
        return last

    def _visible_and_clear(self, point: Vec3, ctx: DecisionContext) -> bool:
        origin = ctx.observation.position
        dx, dy = point.x - origin.x, point.y - origin.y
        horizontal = math.hypot(dx, dy)
        if horizontal < 1e-9:
            return True
        if horizontal > self.sensing_horizon_m - self._visibility_clearance:
            return False
        return min_clearance(ctx.observation, math.atan2(dy, dx)) >= (
            horizontal + self._visibility_clearance
        )

    def _backup_switch_index(self, path: list[Vec3], end: int, speed_mps: float) -> int:
        stopping_distance = (
            speed_mps * speed_mps / (2.0 * max(self.max_acc_mps2, 1e-6))
            + self.braking_margin_m
        )
        accumulated = 0.0
        index = end
        while index > 0 and accumulated < stopping_distance:
            accumulated += path[index].distance_to(path[index - 1])
            index -= 1
        return index

    def _trajectory(
        self,
        committed: list[Vec3],
        ctx: DecisionContext,
        *,
        exploratory_points: int,
        branch_index: int,
        backup_points: int,
        backup_required: bool,
        reaches_goal: bool,
    ) -> Trajectory:
        elapsed_s = 0.0
        points: list[TrajectoryPoint] = []
        cruise = max(0.5, min(self._max_speed, 4.0))
        for index, (a, b) in enumerate(itertools.pairwise(committed), start=1):
            length = a.distance_to(b)
            elapsed_s += length / cruise
            velocity = (
                Vec3(
                    x=(b.x - a.x) * cruise / max(length, 1e-9),
                    y=(b.y - a.y) * cruise / max(length, 1e-9),
                    z=(b.z - a.z) * cruise / max(length, 1e-9),
                )
                if index < len(committed) - 1
                else Vec3(x=0.0, y=0.0, z=0.0)
            )
            points.append(
                TrajectoryPoint(
                    t_offset_ns=s_to_ns(elapsed_s),
                    position=b,
                    velocity=velocity,
                    yaw_rad=math.atan2(b.y - a.y, b.x - a.x),
                )
            )
        return Trajectory(
            start_t_sim_ns=ctx.t_sim_ns,
            points=tuple(points),
            planner_name=self.name,
            feasible=True,
            reason=(
                "SUPER exploratory prefix plus known-free stopping backup"
                if backup_required
                else "SUPER exploratory trajectory wholly known-free"
            ),
            metadata={
                "paper": "SUPER",
                "replan_status": "success_with_backup" if backup_required else "success_no_backup",
                "exploratory_points": str(exploratory_points),
                "committed_points": str(len(committed)),
                "exploratory_prefix_points": str(branch_index + 1),
                "backup_points": str(backup_points),
                "backup_known_free": "true",
                "backup_terminal_speed_mps": "0.0",
                "unknown_allowed_in_exploratory": "true",
                "reaches_goal": str(reaches_goal).lower(),
            },
        )

    # -- geometry helpers -------------------------------------------------

    def _bounded_goal(self, start: Vec3, goal: Vec3) -> Vec3:
        dx, dy = goal.x - start.x, goal.y - start.y
        # Stay level during long horizontal exploration, then resolve the
        # requested altitude once the vehicle is horizontally at the semantic
        # goal.  Using full 3-D distance for this condition created a deadlock:
        # a 12 m altitude error could never become <=4 m because the planner
        # refused to command any vertical motion until it already was.
        horizontal = math.hypot(dx, dy)
        terminal_z = goal.z if horizontal <= 4.0 else start.z
        bounded_dz = terminal_z - start.z
        distance = math.sqrt(dx * dx + dy * dy + bounded_dz * bounded_dz)
        if distance <= self.planning_horizon_m:
            return Vec3(
                x=goal.x,
                y=goal.y,
                z=min(self._max_alt, max(self._min_alt, terminal_z)),
            )
        scale = self.planning_horizon_m / max(distance, 1e-9)
        return Vec3(
            x=start.x + dx * scale,
            y=start.y + dy * scale,
            z=min(
                self._max_alt,
                max(self._min_alt, start.z + bounded_dz * scale),
            ),
        )

    def _line_clear(self, a: Vec3, b: Vec3) -> bool:
        distance = a.distance_to(b)
        samples = max(1, math.ceil(distance / (self.resolution_m * 0.5)))
        for index in range(samples + 1):
            t = index / samples
            if self._blocked(self._cell(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)):
                return False
        return True

    def _cell(self, x: float, y: float) -> Cell:
        return (
            math.floor(x / self.resolution_m + 0.5),
            math.floor(y / self.resolution_m + 0.5),
        )

    @staticmethod
    def _heuristic(a: Cell, b: Cell) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    @staticmethod
    def _reconstruct(came_from: dict[Cell, Cell], current: Cell) -> list[Cell]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    @staticmethod
    def _interpolated_altitude(start: Vec3, goal: Vec3, index: int, total: int) -> float:
        if total <= 1:
            return goal.z
        t = index / (total - 1)
        return start.z + (goal.z - start.z) * t
