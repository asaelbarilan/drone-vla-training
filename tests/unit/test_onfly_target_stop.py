"""Target-associated arrival regression: nearby navigation pixels cannot authorize STOP."""

import asyncio
import json

import numpy as np
import pytest

from tests.unit.test_onfly import MISSION, StubModel, context, services
from uavlab.contracts import ProgressLabel, Vec3
from uavlab.core.frame_store import global_store
from uavlab.core.services import bind
from uavlab.plugins.reasoning.onfly import OnFlyDecisionAgent, OnFlyHybridMemory, OnFlyMonitor


def setup_monitor(depth_m=1.0, **reply_changes):
    ctx = context()
    intr = ctx.observation.intrinsics
    depth = np.full((intr.height, intr.width), depth_m)
    global_store().put(ctx.observation.depth.uri, depth)
    reply = dict(
        earlier_target_visible=True,
        latest_target_visible=True,
        latest_target_scale="large",
        status="STOP",
        target_u=500,
        target_v=500,
    )
    reply.update(reply_changes)
    model = StubModel([json.dumps(reply)])
    monitor = OnFlyMonitor(model_id="stub", structured_evidence=True, target_bound_stop=True)
    bind(monitor, services(model))
    monitor.reset(MISSION, 1060)
    return ctx, monitor, model


def fresh(ctx, **updates):
    ctx.observation = ctx.observation.model_copy(
        update={
            "seq": ctx.observation.seq + 1,
            "t_sim_ns": ctx.observation.t_sim_ns + 2_000_000_000,
            **updates,
        }
    )


def test_near_target_stops_only_after_distinct_consistent_frames():
    ctx, monitor, _ = setup_monitor()
    assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE
    fresh(ctx)
    result = asyncio.run(monitor.assess(ctx))
    assert result.label is ProgressLabel.STOP
    assert "target_consistent=True" in result.evidence


def test_repeated_frame_cannot_confirm_arrival():
    ctx, monitor, _ = setup_monitor()
    assert all(asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE for _ in range(4))


def test_near_navigation_pixel_does_not_authorize_distant_target_stop():
    ctx, monitor, _ = setup_monitor(depth_m=20.0, target_u=800, target_v=500)
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(StubModel(['{"u":112,"v":112}'])))
    policy.reset(MISSION, 1060)
    depth = global_store().get(ctx.observation.depth.uri)
    depth[105:120, 105:120] = 1.0
    ctx.last_decision = asyncio.run(policy.decide(ctx))
    assert float(ctx.last_decision.provenance["sampled_depth_m"]) == 1.0
    for _ in range(3):
        assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE
        fresh(ctx)
    assert monitor._ever_acquired  # distant acquisition is legitimate, arrival is not


@pytest.mark.parametrize("depth", [float("nan"), float("inf"), 0.0, -1.0, 2.5, 50.0])
def test_invalid_or_far_target_range_never_stops(depth):
    ctx, monitor, _ = setup_monitor(depth)
    for _ in range(3):
        assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE
        fresh(ctx)


@pytest.mark.parametrize(
    "changes",
    [
        dict(target_u=None, target_v=None),
        dict(target_u=True),
        dict(target_v=1000),
        dict(latest_target_visible="false"),
    ],
)
def test_missing_or_malformed_target_evidence_fails_closed(changes):
    ctx, monitor, _ = setup_monitor(**changes)
    for _ in range(3):
        assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE
        fresh(ctx)


def test_jumping_world_target_resets_confirmation():
    ctx, monitor, _ = setup_monitor()
    asyncio.run(monitor.assess(ctx))
    fresh(ctx, position=Vec3(x=20, y=0, z=3))
    assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE
    fresh(ctx)
    assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.STOP


def test_missing_current_rgb_does_not_use_history_as_current():
    ctx, monitor, _ = setup_monitor()
    memory = OnFlyHybridMemory()
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()
    ctx.observation = ctx.observation.model_copy(update={"rgb": None})
    assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE


def test_depth_snapshot_survives_inference_eviction():
    ctx, monitor, model = setup_monitor()
    original = model.invoke

    async def evict(request):
        global_store().get(ctx.observation.depth.uri)[:] = 0
        return await original(request)

    model.invoke = evict
    result = asyncio.run(monitor.assess(ctx))
    assert "target_bound_range_m=1." in result.evidence
