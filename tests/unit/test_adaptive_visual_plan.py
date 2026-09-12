"""Model authority, world-point persistence and unprivileged feedback tests."""

import asyncio
import json
import math
from copy import deepcopy

import pytest

from uavlab.contracts import MemorySnapshot, MissionSpec, PerceptionState, TaskFamily, Vec3
from uavlab.core.clock import SimClock
from uavlab.core.compose import load_architecture
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult, RoutingFeedback
from uavlab.plugins.reasoning.adaptive_visual_plan import AdaptiveVisualPlanPolicy

MISSION = MissionSpec(
    mission_id="adaptive-test",
    instruction="fly to the red tower and stop there",
    task_family=TaskFamily.LONG_HORIZON_NAV,
)


class Stub:
    def __init__(self, replies):
        self.replies = replies
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        return InferenceResult(payload=self.replies.pop(0))


def reply(**overrides):
    result = {
        "assessment": "uncertain",
        "reason": "An opening may reveal the route.",
        "plan": [
            {
                "id": "look",
                "objective": "View around the right obstacle",
                "expected_view": "Space behind the obstacle becomes visible",
            },
            {
                "id": "approach",
                "objective": "Approach the red tower",
                "expected_view": "The red tower is close",
            },
        ],
        "active_id": "look",
        "scene_memory": "Tower partly occluded; passage width uncertain.",
        "action": {"mode": "move", "u": 750, "v": 450, "distance": 7},
    }
    result.update(overrides)
    return json.dumps(result)


def setup(replies, **params):
    env = REGISTRY.build("environment", "grid3d", {"render": True, "render_depth": True})
    obs = asyncio.run(env.reset(MISSION, 1061))
    ctx = DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="adaptive-test",
    )
    backend = Stub(replies)
    service = RuntimeServices(
        clock=SimClock(),
        log=EventLog("adaptive-test"),
        feature_cache=FeatureCache(),
        inference=backend,
        episode_id="adaptive-test",
    )
    policy = AdaptiveVisualPlanPolicy(**params)
    bind(policy, service)
    policy.reset(MISSION, 1061)
    return policy, backend, ctx, service


def decide(policy, ctx):
    return asyncio.run(policy.decide(ctx))


def test_model_authors_order_active_step_and_waypoint_without_oracle():
    policy, model, ctx, service = setup([reply(active_id="approach")])
    # Poison channels forbidden to this policy. They must never enter the request.
    ctx.observation = ctx.observation.model_copy(
        update={
            "privileged": {"goal": [99999, 88888, 77777]},
            "semantic_hits": ("POISONED_DETECTOR",),
        }
    )
    output = decide(policy, ctx)
    assert output.provenance["active_subgoal_id"] == "approach"  # Not list[0].
    assert output.payload.target_label is None
    assert not output.payload.stop_at_target
    assert output.payload.target != ctx.observation.position
    prompt = model.requests[0].prompt
    assert "99999" not in prompt and "POISONED_DETECTOR" not in prompt
    assert model.requests[0].image_count == 1 and len(model.requests[0].images) == 1
    event = service.log.events[-1]
    assert event.trace_id == output.decision_id
    assert event.payload["response"]["active_id"] == "approach"
    assert event.payload["response"]["plan"][0]["id"] == "look"


def test_retained_world_point_survives_camera_motion_and_arrival_without_auto_advance():
    policy, model, ctx, _ = setup([reply(), reply(action={"mode": "retain"})])
    first = decide(policy, ctx)
    ctx.observation = ctx.observation.model_copy(
        update={
            "position": first.payload.target,
            "yaw_rad": math.pi / 2,
            "seq": 99,
        }
    )
    second = decide(policy, ctx)
    assert second.payload.target == first.payload.target
    assert second.payload.tolerance_m == first.payload.tolerance_m
    assert second.provenance["active_subgoal_id"] == "look"
    assert second.provenance["point_source_observation_seq"] == str(first.source_observation_seq)
    state = json.loads(model.requests[1].prompt.split("INPUT STATE:\n")[1])
    assert state["previous_response"]["plan"][0]["id"] == "look"
    assert state["distance_to_proposed_point_m"] == 0
    assert policy.stats()["adaptive_plan_retained_goals"] == 1


def test_model_replanning_changes_the_point_and_carries_matched_failure():
    policy, model, ctx, service = setup(
        [
            reply(),
            reply(
                assessment="blocked",
                active_id="approach",
                action={"mode": "move", "u": 250, "v": 450, "distance": 7},
            ),
        ]
    )
    first = decide(policy, ctx)
    old_event = deepcopy(service.log.events[-1].payload)
    ctx.last_routing_feedback = RoutingFeedback(
        first.decision_id,
        False,
        "no known-free prefix",
        first.kind,
        None,
        ctx.t_sim_ns,
    )
    second = decide(policy, ctx)
    assert second.payload.target != first.payload.target
    assert second.provenance["active_subgoal_id"] == "approach"
    assert second.provenance["plan_revision"] == "2"
    state = json.loads(model.requests[1].prompt.split("INPUT STATE:\n")[1])
    assert state["history"][0]["routing"]["accepted_not_completed"] is False
    assert "no known-free prefix" in model.requests[1].prompt
    assert service.log.events[0].payload == old_event  # Historical evidence is immutable.


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        reply(extra="undeclared"),
        reply(active_id="missing"),
        reply(action={"mode": "move", "u": True, "v": 400, "distance": 7}),
        reply(action={"mode": "move", "u": 1001, "v": 400, "distance": 7}),
        reply(action={"mode": "move", "u": 500, "v": 400, "distance": 0}),
        reply(action={"mode": "retain", "u": 500}),
        reply(active_id="approach", action={"mode": "retain"}),
        reply(plan=[{"id": "x", "objective": "a", "expected_view": "b"}] * 2, active_id="x"),
    ],
)
def test_bad_output_cannot_mutate_the_existing_plan_or_generate_fallback_motion(bad):
    policy, _, ctx, service = setup([reply(), bad])
    decide(policy, ctx)
    before = policy.snapshot()
    events = len(service.log.events)
    with pytest.raises(RuntimeError, match="invalid adaptive visual plan"):
        decide(policy, ctx)
    assert policy.snapshot() == before
    assert len(service.log.events) == events


def test_retain_without_a_point_fails_closed_and_reset_discards_all_state():
    policy, model, ctx, _ = setup([reply(action={"mode": "retain"}), reply()])
    with pytest.raises(RuntimeError, match="existing world point"):
        decide(policy, ctx)
    decide(policy, ctx)
    policy.reset(MISSION, 1062)
    assert policy.snapshot() == {
        "revision": 0,
        "previous_response": None,
        "proposed_world_point": None,
        "point_origin": None,
        "history": [],
    }
    assert len(model.requests) == 2


def test_unrelated_feedback_is_not_attached_and_snapshots_are_independent():
    policy, model, ctx, _ = setup([reply(), reply(action={"mode": "retain"})], history_limit=1)
    first = decide(policy, ctx)
    external = policy.snapshot()
    external["history"][0]["routing"] = "tampered"
    ctx.last_routing_feedback = RoutingFeedback(
        "another-policy",
        False,
        "unrelated-rejection",
        first.kind,
        None,
        ctx.t_sim_ns,
    )
    decide(policy, ctx)
    assert "unrelated-rejection" not in model.requests[1].prompt
    assert "tampered" not in model.requests[1].prompt
    assert len(policy.snapshot()["history"]) == 1


def test_small_step_is_not_already_inside_the_waypoint_tolerance():
    policy, _, ctx, _ = setup([reply(action={"mode": "move", "u": 500, "v": 500, "distance": 1})])
    output = decide(policy, ctx)
    assert output.payload.tolerance_m < output.payload.target.distance_to(ctx.observation.position)


def test_development_profile_preserves_shared_execution_and_uses_only_gemma():
    original = load_architecture("c5_gemma_guarded_monitor_dev")
    new = load_architecture("vlm_adaptive_plan_gemma_dev")
    for field in (
        "planner",
        "controller",
        "shield",
        "monitor",
        "scheduler",
        "staleness",
        "perception",
        "memory",
    ):
        assert getattr(new, field) == getattr(original, field), field
    assert new.inference.name == "ollama"
    assert new.inference.params["model_id"] == new.policy.params["model_id"] == "gemma4:e2b"
    assert new.inference.params["expected_digest"] == original.inference.params["expected_digest"]
    assert new.verifier.name == "semantic_geometric" and not new.verifier.params["repair"]
    assert "coordinate_contract" not in new.policy.params
    policy = REGISTRY.build("policy", new.policy.name, new.policy.params)
    assert policy.name == "adaptive_visual_plan"


def test_model_waypoint_reaches_shared_super_and_controller_in_clear_space():
    from uavlab.core.decision_router import DecisionRouter

    policy, _, ctx, _ = setup([reply(action={"mode": "move", "u": 500, "v": 420, "distance": 5})])
    ctx.observation = ctx.observation.model_copy(
        update={
            "position": Vec3(x=0.0, y=0.0, z=3.0),
            "yaw_rad": 0.0,
            "velocity": Vec3(x=0.0, y=0.0, z=0.0),
            "range_rays": (25.0,) * 24,
            "ray_bearings_rad": tuple(-math.pi + i * math.tau / 24 for i in range(24)),
        }
    )
    config = load_architecture("vlm_adaptive_plan_gemma_dev")
    components = {}
    for name in ("planner", "verifier", "controller"):
        spec = getattr(config, name)
        components[name] = REGISTRY.build(name, spec.name, spec.params)
        components[name].reset(MISSION, 1061)
    router = DecisionRouter(config, shield=None, **components)
    router.reset(MISSION, 1061)
    output = decide(policy, ctx)
    outcome = router.accept(output, ctx)
    assert outcome.accepted, outcome.reason
    command, _, _ = router.command_for_tick(ctx)
    assert command.velocity.x > 0
    assert not router.stop_requested
