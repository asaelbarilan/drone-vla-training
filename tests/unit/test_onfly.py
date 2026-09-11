"""Paper-locked mechanism tests for the normalized OnFly profiles."""

from __future__ import annotations

import ast
import asyncio
import inspect
import math

import numpy as np
import pytest

from uavlab.contracts import (
    MemorySnapshot,
    MissionSpec,
    PerceptionState,
    ProgressLabel,
    TaskFamily,
    Vec3,
)
from uavlab.core.camera import Camera
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.orchestrator import _onfly_monitor_anchor, _onfly_recovery_heading
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult, RoutingFeedback
from uavlab.plugins.reasoning import onfly as onfly_module
from uavlab.plugins.reasoning.onfly import (
    OnFlyDecisionAgent,
    OnFlyHybridMemory,
    OnFlyMonitor,
    OnFlySemanticGeometricVerifier,
    OnFlySlidingMemory,
    _history_sheet,
    _latest_emphasis_sheet,
    _monitor_prompt,
    bearing_gated_range,
)

MISSION = MissionSpec(
    mission_id="onfly-test",
    instruction="fly to the red tower and stop there",
    task_family=TaskFamily.LONG_HORIZON_NAV,
)


class StubModel:
    name = "stub_onfly"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.requests = []

    async def invoke(self, request) -> InferenceResult:
        self.requests.append(request)
        reply = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        return InferenceResult(payload=reply, output_tokens=4, latency_ns=0)


def context(seed: int = 1060, memory: MemorySnapshot | None = None) -> DecisionContext:
    env = REGISTRY.build(
        "environment",
        "grid3d",
        {"render": True, "render_depth": True, "sensor_range_m": 60.0},
    )
    obs = asyncio.run(env.reset(MISSION, seed))
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=memory or MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="onfly-test",
    )


def services(model: StubModel) -> RuntimeServices:
    return RuntimeServices(
        clock=SimClock(),
        log=EventLog("onfly-test", None),
        feature_cache=FeatureCache(),
        inference=model,
        episode_id="onfly-test",
    )


def test_bearing_gate_reduces_edge_range_symmetrically() -> None:
    center = bearing_gated_range(
        7.0, 112, fx=112, cx=112, half_fov_rad=math.pi / 4, sigma_theta=0.65
    )
    left = bearing_gated_range(
        7.0, 1, fx=112, cx=112, half_fov_rad=math.pi / 4, sigma_theta=0.65
    )
    right = bearing_gated_range(
        7.0, 223, fx=112, cx=112, half_fov_rad=math.pi / 4, sigma_theta=0.65
    )
    assert center == pytest.approx(7.0)
    assert left == pytest.approx(right)
    assert left < center


def test_decision_agent_emits_typed_depth_waypoint_and_history_cue() -> None:
    model = StubModel(['{"u":112,"v":112}', '{"u":120,"v":112}'])
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    ctx = context()
    first = asyncio.run(policy.decide(ctx))
    second = asyncio.run(policy.decide(ctx))
    assert first.payload.target.distance_to(ctx.observation.position) <= 10.0
    assert first.provenance["pixel_u"] == "112"
    assert first.provenance["rgb_digest"] == ctx.observation.rgb.digest
    assert model.requests[0].response_schema is not None
    assert "previous 3d goal reprojects" in model.requests[1].prompt.lower()
    assert second.provenance["history_pixel"] != "None"


def test_decision_agent_uses_rejection_feedback_and_drops_bad_history_point() -> None:
    model = StubModel(['{"u":112,"v":112}', '{"u":40,"v":80}'])
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    ctx = context()
    first = asyncio.run(policy.decide(ctx))
    ctx.last_routing_feedback = RoutingFeedback(
        decision_id=first.decision_id,
        accepted=False,
        reason="planner reported infeasible: no known-free prefix",
        proposed_kind=first.kind,
        expanded_kind=None,
        t_sim_ns=ctx.t_sim_ns,
    )

    second = asyncio.run(policy.decide(ctx))

    prompt = model.requests[1].prompt.lower()
    assert "rejected the previous proposal" in prompt
    assert "(112, 112)" in prompt
    assert "do not repeat" in prompt
    assert second.provenance["history_pixel"] == "None"


def test_decision_agent_fails_closed_on_extra_or_bad_fields() -> None:
    model = StubModel(['{"u":112,"v":112,"land":false}'])
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    with pytest.raises(RuntimeError, match="invalid OnFly"):
        asyncio.run(policy.decide(context()))


def test_qwen_relative_coordinate_contract_scales_to_calibrated_pixels() -> None:
    model = StubModel(['{"u":999,"v":999}'])
    policy = OnFlyDecisionAgent(
        model_id="stub", coordinate_contract="qwen_relative_1000"
    )
    bind(policy, services(model))
    policy.reset(MISSION, 1060)

    decision = asyncio.run(policy.decide(context()))

    assert decision.provenance["model_u"] == "999"
    assert decision.provenance["model_v"] == "999"
    assert decision.provenance["pixel_u"] == "223"
    assert decision.provenance["pixel_v"] == "223"
    assert decision.provenance["coordinate_contract"] == "qwen_relative_1000"
    assert model.requests[0].response_schema["properties"]["u"]["maximum"] == 999
    assert "1000 by 1000 reference grid" in model.requests[0].prompt


def test_onfly_verifier_trusts_consistent_rgbd_goal_over_coarse_range_ray() -> None:
    model = StubModel(['{"u":112,"v":112}'])
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    ctx = context()
    decision = asyncio.run(policy.decide(ctx))
    endpoint_range = ctx.observation.position.distance_to(decision.payload.target)
    # Force every coarse fan ray to coincide with the endpoint. The generic
    # verifier rejects this, but OnFly's selected RGB-D pixel provides the
    # calibrated depth/bearing contract checked by its own verifier.
    ctx.observation = ctx.observation.model_copy(
        update={"range_rays": tuple(endpoint_range for _ in ctx.observation.range_rays)}
    )
    verifier = OnFlySemanticGeometricVerifier(
        max_waypoint_distance_m=7.0, min_clearance_m=1.2
    )
    verifier.reset(MISSION, 1060)

    result = verifier.verify(decision, ctx)

    assert result.accepted


def test_near_range_goal_preserves_its_camera_forward_bearing_gate() -> None:
    model = StubModel(['{"u":112,"v":112}'])
    policy = OnFlyDecisionAgent(
        model_id="stub", max_depth_m=0.25, goal_standoff_m=0.0
    )
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    ctx = context()

    decision = asyncio.run(policy.decide(ctx))
    gated_range = float(decision.provenance["gated_range_m"])
    intr = ctx.observation.intrinsics
    assert intr is not None
    camera = Camera(
        width=intr.width,
        height=intr.height,
        fov_deg=math.degrees(2 * math.atan(intr.width / (2 * intr.fx))),
        pitch_rad=-0.15,
    )
    endpoint = np.array(
        [[decision.payload.target.x, decision.payload.target.y, decision.payload.target.z]]
    )
    origin = np.array(
        [
            ctx.observation.position.x,
            ctx.observation.position.y,
            ctx.observation.position.z,
        ]
    )
    _, endpoint_depth = camera.project(endpoint, origin, ctx.observation.yaw_rad)

    assert endpoint_depth[0] == pytest.approx(gated_range, abs=1e-3)
    verifier = OnFlySemanticGeometricVerifier(max_waypoint_distance_m=10.0)
    verifier.reset(MISSION, 1060)
    assert verifier.verify(decision, ctx).accepted


def test_off_axis_slant_range_is_validated_as_camera_forward_depth() -> None:
    model = StubModel(['{"u":744,"v":426}'])
    policy = OnFlyDecisionAgent(
        model_id="stub", coordinate_contract="qwen_relative_1000"
    )
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    ctx = context()

    decision = asyncio.run(policy.decide(ctx))
    euclidean_range = ctx.observation.position.distance_to(decision.payload.target)
    gated_range = float(decision.provenance["gated_range_m"])
    assert euclidean_range > gated_range

    verifier = OnFlySemanticGeometricVerifier(max_waypoint_distance_m=7.0)
    verifier.reset(MISSION, 1060)
    assert verifier.verify(decision, ctx).accepted


def test_onfly_verifier_rejects_inconsistent_depth_provenance() -> None:
    model = StubModel(['{"u":112,"v":112}'])
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    ctx = context()
    decision = asyncio.run(policy.decide(ctx))
    invalid = decision.model_copy(
        update={
            "provenance": {
                **decision.provenance,
                "sampled_depth_m": "1.0",
                "gated_range_m": "2.0",
            }
        }
    )
    verifier = OnFlySemanticGeometricVerifier(max_waypoint_distance_m=7.0)
    verifier.reset(MISSION, 1060)

    result = verifier.verify(invalid, ctx)

    assert not result.accepted
    assert "exceeds" in result.reason


def test_onfly_verifier_checks_depth_from_source_pose_after_async_motion() -> None:
    model = StubModel(['{"u":700,"v":400}'])
    policy = OnFlyDecisionAgent(
        model_id="stub", coordinate_contract="qwen_relative_1000"
    )
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    source_ctx = context()
    decision = asyncio.run(policy.decide(source_ctx))

    verification_ctx = context()
    verification_ctx.observation = verification_ctx.observation.model_copy(
        update={
            "position": Vec3(x=2.0, y=-1.0, z=3.5),
            "yaw_rad": 0.4,
        }
    )
    verifier = OnFlySemanticGeometricVerifier(max_waypoint_distance_m=10.0)
    verifier.reset(MISSION, 1060)

    result = verifier.verify(decision, verification_ctx)

    assert result.accepted


def test_visual_memories_are_bounded_and_hybrid_keeps_initial_latest() -> None:
    ctx = context()
    for memory in (OnFlySlidingMemory(keyframe_budget=4), OnFlyHybridMemory(keyframe_budget=4)):
        memory.reset(MISSION, 1060)
        memory.update(ctx.observation, ctx.perception, None)
        snapshot = memory.snapshot()
        assert snapshot.items
        assert all(item.image_uri for item in snapshot.items)
        assert len(snapshot.items) <= 6
    hybrid = OnFlyHybridMemory(keyframe_budget=4)
    hybrid.reset(MISSION, 1060)
    for index in range(4):
        moved = ctx.observation.model_copy(
            update={
                "seq": index + 1,
                "position": Vec3(x=float(index * 4), y=0.0, z=3.0),
            }
        )
        hybrid.update(moved, ctx.perception, None)
    snapshot = hybrid.snapshot()
    assert snapshot.items[0].kind == "initial"
    assert snapshot.items[-1].kind == "latest"
    assert len(snapshot.items) > 2


def test_hybrid_memory_keeps_sticky_winners_and_prefix_until_segment_changes() -> None:
    ctx = context()
    hybrid = OnFlyHybridMemory(
        keyframe_budget=2,
        translation_threshold_m=1.0,
        dedupe_distance_m=0.0,
    )
    hybrid.reset(MISSION, 1060)

    def add(seq: int, distance: float) -> None:
        observation = ctx.observation.model_copy(
            update={
                "seq": seq,
                "t_sim_ns": seq * 1_000_000_000,
                "position": Vec3(x=distance, y=0.0, z=3.0),
            }
        )
        hybrid.update(observation, ctx.perception, None)

    for seq, distance in enumerate((0.0, 4.0, 8.0, 12.0), start=1):
        add(seq, distance)
    first = hybrid.snapshot()
    assert [item.observation_seq for item in first.items if item.kind == "keyframe"] == [2, 3]

    # At total distance 14, frames 4 m and 8 m remain in their old segments.
    # A stateless center selector would replace 8 m with the newer 12 m frame;
    # the paper's sticky rule must not.
    add(5, 14.0)
    sticky = hybrid.snapshot()
    assert [item.observation_seq for item in sticky.items if item.kind == "keyframe"] == [2, 3]
    assert sticky.stats["prefix_reused"] == 2.0

    # Once total distance moves the old second winner out of its segment, only
    # that invalid suffix is replaced and the valid first slot stays intact.
    add(6, 24.0)
    shifted = hybrid.snapshot()
    assert [item.observation_seq for item in shifted.items if item.kind == "keyframe"] == [2, 5]
    assert shifted.stats["prefix_reused"] == 1.0


def test_monitor_is_forced_choice_and_requires_stable_stop() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()
    model = StubModel(['{"status":"STOP"}', '{"status":"STOP"}'])
    monitor = OnFlyMonitor(model_id="stub", stop_confirmations=2)
    bind(monitor, services(model))
    monitor.reset(MISSION, 1060)
    assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.CONTINUE
    assert asyncio.run(monitor.assess(ctx)).label is ProgressLabel.STOP
    assert model.requests[0].image_count >= 1
    assert model.requests[0].response_schema is not None


def test_monitor_contract_defines_post_acquisition_loss_without_truth() -> None:
    prompt = _monitor_prompt(MISSION.instruction)
    assert "destination appeared in earlier route images but disappeared" in prompt
    assert "Do not assume an invisible destination remains ahead" in prompt
    assert "small or distant target" in prompt
    assert "LATEST image only" in prompt
    assert "absent from the latest image, STOP is forbidden" in prompt
    assert "stop and reorient" in prompt
    assert "matches every explicitly named visual attribute" in prompt
    assert "distractor" in prompt


def test_latest_emphasis_sheet_keeps_history_and_labels_latest() -> None:
    ctx = context()
    from uavlab.core.frame_store import global_store

    image = global_store().get(ctx.observation.rgb.uri)
    sheet = _latest_emphasis_sheet([image, image, image])
    assert sheet.size == (672, 472)
    # Latest panel preserves real sensor pixels rather than synthesizing state.
    assert sheet.getpixel((400, 240)) != (0, 0, 0)


def test_history_sheet_keeps_latest_as_separate_model_image() -> None:
    ctx = context()
    from uavlab.core.frame_store import global_store

    image = global_store().get(ctx.observation.rgb.uri)
    sheet = _history_sheet([image, image])
    assert sheet.size == (672, 248)

    memory = OnFlyHybridMemory(
        keyframe_budget=4,
        translation_threshold_m=0.0,
        rotation_threshold_rad=0.0,
    )
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    shifted = ctx.observation.model_copy(
        update={
            "seq": ctx.observation.seq + 1,
            "t_sim_ns": ctx.observation.t_sim_ns + 1,
            "position": Vec3(x=1.0, y=0.0, z=ctx.observation.position.z),
        }
    )
    memory.update(shifted, ctx.perception, None)
    ctx.memory = memory.snapshot()
    model = StubModel(
        [
            '{"earlier_target_visible":false,"latest_target_visible":false,'
            '"latest_target_scale":"absent","status":"CONTINUE"}'
        ]
    )
    monitor = OnFlyMonitor(
        model_id="stub",
        layout="history_sheet_plus_latest",
        structured_evidence=True,
    )
    bind(monitor, services(model))
    monitor.reset(MISSION, 1060)

    asyncio.run(monitor.assess(ctx))

    assert model.requests[0].image_count == 2
    assert "second image" in model.requests[0].prompt


def test_structured_monitor_vetoes_distant_stop_with_depth_camera() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()

    decision_model = StubModel(['{"u":112,"v":112}'])
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(decision_model))
    policy.reset(MISSION, 1060)
    ctx.last_decision = asyncio.run(policy.decide(ctx))

    monitor_model = StubModel(
        [
            '{"earlier_target_visible":true,"latest_target_visible":true,'
            '"latest_target_scale":"large","status":"STOP"}'
        ]
    )
    monitor = OnFlyMonitor(
        model_id="stub", structured_evidence=True, stop_max_depth_m=3.0
    )
    bind(monitor, services(monitor_model))
    monitor.reset(MISSION, 1060)

    progress = asyncio.run(monitor.assess(ctx))

    assert progress.label is ProgressLabel.CONTINUE
    assert "depth" in progress.evidence
    assert progress.recovery_anchor_valid
    assert not progress.recovery_reacquired


def test_monitor_accepts_current_visibility_when_previous_goal_left_the_frame() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()

    decision_model = StubModel(['{"u":112,"v":112}', '{"u":112,"v":112}'])
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(decision_model))
    policy.reset(MISSION, 1060)
    asyncio.run(policy.decide(ctx))
    ctx.last_decision = asyncio.run(policy.decide(ctx))
    assert ctx.last_decision.provenance["history_pixel"] != "None"

    monitor_model = StubModel(
        [
            '{"earlier_target_visible":true,"latest_target_visible":true,'
            '"latest_target_scale":"large","status":"STOP"}',
            '{"earlier_target_visible":true,"latest_target_visible":true,'
            '"latest_target_scale":"large","status":"STOP"}',
        ]
    )
    monitor = OnFlyMonitor(
        model_id="stub", structured_evidence=True, stop_max_depth_m=3.0
    )
    bind(monitor, services(monitor_model))
    monitor.reset(MISSION, 1060)

    tracked = asyncio.run(monitor.assess(ctx))
    assert tracked.label is ProgressLabel.CONTINUE
    assert tracked.recovery_anchor_valid

    ctx.last_decision = ctx.last_decision.model_copy(
        update={
            "provenance": {
                **ctx.last_decision.provenance,
                "history_pixel": "None",
            }
        }
    )
    reacquired = asyncio.run(monitor.assess(ctx))

    assert reacquired.label is ProgressLabel.CONTINUE
    assert "history_continuous=False" in reacquired.evidence
    assert reacquired.recovery_anchor_valid
    assert reacquired.recovery_reacquired


def test_structured_monitor_normalizes_postacquisition_absent_continue_to_lost() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()
    model = StubModel(
        [
            '{"earlier_target_visible":false,"latest_target_visible":true,'
            '"latest_target_scale":"small","status":"CONTINUE"}',
            '{"earlier_target_visible":true,"latest_target_visible":true,'
            '"latest_target_scale":"small","status":"CONTINUE"}',
            '{"earlier_target_visible":true,"latest_target_visible":false,'
            '"latest_target_scale":"absent","status":"CONTINUE"}',
        ]
    )
    monitor = OnFlyMonitor(model_id="stub", structured_evidence=True)
    bind(monitor, services(model))
    monitor.reset(MISSION, 1060)

    asyncio.run(monitor.assess(ctx))
    acquired = asyncio.run(monitor.assess(ctx))
    lost = asyncio.run(monitor.assess(ctx))

    assert acquired.recovery_anchor_valid
    assert lost.label is ProgressLabel.LOST
    assert "post-acquisition CONTINUE" in lost.evidence
    assert not lost.recovery_anchor_valid


def test_structured_monitor_normalizes_inconsistent_absent_stop_to_lost() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()
    model = StubModel(
        [
            '{"earlier_target_visible":false,"latest_target_visible":true,'
            '"latest_target_scale":"small","status":"CONTINUE"}',
            '{"earlier_target_visible":true,"latest_target_visible":true,'
            '"latest_target_scale":"small","status":"CONTINUE"}',
            '{"earlier_target_visible":true,"latest_target_visible":false,'
            '"latest_target_scale":"absent","status":"STOP"}'
        ]
    )
    monitor = OnFlyMonitor(model_id="stub", structured_evidence=True)
    bind(monitor, services(model))
    monitor.reset(MISSION, 1060)

    asyncio.run(monitor.assess(ctx))
    asyncio.run(monitor.assess(ctx))
    progress = asyncio.run(monitor.assess(ctx))

    assert progress.label is ProgressLabel.LOST
    assert "contradicted" in progress.evidence


def test_structured_monitor_normalizes_preacquisition_lost_to_continue() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()
    model = StubModel(
        [
            '{"earlier_target_visible":false,"latest_target_visible":false,'
            '"latest_target_scale":"absent","status":"LOST"}'
        ]
    )
    monitor = OnFlyMonitor(model_id="stub", structured_evidence=True)
    bind(monitor, services(model))
    monitor.reset(MISSION, 1060)

    progress = asyncio.run(monitor.assess(ctx))

    assert progress.label is ProgressLabel.CONTINUE
    assert "pre-acquisition" in progress.evidence
    assert progress.recovery_anchor_valid
    assert not progress.recovery_reacquired


def test_structured_monitor_retains_acquisition_across_independent_requests() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()
    model = StubModel(
        [
            '{"earlier_target_visible":false,"latest_target_visible":true,'
            '"latest_target_scale":"small","status":"CONTINUE"}',
            '{"earlier_target_visible":true,"latest_target_visible":true,'
            '"latest_target_scale":"small","status":"CONTINUE"}',
            '{"earlier_target_visible":false,"latest_target_visible":false,'
            '"latest_target_scale":"absent","status":"LOST"}',
        ]
    )
    monitor = OnFlyMonitor(model_id="stub", structured_evidence=True)
    bind(monitor, services(model))
    monitor.reset(MISSION, 1060)

    asyncio.run(monitor.assess(ctx))
    acquired = asyncio.run(monitor.assess(ctx))
    later_loss = asyncio.run(monitor.assess(ctx))

    assert acquired.label is ProgressLabel.CONTINUE
    assert later_loss.label is ProgressLabel.LOST
    assert "ever_acquired=True" in later_loss.evidence


def test_structured_monitor_does_not_acquire_from_history_only() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()
    model = StubModel(
        [
            '{"earlier_target_visible":true,"latest_target_visible":false,'
            '"latest_target_scale":"absent","status":"LOST"}',
            '{"earlier_target_visible":false,"latest_target_visible":true,'
            '"latest_target_scale":"small","status":"CONTINUE"}',
            '{"earlier_target_visible":true,"latest_target_visible":false,'
            '"latest_target_scale":"absent","status":"LOST"}',
        ]
    )
    monitor = OnFlyMonitor(model_id="stub", structured_evidence=True)
    bind(monitor, services(model))
    monitor.reset(MISSION, 1060)

    history_only = asyncio.run(monitor.assess(ctx))
    isolated_latest = asyncio.run(monitor.assess(ctx))
    absent_again = asyncio.run(monitor.assess(ctx))

    assert history_only.label is ProgressLabel.CONTINUE
    assert isolated_latest.label is ProgressLabel.CONTINUE
    assert absent_again.label is ProgressLabel.CONTINUE
    assert "ever_acquired=False" in absent_again.evidence
    assert "acquisition_count=0/2" in absent_again.evidence


def test_lost_recovery_restores_last_normal_heading_not_bearing_to_position() -> None:
    assert _onfly_recovery_heading(1.25, -2.0) == pytest.approx(1.25)
    # Before any normal state exists, the bounded fallback faces backwards.
    fallback = _onfly_recovery_heading(None, 0.4)
    wrapped_error = math.atan2(
        math.sin(fallback - (0.4 + math.pi)),
        math.cos(fallback - (0.4 + math.pi)),
    )
    assert wrapped_error == pytest.approx(0.0)


def test_monitor_anchor_uses_pose_of_latest_retained_frame() -> None:
    ctx = context()
    memory = OnFlyHybridMemory(keyframe_budget=4)
    memory.reset(MISSION, 1060)
    memory.update(ctx.observation, ctx.perception, None)
    ctx.memory = memory.snapshot()
    retained_yaw = ctx.observation.yaw_rad
    retained_seq = ctx.observation.seq
    ctx.observation = ctx.observation.model_copy(
        update={"yaw_rad": retained_yaw + 1.0, "seq": retained_seq + 10}
    )

    _, anchor_yaw, anchor_seq = _onfly_monitor_anchor(ctx)

    assert anchor_yaw == pytest.approx(retained_yaw)
    assert anchor_seq == retained_seq


def test_onfly_source_does_not_read_truth_or_sensor_side_semantics() -> None:
    tree = ast.parse(inspect.getsource(onfly_module))
    accessed = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "privileged" not in accessed
    assert "semantic_hits" not in accessed


def test_profiles_map_to_c3_c4_c5_and_only_memory_changes_c4_to_c5(arch_factory) -> None:
    c3 = arch_factory("c3_onfly_gemma")
    c4 = arch_factory("c4_onfly_gemma")
    c5 = arch_factory("c5_onfly_gemma")
    assert (c3.profile_of, c4.profile_of, c5.profile_of) == ("c3", "c4", "c5")
    assert c3.monitor is None
    assert c4.monitor == c5.monitor
    assert c4.policy == c5.policy
    assert c4.verifier == c5.verifier
    assert c4.planner == c5.planner
    assert c4.scheduler == c5.scheduler
    assert c4.memory.name == "onfly_sliding_memory"
    assert c5.memory.name == "onfly_hybrid_memory"


def test_qwen_profiles_preserve_the_same_c3_c4_c5_mechanism_contrasts(arch_factory) -> None:
    c3 = arch_factory("c3_onfly_qwen")
    c4 = arch_factory("c4_onfly_qwen")
    c5 = arch_factory("c5_onfly_qwen")
    assert (c3.profile_of, c4.profile_of, c5.profile_of) == ("c3", "c4", "c5")
    assert c3.monitor is None
    assert c4.monitor == c5.monitor
    assert c4.policy == c5.policy
    assert c4.verifier == c5.verifier
    assert c4.planner == c5.planner
    assert c4.scheduler == c5.scheduler
    assert c4.policy.params["coordinate_contract"] == "qwen_relative_1000"
    assert c4.memory.name == "onfly_sliding_memory"
    assert c5.memory.name == "onfly_hybrid_memory"


def test_shared_comparison_uses_full_onfly_without_mutating_c3_ablation(arch_factory) -> None:
    c3 = arch_factory("c3_onfly_qwen4_shared")
    representative = arch_factory("c5_onfly_qwen4_shared")

    assert c3.monitor is None
    assert c3.semantic_supervision.value == "none"
    assert representative.profile_of == "c5"
    assert representative.monitor is not None
    assert representative.monitor.name == "onfly_monitor"
    assert representative.memory.name == "onfly_hybrid_memory"
    assert representative.semantic_supervision.value == "periodic_monitor"
    assert representative.policy.params["model_id"] == "qwen3-vl:4b"
    assert representative.monitor.params["model_id"] == "qwen3-vl:4b"


def test_model_named_step_curve_is_the_spf_adaptive_form() -> None:
    policy = OnFlyDecisionAgent(
        model_id="stub",
        step_from_model=True,
        step_levels=5,
        step_scale_m=9.0,
        step_exponent=1.0,
        step_min_m=1.0,
    )
    assert policy._model_step_m(5) == pytest.approx(9.0)
    assert policy._model_step_m(3) == pytest.approx(5.4)
    assert policy._model_step_m(1) == pytest.approx(1.8)
    floored = OnFlyDecisionAgent(
        model_id="stub", step_from_model=True, step_levels=5, step_scale_m=2.0, step_min_m=1.5
    )
    assert floored._model_step_m(1) == pytest.approx(1.5)
    with pytest.raises(ValueError):
        policy._model_step_m(6)


def test_schema_carries_the_step_level_only_when_enabled() -> None:
    off = OnFlyDecisionAgent(model_id="stub")
    assert "d" not in off._schema(224, 224)["properties"]
    on = OnFlyDecisionAgent(model_id="stub", step_from_model=True, step_levels=5)
    schema = on._schema(224, 224)
    assert schema["properties"]["d"] == {"type": "integer", "minimum": 1, "maximum": 5}
    assert "d" in schema["required"]


def test_model_named_step_replaces_the_depth_derived_ceiling() -> None:
    """The whole ablation: the hop is set by ``d``, never by sensed depth.

    C5's own step obeys ``range <= sensed_depth(u, v)``, so it cannot cross the
    first surface on the ray. Here the same pixel yields two different ranges
    purely because the model named a different level.
    """
    ranges = []
    for reply in ('{"u":112,"v":112,"d":1}', '{"u":112,"v":112,"d":5}'):
        model = StubModel([reply])
        policy = OnFlyDecisionAgent(
            model_id="stub",
            step_from_model=True,
            step_levels=5,
            step_scale_m=9.0,
            step_min_m=1.0,
        )
        bind(policy, services(model))
        policy.reset(MISSION, 1060)
        envelope = asyncio.run(policy.decide(context()))
        assert envelope.provenance["step_source"] == "model"
        ranges.append(float(envelope.provenance["executable_range_m"]))
    assert ranges == [pytest.approx(1.8), pytest.approx(9.0)]


def test_depth_step_remains_the_default_and_is_recorded_as_such() -> None:
    model = StubModel(['{"u":112,"v":112}'])
    policy = OnFlyDecisionAgent(model_id="stub")
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    envelope = asyncio.run(policy.decide(context()))
    assert envelope.provenance["step_source"] == "depth"
    assert envelope.provenance["model_step_level"] == "0"


def test_model_named_step_fails_closed_without_a_level() -> None:
    model = StubModel(['{"u":112,"v":112}'])
    policy = OnFlyDecisionAgent(model_id="stub", step_from_model=True)
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    with pytest.raises(RuntimeError):
        asyncio.run(policy.decide(context()))


def test_route_hint_reaches_the_prompt_with_live_odometry() -> None:
    """Guard for the privileged route-hint diagnostic.

    If the hint silently failed to reach the model the probe would look like a
    capability result while actually measuring nothing, so this asserts the text
    is present and that the odometry anchoring it is real rather than constant.
    """
    model = StubModel(['{"u":112,"v":112}'])
    route = "after 0 m of path, turn left 47 degrees and fly 12.6 m."
    policy = OnFlyDecisionAgent(model_id="stub", route_hint=route)
    bind(policy, services(model))
    policy.reset(MISSION, 1060)
    ctx = context()
    asyncio.run(policy.decide(ctx))
    prompt = model.requests[0].prompt
    assert route in prompt
    assert "Onboard odometry says you have flown" in prompt
    assert "0 m of path" in prompt

    plain = StubModel(['{"u":112,"v":112}'])
    bare = OnFlyDecisionAgent(model_id="stub")
    bind(bare, services(plain))
    bare.reset(MISSION, 1060)
    asyncio.run(bare.decide(context()))
    assert "Onboard odometry" not in plain.requests[0].prompt


def test_route_flown_survives_the_truncated_position_window() -> None:
    """Path length must not reset when the 12-sample prompt window rolls over."""
    policy = OnFlyDecisionAgent(model_id="stub", route_hint="x")
    policy.reset(MISSION, 1060)
    for i in range(30):
        policy._route_positions.append(Vec3(x=float(i), y=0.0, z=0.0))
        if i:
            policy._route_flown_m += 1.0
        policy._route_positions = policy._route_positions[-12:]
    assert len(policy._route_positions) == 12
    assert policy._route_flown_m == pytest.approx(29.0)


@pytest.mark.parametrize("enabled", [True, False])
def test_previous_goal_prompt_can_be_ablated_without_losing_geometry(enabled):
    model = StubModel(['{"u":112,"v":112}'])
    agent = OnFlyDecisionAgent(previous_goal_prompt=enabled)
    agent.reset(MISSION, 1060)
    bind(agent, services(model))
    ctx = context()
    asyncio.run(agent.decide(ctx))
    decision = asyncio.run(agent.decide(ctx))
    prompt = model.requests[-1].prompt
    assert ("previous 3D goal reprojects" in prompt) is enabled
    assert ("Choose a fresh navigation point" in prompt) is not enabled
    assert decision.provenance["history_pixel"] != "None"
