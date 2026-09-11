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


def test_current_grounding_absence_cannot_use_coordinates_to_stop():
    ctx, monitor, model = setup_monitor()
    monitor.current_grounding = True
    model.replies = [json.dumps(dict(evidence="gray obstacle", visible=False, u=500, v=500))]
    for _ in range(3):
        result = asyncio.run(monitor.assess(ctx))
        assert result.label is ProgressLabel.CONTINUE
        fresh(ctx)
    assert not monitor._ever_acquired
    assert "gray obstacle" in result.evidence
    assert monitor.parse_errors == 0
    assert all(request.image_count == 1 for request in model.requests)


@pytest.mark.parametrize(
    "depth,expected", [(1.0, ProgressLabel.STOP), (20.0, ProgressLabel.CONTINUE)]
)
def test_current_grounding_keeps_metric_arrival_gate(depth, expected):
    ctx, monitor, model = setup_monitor(depth_m=depth)
    monitor.current_grounding = True
    model.replies = [json.dumps(dict(evidence="target visible", visible=True, u=500, v=500))]
    asyncio.run(monitor.assess(ctx))
    fresh(ctx)
    assert asyncio.run(monitor.assess(ctx)).label is expected
    assert monitor.parse_errors == 0


@pytest.mark.parametrize("kind", ["target", "exploration"])
def test_grounded_waypoint_labels_only_model_identified_targets(kind):
    ctx = context()
    model = StubModel([json.dumps(dict(evidence="a structure", kind=kind, u=112, v=112))])
    agent = OnFlyDecisionAgent(model_id="stub", grounded_waypoints=True, previous_goal_prompt=False)
    bind(agent, services(model))
    agent.reset(MISSION, 1060)
    decision = asyncio.run(agent.decide(ctx))
    assert (decision.payload.target_label is not None) == (kind == "target")
    assert decision.provenance["waypoint_kind"] == kind
    assert "previous-goal" not in model.requests[0].prompt


@pytest.mark.parametrize(
    "color,expected",
    [
        ("gray", ProgressLabel.CONTINUE),
        ("unknown", ProgressLabel.CONTINUE),
        ("red", ProgressLabel.STOP),
    ],
)
def test_attribute_guard_checks_model_color_before_arrival(color, expected):
    ctx, monitor, model = setup_monitor()
    monitor.current_grounding = monitor.semantic_color_guard = True
    monitor.reset(MISSION, 1060)
    model.replies = [
        json.dumps(dict(evidence="a building", visible=True, u=500, v=500, observed_color=color))
    ]
    asyncio.run(monitor.assess(ctx))
    fresh(ctx)
    result = asyncio.run(monitor.assess(ctx))
    assert result.label is expected
    assert monitor.parse_errors == 0
    assert "color_guard=" in result.evidence


def test_mismatched_policy_object_uses_model_exploration_alternative():
    ctx = context()
    model = StubModel(
        [
            json.dumps(
                dict(
                    evidence="gray tower",
                    kind="target",
                    observed_color="gray",
                    u=112,
                    v=112,
                    explore_u=160,
                    explore_v=100,
                )
            )
        ]
    )
    agent = OnFlyDecisionAgent(model_id="stub", grounded_waypoints=True, semantic_color_guard=True)
    bind(agent, services(model))
    agent.reset(MISSION, 1060)
    decision = asyncio.run(agent.decide(ctx))
    assert decision.payload.target_label is None
    assert decision.provenance["raw_waypoint_kind"] == "target"
    assert decision.provenance["waypoint_kind"] == "exploration"
    assert decision.provenance["pixel_u"] == "160"


@pytest.mark.parametrize(
    "instruction",
    ["fly to the tower", "fly to red or green tower", "fly to the tower that is not red"],
)
def test_ambiguous_color_contract_is_not_guessed(instruction):
    from uavlab.plugins.reasoning.onfly import _mission_color

    with pytest.raises(ValueError, match="unambiguous"):
        _mission_color(instruction)


def test_color_contract_is_not_hardcoded_to_red():
    from uavlab.plugins.reasoning.onfly import _mission_color

    assert _mission_color("fly to the blue tower") == "blue"
    assert _mission_color("fly to the grey tower") == "gray"
