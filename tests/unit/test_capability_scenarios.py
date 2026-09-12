"""Capability scoring, sensing privacy, determinism and negative controls."""

import asyncio
import math

import numpy as np
import pytest

from uavlab.adapters.gym.capability_env import SCENARIOS, point
from uavlab.contracts import ControlCommand, MissionSpec, Vec3
from uavlab.contracts.mission import SuccessCriteria
from uavlab.core.compose import load_environment
from uavlab.core.frame_store import global_store
from uavlab.core.registry import REGISTRY


def make_env(name, **params):
    config = load_environment("capability_" + name)
    mission = MissionSpec(
        mission_id="fixture",
        instruction=config.instruction,
        task_family=config.task_family,
        success=SuccessCriteria.model_validate(config.params["success"]),
    )
    env = REGISTRY.build("environment", config.adapter.name, dict(config.params, **params))
    return env, mission


async def step(env, velocity=(0, 0, 0), yaw=0, steps=1):
    for _ in range(steps):
        await env.step(
            ControlCommand(
                t_sim_ns=env._t_ns,
                velocity=Vec3(x=velocity[0], y=velocity[1], z=velocity[2]),
                yaw_rate_rps=yaw,
            ),
            50_000_000,
        )


@pytest.mark.parametrize("name", SCENARIOS)
def test_reset_images_privacy_and_determinism(name):
    async def check():
        env, mission = make_env(name)
        a = await env.reset(mission, 1061)
        pixels = np.asarray(global_store().get(a.rgb.uri)).copy()
        assert a.semantic_hits == () and a.privileged is None
        assert a.coarse_goal_direction is None
        assert a.rgb.shape and a.depth.shape
        assert not env.status().task_complete
        await step(env, (1, 0, 0), steps=5)
        pose = env.vehicle.position.copy()
        b = await env.reset(mission, 1061)
        np.testing.assert_array_equal(pixels, np.asarray(global_store().get(b.rgb.uri)))
        # Extra reads must not advance objectives or perturb the physical outcome.
        for _ in range(5):
            await env.observe()
            env.status()
        await step(env, (1, 0, 0), steps=5)
        np.testing.assert_array_equal(pose, env.vehicle.position)

    asyncio.run(check())


def test_search_requires_turn_and_reveals_target():
    async def check():
        env, mission = make_env("turn_search")
        await env.reset(mission, 1061)
        assert not env.status().goal_visible
        await step(env, yaw=math.pi / 2, steps=30)
        assert env.status().goal_visible
        assert env.status().extras["target_ever_visible"] == 1
        assert not env.status().task_complete

    asyncio.run(check())


def test_ordered_visit_rejects_final_goal_shortcut():
    async def check():
        env, mission = make_env("ordered_visit")
        await env.reset(mission, 1061)
        env.vehicle.position = env.goal.copy()
        await step(env, steps=12)
        assert not env.status().task_complete
        env.vehicle.position = env.subgoals[0].copy()
        await step(env, steps=12)
        assert env.status().subgoals_completed == 1
        assert not env.status().task_complete
        env.vehicle.position = env.goal.copy()
        await step(env, steps=12)
        assert env.status().task_complete

    asyncio.run(check())


@pytest.mark.parametrize(
    "blocked,side,success", [(True, -1, True), (False, 1, True), (False, -1, False)]
)
def test_conditional_gate_scores_the_requested_branch(blocked, side, success):
    async def check():
        env, mission = make_env("conditional_gate", left_blocked=blocked)
        await env.reset(mission, 1061)
        # Local crossing unit probe; full continuous trajectories are validated separately.
        env.vehicle.position = point(7.9, side * 5)
        env.vehicle.velocity = point(2, 0, 0)
        await step(env, (2, 0, 0), steps=4)
        env.vehicle.velocity[:] = 0
        env.vehicle.position = env.goal.copy()
        await step(env, steps=12)
        assert env.status().task_complete is success

    asyncio.run(check())


def test_closure_changes_rgb_depth_and_collision_geometry_at_fixed_time():
    async def check():
        env, mission = make_env("closing_passage")
        a = await env.reset(mission, 1061)
        rgb = np.asarray(global_store().get(a.rgb.uri)).copy()
        depth = np.asarray(global_store().get(a.depth.uri)).copy()
        await step(env, steps=60)
        assert len(env.obstacles) == 2
        await step(env)
        b = await env.observe()
        assert len(env.obstacles) == 3 and len(env.task_events) == 1
        assert not np.array_equal(rgb, np.asarray(global_store().get(b.rgb.uri)))
        assert not np.array_equal(depth, np.asarray(global_store().get(b.depth.uri)))
        assert not env.status().collided
        assert env.obstacles[-1].distance(point(14)) < 0

    asyncio.run(check())


def test_stationary_vehicle_cannot_pass_following():
    async def check():
        env, mission = make_env("follow_target")
        await env.reset(mission, 1061)
        await step(env, steps=420)
        assert not env.status().task_complete
        assert env.goal[0] == pytest.approx(22.7)
        assert env.status().extras["tracking_total_s"] == pytest.approx(15)

    asyncio.run(check())


def test_sustained_tracking_passes_outside_arrival_radius():
    async def check():
        env, mission = make_env("follow_target")
        await env.reset(mission, 1061)
        env.vehicle.position = point(3)
        env.vehicle.velocity = point(0.7, 0, 0)
        await step(env, (0.7, 0, 0), steps=402)
        status = env.status()
        assert status.task_complete
        assert status.distance_to_goal_m == pytest.approx(5)
        assert status.extras["tracking_fraction"] == pytest.approx(1)

    asyncio.run(check())


def test_vehicle_identity_is_orientation_only_and_wrong_car_fails():
    async def check():
        for seed in [1060, 1061]:
            env, mission = make_env("overturned_vehicle")
            obs = await env.reset(mission, seed)
            assert obs.semantic_hits == ()
            assert len(env.obstacles) == 12 and not env.landmarks
            assert all(o.label == "obstacle" for o in env.obstacles)
            env.vehicle.position = point(12, -env.target_side * 4, 3.2)
            await step(env, steps=12)
            assert not env.status().task_complete
            env.vehicle.position = env.goal.copy()
            await step(env, steps=12)
            assert env.status().task_complete

    asyncio.run(check())


@pytest.mark.parametrize("complete,distance,expected", [(False, 0, False), (True, 5, True)])
def test_runtime_uses_task_gate_instead_of_distance(complete, distance, expected):
    from types import SimpleNamespace

    from uavlab.analysis.metrics import compute_metrics
    from uavlab.contracts import TerminationReason
    from uavlab.contracts.env_status import EnvironmentStatus
    from uavlab.core.compose import load_architecture
    from uavlab.core.config import EpisodeSpec
    from uavlab.core.orchestrator import Orchestrator

    runner = Orchestrator(
        load_architecture("c0"),
        load_environment("capability_follow_target"),
        EpisodeSpec(episode_id="gate", seed=1061),
    )
    runner._build_components()  # simulated inference only; never run the policy
    state = EnvironmentStatus(
        t_sim_ns=0,
        position=Vec3(x=0, y=0, z=3),
        distance_to_goal_m=distance,
        task_complete=complete,
    )
    runner.env = SimpleNamespace(status=lambda: state)
    assert runner._check_termination() is expected
    runner._termination = TerminationReason.GOAL_REACHED
    assert runner._succeeded() is expected
    runner.router.stop_requested = True
    metrics = compute_metrics(
        log=runner.log,
        router=runner.router,
        scheduler=runner.scheduler,
        status=state,
        sim_duration_ns=0,
        arch=runner.arch,
        inference=None, feature_cache=runner.feature_cache, reached_goal_t_ns=None,
    )
    assert metrics["correct_terminal_stop"] == float(expected)
