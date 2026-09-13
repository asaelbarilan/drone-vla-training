from __future__ import annotations

import asyncio
import math

import pytest

from uavlab.contracts import (
    DecisionKind,
    Detection,
    MemorySnapshot,
    MissionConstraints,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    SkillCall,
    TaskFamily,
    Vec3,
)
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.services import RuntimeServices, bind
from uavlab.core.skills import InvalidSkillArguments, SkillRuntime
from uavlab.interfaces import (
    DecisionContext,
    InferenceResult,
    RoutingFeedback,
    SemanticCompletionEvidence,
)
from uavlab.plugins.inference.simulated import SimulatedInference
from uavlab.plugins.reasoning.aerialclaw import (
    AerialClawAgentPolicy,
    AerialClawOutputError,
    AerialClawUnavailable,
)

MISSION = MissionSpec(
    mission_id="aerialclaw",
    instruction="find the target and stop above it",
    task_family=TaskFamily.OBJECT_SEARCH,
    allowed_skills=("goto", "move", "approach", "hover", "scan", "stop"),
    constraints=MissionConstraints(
        geofence_radius_m=60.0,
        min_altitude_m=0.5,
        max_altitude_m=25.0,
        max_speed_mps=5.0,
    ),
)


class StubAgentModel:
    name = "stub_real_model"
    model_id = "qwen3.5:2b"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.requests = []

    async def invoke(self, request) -> InferenceResult:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.replies) - 1)
        return InferenceResult(payload=self.replies[index], output_tokens=20, latency_ns=0)


def context(
    *, feedback: RoutingFeedback | None = None, position: Vec3 | None = None
) -> DecisionContext:
    obs = ObservationPacket(
        seq=3,
        t_sim_ns=2_000_000_000,
        t_wall_ns=3,
        position=position or Vec3(x=1.0, y=2.0, z=3.0),
        velocity=Vec3(x=0.0, y=0.0, z=0.0),
        yaw_rad=0.1,
        battery_frac=0.9,
    )
    perception = PerceptionState(
        observation_seq=obs.seq,
        t_sim_ns=obs.t_sim_ns,
        detections=(
            Detection(
                label="target",
                score=0.8,
                position=Vec3(x=8.0, y=4.0, z=3.0),
            ),
            Detection(
                label="distractor_0",
                score=0.95,
                position=Vec3(x=4.0, y=-2.0, z=3.0),
            ),
        ),
    )
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=perception,
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="ac-test",
        last_routing_feedback=feedback,
    )


def policy_with(replies: list[str]) -> tuple[AerialClawAgentPolicy, StubAgentModel]:
    model = StubAgentModel(replies)
    policy = AerialClawAgentPolicy(model_id=model.model_id)
    services = RuntimeServices(
        clock=SimClock(),
        log=EventLog("ac-test", None),
        feature_cache=FeatureCache(),
        inference=model,
        episode_id="ac-test",
    )
    bind(policy, services)
    policy.reset(MISSION, 1020)
    return policy, model


def reply(skill: str = "goto") -> str:
    return (
        '{"thinking":"target visible","decision":"act","action":{"skill":"'
        + skill
        + '","args":{"x":8.0,"y":4.0,"z":3.0,"label":"target"}},'
        '"reflection":null,"goal_progress":"approaching target","confidence":0.8}'
    )


def stuck_reply() -> str:
    return (
        '{"thinking":"search failed","decision":"stuck","action":null,'
        '"reflection":"no result","goal_progress":"no target","confidence":0.6}'
    )


def scan_reply() -> str:
    return (
        '{"thinking":"scan","decision":"act","action":{"skill":"scan",'
        '"args":{"yaw_rate_rps":1.5,"duration_s":3.0}},"reflection":null,'
        '"goal_progress":"scanning","confidence":0.7}'
    )


def done_reply() -> str:
    return (
        '{"thinking":"done","decision":"done","action":null,"reflection":null,'
        '"goal_progress":"complete","confidence":0.9}'
    )


def test_real_model_decision_becomes_one_typed_skill_call() -> None:
    policy, model = policy_with([reply()])
    envelope = asyncio.run(policy.decide(context()))
    assert envelope is not None
    assert envelope.kind is DecisionKind.SKILL
    assert isinstance(envelope.payload, SkillCall)
    assert envelope.payload.skill_name == "goto"
    assert model.requests[0].response_schema is not None
    assert "# SOUL.md" in model.requests[0].prompt
    assert "# Search for a semantic target" in model.requests[0].prompt
    assert "BODY.md" in model.requests[0].prompt
    assert "Current exact-label target candidates" in model.requests[0].prompt
    assert "Current non-target detections" in model.requests[0].prompt
    assert "distractor_0" in model.requests[0].prompt
    assert "approach_exact_label_target" in model.requests[0].prompt
    assert "decision: act" in model.requests[0].prompt
    assert "irreversible terminal mission failure" in model.requests[0].prompt
    assert "privileged" not in model.requests[0].prompt.lower()


def test_accepted_goto_is_locally_replanned_without_a_new_llm_decision() -> None:
    policy, model = policy_with([reply(), reply()])
    first = asyncio.run(policy.decide(context()))
    assert first is not None
    accepted = RoutingFeedback(
        decision_id=first.decision_id,
        accepted=True,
        reason="waypoint planned",
        proposed_kind=DecisionKind.SKILL,
        expanded_kind=DecisionKind.WAYPOINT,
        t_sim_ns=2_000_000_000,
    )

    continuation = asyncio.run(policy.decide(context(feedback=accepted)))
    assert continuation is not None
    assert continuation.producer.endswith(":skill_executor")
    assert isinstance(continuation.payload, SkillCall)
    assert continuation.payload == first.payload
    assert len(model.requests) == 1

    completed_feedback = RoutingFeedback(
        decision_id=continuation.decision_id,
        accepted=True,
        reason="waypoint planned",
        proposed_kind=DecisionKind.SKILL,
        expanded_kind=DecisionKind.WAYPOINT,
        t_sim_ns=3_000_000_000,
    )
    completed_ctx = context(
        feedback=completed_feedback,
        position=Vec3(x=8.0, y=4.0, z=3.0),
    )
    fresh = asyncio.run(policy.decide(completed_ctx))
    assert fresh is not None
    assert fresh.producer == "aerialclaw_agent"
    assert len(model.requests) == 2
    completion = completed_ctx.scratch.get("semantic_completion_evidence")
    assert isinstance(completion, SemanticCompletionEvidence)
    assert completion.label == "target"
    SkillRuntime(MISSION.allowed_skills).expand(
        SkillCall(skill_name="stop", args={"reason": "completed skill"}),
        completed_ctx,
    )


def test_runtime_feedback_and_reflection_reach_the_next_agent_cycle() -> None:
    policy, model = policy_with([reply(), reply("goto"), scan_reply()])
    first = asyncio.run(policy.decide(context()))
    feedback = RoutingFeedback(
        decision_id=first.decision_id,
        accepted=False,
        reason="invalid skill arguments: altitude outside envelope",
        proposed_kind=DecisionKind.SKILL,
        expanded_kind=None,
        t_sim_ns=3_000_000_000,
    )
    corrected = asyncio.run(policy.decide(context(feedback=feedback)))
    assert corrected is not None
    assert isinstance(corrected.payload, SkillCall)
    assert corrected.payload.skill_name == "scan"
    second_prompt = model.requests[1].prompt
    assert "invalid skill arguments" in second_prompt
    assert "target visible" not in second_prompt  # thinking is not persisted as hidden rationale
    assert "approaching target" in second_prompt
    assert policy.stats()["aerialclaw_protocol_rejections"] == 1.0


def test_search_cannot_claim_stuck_while_coverage_options_remain() -> None:
    policy, model = policy_with([stuck_reply(), reply()])
    envelope = asyncio.run(policy.decide(context()))
    assert envelope is not None
    assert isinstance(envelope.payload, SkillCall)
    assert envelope.payload.skill_name == "goto"
    assert len(model.requests) == 2
    assert policy.stats()["aerialclaw_protocol_rejections"] == 1.0


def test_search_cannot_keep_scanning_after_a_full_turn() -> None:
    policy, model = policy_with([scan_reply(), reply()])
    policy._scan_angle_since_motion_rad = math.tau
    envelope = asyncio.run(policy.decide(context()))
    assert envelope is not None
    assert isinstance(envelope.payload, SkillCall)
    assert envelope.payload.skill_name == "goto"
    assert len(model.requests) == 2
    assert policy.stats()["aerialclaw_protocol_rejections"] == 1.0


def test_unsupported_done_is_rejected_before_the_router() -> None:
    policy, model = policy_with([done_reply(), scan_reply()])
    ctx = context(position=Vec3(x=-20.0, y=-20.0, z=3.0))
    envelope = asyncio.run(policy.decide(ctx))
    assert envelope is not None
    assert isinstance(envelope.payload, SkillCall)
    assert envelope.payload.skill_name == "scan"
    assert len(model.requests) == 2
    assert policy.stats()["aerialclaw_protocol_rejections"] == 1.0


def test_soft_skill_document_materially_changes_the_prompt() -> None:
    policy, _ = policy_with([reply()])
    original = policy._build_prompt(context())
    policy.strategies["object_search"] = "# Replacement strategy\nscan exactly once"
    changed = policy._build_prompt(context())
    assert original != changed
    assert "Replacement strategy" in changed


def test_completion_evidence_uses_only_exact_label_and_current_kinematics() -> None:
    policy, _ = policy_with([reply()])
    evidence = policy._completion_evidence(context(position=Vec3(x=8.0, y=4.0, z=3.0)))
    assert evidence["supported"] is True
    assert evidence["source"] == "live exact-label detection"
    prompt = policy._build_prompt(context(position=Vec3(x=8.0, y=4.0, z=3.0)))
    assert '"supported": true' in prompt
    assert "scoring truth" in prompt


def test_navigation_reconnaissance_options_are_body_derived_and_bounded() -> None:
    policy, _ = policy_with([reply()])
    nav = MISSION.model_copy(update={"task_family": TaskFamily.LONG_HORIZON_NAV})
    policy.reset(nav, 1020)
    ctx = context()
    ctx.mission = nav
    policy._record_position(ctx.observation.position)
    options = policy._coverage_reference(ctx)
    assert len(options) == 4
    assert all(
        Vec3(
            x=float(option["goto_args"]["x"]),
            y=float(option["goto_args"]["y"]),
            z=float(option["goto_args"]["z"]),
        ).distance_to(ctx.observation.position)
        <= 17.5
        for option in options
    )


def test_navigation_reconnaissance_option_deflects_from_a_sensed_obstacle() -> None:
    policy, _ = policy_with([reply()])
    nav = MISSION.model_copy(update={"task_family": TaskFamily.LONG_HORIZON_NAV})
    policy.reset(nav, 1020)
    ctx = context()
    ctx.mission = nav
    bearings = tuple(-math.pi + i * (math.tau / 24) for i in range(24))
    ranges = tuple(5.0 if abs(abs(bearing) - math.pi) < 0.1 else 25.0 for bearing in bearings)
    ctx.observation = ctx.observation.model_copy(
        update={"yaw_rad": 0.0, "ray_bearings_rad": bearings, "range_rays": ranges}
    )
    policy._record_position(ctx.observation.position, ctx.observation.yaw_rad)

    options = policy._coverage_reference(ctx)
    back = next(option for option in options if option["id"] == 3)

    assert abs(float(back["goto_args"]["y"]) - ctx.observation.position.y) > 1.0


def test_object_search_coverage_is_frozen_relative_to_launch_yaw() -> None:
    policy, _ = policy_with([reply()])
    ctx = context()
    policy._record_position(ctx.observation.position, ctx.observation.yaw_rad)

    first = policy._coverage_reference(ctx)[0]
    dx = float(first["goto_args"]["x"]) - ctx.observation.position.x
    dy = float(first["goto_args"]["y"]) - ctx.observation.position.y

    assert math.atan2(dy, dx) == pytest.approx(ctx.observation.yaw_rad, abs=0.01)


def test_empty_or_malformed_output_fails_closed_without_a_script() -> None:
    policy, _ = policy_with(["", "not-json"])
    with pytest.raises(AerialClawOutputError, match="no valid decision"):
        asyncio.run(policy.decide(context()))


def test_terminal_decision_cannot_smuggle_an_action_through_the_schema() -> None:
    contradictory = (
        '{"thinking":"scan","decision":"stuck","action":{"skill":"scan",'
        '"args":{}},"reflection":null,"goal_progress":"searching","confidence":0.7}'
    )
    policy, model = policy_with([contradictory, contradictory])
    with pytest.raises(AerialClawOutputError, match="no valid decision"):
        asyncio.run(policy.decide(context()))
    schema_text = str(model.requests[0].response_schema)
    assert "_ActDecision" in schema_text
    assert "_StuckDecision" in schema_text


def test_cost_only_simulated_inference_is_refused() -> None:
    policy = AerialClawAgentPolicy()
    backend = SimulatedInference()
    services = RuntimeServices(
        clock=SimClock(),
        log=EventLog("ac-test", None),
        feature_cache=FeatureCache(),
        inference=backend,
        episode_id="ac-test",
    )
    bind(backend, services)
    bind(policy, services)
    policy.reset(MISSION, 1020)
    with pytest.raises(AerialClawUnavailable, match="cost-only"):
        asyncio.run(policy.decide(context()))


@pytest.mark.parametrize(
    "call",
    [
        SkillCall(skill_name="goto", args={"x": 1.0, "y": 2.0}),
        SkillCall(skill_name="goto", args={"x": 1.0, "y": 2.0, "z": 3.0, "hack": 1.0}),
        SkillCall(skill_name="move", args={"dx": 0.0, "dy": 0.0, "dz": 0.0}),
        SkillCall(skill_name="scan", args={"duration_s": 100.0}),
    ],
)
def test_skill_runtime_rejects_undocumented_or_invalid_arguments(call: SkillCall) -> None:
    with pytest.raises(InvalidSkillArguments):
        SkillRuntime(MISSION.allowed_skills).expand(call, context())


@pytest.mark.parametrize(
    "position,speed,allowed",
    [
        (Vec3(x=12, y=0, z=3), 0.0, True),
        (Vec3(x=10, y=0, z=3), 0.75, True),
        (Vec3(x=9.99, y=0, z=3), 0.0, False),
        (Vec3(x=12, y=0, z=3), 0.76, False),
    ],
)
def test_coordinate_done_and_runtime_share_live_arrival_contract(position, speed, allowed):
    from dataclasses import replace

    mission = MISSION.model_copy(
        update={
            "instruction": (
                "Fly to world ENU coordinate (12, 0, 3) metres "
                "and stop within 2 metres."
            ),
            "task_family": TaskFamily.KNOWN_GOAL_NAV,
        }
    )
    ctx = context(position=position)
    ctx = replace(
        ctx,
        mission=mission,
        perception=ctx.perception.model_copy(update={"detections": ()}),
        observation=ctx.observation.model_copy(update={"velocity": Vec3(x=speed, y=0, z=0)}),
    )
    policy, model = policy_with([done_reply()])
    policy.reset(mission, 1061)
    assert policy._completion_evidence(ctx)["supported"] is allowed
    if allowed:
        decision = asyncio.run(policy.decide(ctx))
        result = SkillRuntime(("stop",)).expand(decision.payload, ctx)
        assert result.label.value == "stop"
        assert len(model.requests) == 1
    else:
        with pytest.raises(InvalidSkillArguments):
            SkillRuntime(("stop",)).expand(SkillCall(skill_name="stop"), ctx)


def test_public_coordinate_evidence_never_uses_search_goal_or_ambiguous_text():
    from uavlab.core.mission_evidence import public_coordinate_goal

    known = MISSION.model_copy(update={"task_family": TaskFamily.KNOWN_GOAL_NAV})
    for text in (
        "fly to red pillar",
        "world ENU coordinate (NaN,0,3)",
        "world ENU coordinate (1e999,0,3)",
        "world ENU coordinate (12,0,3), then world ENU coordinate (4,5,3)",
    ):
        assert public_coordinate_goal(known.model_copy(update={"instruction": text})) is None
    instruction = "Fly to world ENU coordinate (-12.5, 2e1, 3)."
    assert public_coordinate_goal(MISSION.model_copy(update={"instruction": instruction})) is None
    assert public_coordinate_goal(known.model_copy(update={"instruction": instruction})) == Vec3(
        x=-12.5, y=20, z=3
    )


def test_saved_d104_done_reply_passes_coordinate_contract_without_reprompt():
    import json
    from dataclasses import replace
    from pathlib import Path

    record = json.loads(
        Path(
            "reports/capability_screen_20260912/c1_coordinate_completion/call-000002.json"
        ).read_text(encoding="utf-8")
    )
    mission = MISSION.model_copy(
        update={
            "instruction": (
                "Fly to world ENU coordinate (12, 0, 3) metres "
                "and stop within 2 metres."
            ),
            "task_family": TaskFamily.KNOWN_GOAL_NAV,
        }
    )
    ctx = context(position=Vec3(x=11.92, y=0, z=3))
    ctx = replace(
        ctx, mission=mission, perception=ctx.perception.model_copy(update={"detections": ()})
    )
    policy, model = policy_with([record["response"]])
    policy.reset(mission, 1061)
    decision = asyncio.run(policy.decide(ctx))
    assert SkillRuntime(("stop",)).expand(decision.payload, ctx).label.value == "stop"
    assert policy.stats()["aerialclaw_protocol_rejections"] == 0
    assert len(model.requests) == 1
