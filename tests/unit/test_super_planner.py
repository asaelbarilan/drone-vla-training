"""Mechanism tests for the SUPER-derived shared execution substrate."""

from __future__ import annotations

import math
from pathlib import Path

from uavlab.contracts import (
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    TaskFamily,
    Vec3,
    WaypointGoal,
)
from uavlab.core.compose import load_architecture
from uavlab.interfaces import DecisionContext
from uavlab.plugins.planning.super import SuperLocalPlanner

MISSION = MissionSpec(
    mission_id="super-unit",
    instruction="reach the goal",
    task_family=TaskFamily.LONG_HORIZON_NAV,
)


def observation(*, privileged=None, ranges: tuple[float, ...] | None = None) -> ObservationPacket:
    bearings = tuple(-math.pi + i * (2.0 * math.pi / 24) for i in range(24))
    return ObservationPacket(
        seq=1,
        t_sim_ns=0,
        t_wall_ns=0,
        position=Vec3(x=0.0, y=0.0, z=3.0),
        velocity=Vec3(x=4.0, y=0.0, z=0.0),
        yaw_rad=0.0,
        range_rays=ranges if ranges is not None else (25.0,) * 24,
        ray_bearings_rad=bearings if ranges is not None or ranges != () else (),
        privileged=privileged,
    )


def context(obs: ObservationPacket) -> DecisionContext:
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="super-unit",
    )


GOAL = WaypointGoal(target=Vec3(x=40.0, y=0.0, z=3.0))


def test_super_builds_exploratory_and_known_free_stopping_backup():
    planner = SuperLocalPlanner(planning_horizon_m=30.0)
    planner.reset(MISSION, seed=1000)

    trajectory = planner.plan(GOAL, context(observation()))
    diagnostics = planner.last_diagnostics

    assert trajectory.feasible
    assert diagnostics.path_search_succeeded
    assert diagnostics.backup_required
    assert diagnostics.exploratory_points > diagnostics.committed_points
    assert diagnostics.backup_points >= 2
    assert diagnostics.backup_known_free
    assert trajectory.points[-1].velocity == Vec3(x=0.0, y=0.0, z=0.0)
    assert trajectory.metadata["replan_status"] == "success_with_backup"
    assert trajectory.metadata["reaches_goal"] == "false"


def test_super_preserves_a_same_xy_vertical_segment():
    planner = SuperLocalPlanner(planning_horizon_m=30.0)
    planner.reset(MISSION, seed=1000)
    altitude_goal = WaypointGoal(target=Vec3(x=0.0, y=0.0, z=5.0))

    trajectory = planner.plan(altitude_goal, context(observation()))

    assert trajectory.feasible
    assert trajectory.points
    assert trajectory.points[-1].position == altitude_goal.target
    assert trajectory.metadata["reaches_goal"] == "true"
    assert planner.last_diagnostics.path_search_succeeded


def test_failed_replan_preserves_the_previous_safe_commitment():
    planner = SuperLocalPlanner(planning_horizon_m=30.0)
    planner.reset(MISSION, seed=1000)
    first = planner.plan(GOAL, context(observation()))

    blind = observation(ranges=())
    failed = planner.plan(GOAL, context(blind))

    assert first.feasible and not failed.feasible
    assert planner.last_committed == first
    assert planner.last_diagnostics.retained_previous_commitment
    assert failed.metadata["retained_previous_commitment"] == "true"


def test_super_never_uses_the_oracle_privileged_obstacle_channel():
    fake_truth = {
        "goal": [40.0, 0.0, 3.0],
        "obstacles": [{"center": [2.0, 0.0, 3.0], "half": [50.0, 50.0, 50.0]}],
    }
    plain = SuperLocalPlanner(planning_horizon_m=30.0)
    oracle_channel = SuperLocalPlanner(planning_horizon_m=30.0)
    plain.reset(MISSION, seed=1000)
    oracle_channel.reset(MISSION, seed=1000)

    without = plain.plan(GOAL, context(observation()))
    with_fake_truth = oracle_channel.plan(
        GOAL,
        context(observation(privileged=fake_truth)),
    )

    assert without == with_fake_truth


def test_reset_erases_map_and_commitment_state():
    planner = SuperLocalPlanner(planning_horizon_m=30.0)
    planner.reset(MISSION, seed=1000)
    assert planner.plan(GOAL, context(observation())).feasible
    assert planner.last_committed is not None

    planner.reset(MISSION, seed=1001)

    assert planner.last_committed is None
    assert planner.last_diagnostics.reason == "reset"


def test_super_is_shared_by_every_skill_and_waypoint_configuration():
    config_root = Path(__file__).resolve().parents[2] / "configs"
    for architecture_id in ("c0", "c1", "c2", "c3", "c4", "c5", "c6"):
        architecture = load_architecture(architecture_id, config_root)
        assert architecture.planner is not None
        assert architecture.planner.name == "super_local"
