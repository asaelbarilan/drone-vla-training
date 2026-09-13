"""Public hover completion: geometry, real cadence and current view negatives."""

import asyncio
import math

import numpy as np
import pytest

from tests.unit.test_capability_scenarios import make_env, point
from uavlab.contracts import Vec3
from uavlab.plugins.reasoning.onfly_hover import OnFlyHoverMonitor


def fixture():
    env, mission = make_env("approach_hover")
    asyncio.run(env.reset(mission, 1061))
    env.vehicle.position = point(11)
    obs = asyncio.run(env.observe())
    monitor = OnFlyHoverMonitor(
        current_grounding=True,
        target_bound_stop=True,
        structured_evidence=True,
        arrival_memory_s=4,
        camera_pitch_rad=-0.1,
    )
    monitor.reset(mission, 1061)
    monitor._tracked_target = point(12)
    monitor._tracked_target_t_ns = 0
    monitor._tracked_confirmations = 2
    monitor._approach = np.array([1.0, 0.0, 0.0])
    monitor._initial_position = Vec3(x=0, y=0, z=3)
    return obs, monitor


def test_hover_needs_continuous_slow_visible_dwell_then_live_recheck():
    obs, m = fixture()
    for i in range(40):
        o = obs.model_copy(update={"seq": i + 1, "t_sim_ns": i * 50_000_000})
        m.observe_task_evidence(o, {})
        assert not m.stop_still_supported(o)
    o = obs.model_copy(update={"seq": 41, "t_sim_ns": 2_000_000_000})
    m.observe_task_evidence(o, {})
    assert m.stop_still_supported(o)
    for update in [
        {"velocity": Vec3(x=1, y=0, z=0)},
        {"yaw_rad": math.pi},
        {"position": Vec3(x=13, y=0, z=3)},
        {"t_sim_ns": 4_000_000_001},
    ]:
        assert not m.stop_still_supported(o.model_copy(update=update))
    m.observe_task_evidence(o.model_copy(update={"t_sim_ns": 2_500_000_000}), {})
    assert m._hover_s == 0


@pytest.mark.parametrize("failure", ["occluded", "no_depth", "unconfirmed", "moved_target"])
def test_hover_cannot_be_completed_with_missing_or_changed_evidence(failure):
    obs, m = fixture()
    for i in range(35):
        m.observe_task_evidence(obs.model_copy(update={"t_sim_ns": i * 50_000_000}), {})
    if failure == "occluded":
        from uavlab.core.frame_store import global_store

        depth = global_store().get(obs.depth.uri)
        global_store().put(obs.depth.uri, np.full_like(depth, 0.3))
    elif failure == "no_depth":
        obs = obs.model_copy(update={"depth": None})
    elif failure == "unconfirmed":
        m._tracked_confirmations = 1
    else:
        m._tracked_target += np.array([0, 0.3, 0])
    obs = obs.model_copy(update={"t_sim_ns": 1_750_000_000})
    m.observe_task_evidence(obs, {})
    assert m._hover_s == 0
    assert not m.stop_still_supported(obs)


def test_temporal_reference_is_explicit_and_current_frame_remains_last():
    obs, m = fixture()
    prompt, images = m._grounding_context(None, "query", ["current"])
    assert images == ["current"]
    m._reference_image = "earlier"
    prompt, images = m._grounding_context(None, "query", ["current"])
    assert images == ["earlier", "current"]
    assert "SECOND image ONLY" in prompt
    assert "History alone cannot prove current visibility" in prompt


def test_target_pixel_height_cannot_move_the_public_approach_line():
    obs, m = fixture()
    # Both vehicle and inferred target move down; relative target range is valid
    # but initial flight-level approach is violated, as in trial 3.
    m._tracked_target[2] -= 0.4
    obs = obs.model_copy(update={"position": Vec3(x=11, y=0, z=2.6)})
    for i in range(60):
        m.observe_task_evidence(obs.model_copy(update={"t_sim_ns": i * 50_000_000}), {})
    assert m._hover_s == 0
    assert not m.stop_still_supported(obs)


def test_level_approach_preserves_altitude_and_forward_depth_ceiling():
    from tests.unit.test_onfly import MISSION, StubModel, context, services
    from uavlab.core.camera import Camera
    from uavlab.core.frame_store import global_store
    from uavlab.core.services import bind
    from uavlab.plugins.reasoning.onfly import OnFlyDecisionAgent

    ctx = context()
    depth = global_store().get(ctx.observation.depth.uri)
    global_store().put(ctx.observation.depth.uri, np.full_like(depth, 4.0))
    for v in (50, 170):
        policy = OnFlyDecisionAgent(model_id="stub", hold_initial_altitude=True, goal_standoff_m=1)
        bind(policy, services(StubModel(['{"u":112,"v":' + str(v) + "}"])))
        policy.reset(MISSION, 1061)
        result = asyncio.run(policy.decide(ctx))
        target = result.payload.target
        assert target.z == ctx.observation.position.z
        cam = Camera(pitch_rad=policy.camera_pitch_rad)
        p = ctx.observation.position
        _, d = cam.project(
            np.array([[target.x, target.y, target.z]]),
            np.array([p.x, p.y, p.z]),
            ctx.observation.yaw_rad,
        )
        assert d[0] <= float(result.provenance["executable_range_m"]) + 1e-6
