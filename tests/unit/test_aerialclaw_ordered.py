"""Order evidence cannot be fabricated by a done message or a sparse observation."""

import asyncio
from dataclasses import replace

import pytest

from tests.unit.test_aerialclaw_visual import MISSION, action, context, policy
from uavlab.contracts import SkillCall, TaskFamily, Vec3
from uavlab.core.mission_evidence import OrderedVisitEvidence, public_ordered_visit
from uavlab.core.services import bind
from uavlab.core.skills import InvalidSkillArguments, validate_skill_call
from uavlab.plugins.reasoning.aerialclaw_ordered import AerialClawOrderedVisualPolicy

ORDERED = MISSION.model_copy(
    update={
        "task_family": TaskFamily.MULTI_STAGE,
        "instruction": "Visit the red pillar first, staying within 2 metres for at least half a second, then visit the blue pillar and stop within 2 metres.",
    }
)


def evidence():
    contract = public_ordered_visit(ORDERED)
    ev = OrderedVisitEvidence(contract)
    ev.locate("red pillar", Vec3(x=0, y=0, z=3), 0)
    ev.locate("blue pillar", Vec3(x=10, y=0, z=3), 0)
    return ev


def obs(index, x=0):
    return context().observation.model_copy(
        update={"seq": index + 1, "t_sim_ns": index * 50_000_000, "position": Vec3(x=x, y=0, z=3)}
    )


def test_ordered_runtime_rejects_blue_first_and_accepts_observed_red_then_blue():
    ev = evidence()
    ctx = replace(
        context(), mission=ORDERED, scratch={"ordered_visit_evidence": ev}, observation=obs(0, 10)
    )
    with pytest.raises(InvalidSkillArguments):
        validate_skill_call(SkillCall(skill_name="stop"), ctx)
    for i in range(11):
        ev.observe(obs(i))
    assert ev.first_completed_t_ns == 500_000_000
    ctx = replace(ctx, observation=obs(12, 10), t_sim_ns=600_000_000)
    validate_skill_call(SkillCall(skill_name="stop"), ctx)
    assert not ev.stop_supported(obs(13, 0))  # first object alone is not completion
    assert not ev.stop_supported(obs(1000, 10))  # stale location


def test_dwell_needs_contiguous_observations_and_resets_outside_radius():
    ev = evidence()
    ev.observe(obs(0))
    ev.observe(obs(20))
    assert ev.first_completed_t_ns is None
    for i in range(21, 28):
        ev.observe(obs(i))
    ev.observe(obs(28, 5))
    for i in range(29, 39):
        ev.observe(obs(i))
    assert ev.first_completed_t_ns is None
    ev.observe(obs(39))
    assert ev.first_completed_t_ns == 1_950_000_000


def test_two_queries_keep_identity_and_do_not_command_motion_or_complete_order():
    template, model = policy(
        [action("detect_object", {"query": "blue pillar"}), '{"visible":true,"u":502,"v":502}']
    )
    p = AerialClawOrderedVisualPolicy(
        model_id=model.model_id,
        visual_target_query="red pillar",
        camera_pitch_rad=0,
        allowed_skills=ORDERED.allowed_skills,
    )
    bind(p, template.services)
    p.reset(ORDERED, 1061)
    ctx = replace(context(), mission=ORDERED)
    assert asyncio.run(p.decide(ctx)) is None
    assert asyncio.run(p.decide(replace(context(9), mission=ORDERED))) is None
    assert set(p._ordered.locations) == {"blue pillar"}
    assert p._visual_memory.label == "blue pillar"
    assert not p._completion_evidence(replace(context(10), mission=ORDERED))["supported"]
    assert p._active_skill is None
    assert not model.requests[0].images and len(model.requests[1].images) == 1
    assert '"query":"red pillar"' in p._build_prompt(ctx)
    assert '"query":"blue pillar"' in p._build_prompt(ctx)
    prompt = p._build_prompt(ctx)
    assert "inspect the new passive detections" not in prompt
    assert "Use one bounded full-turn scan" not in prompt
    assert "Start by requesting detect_object" in prompt
    p.reset(ORDERED, 1061)
    assert not p._ordered.locations and p._ordered.first_completed_t_ns is None


def test_public_order_contract_does_not_infer_unstated_sequence():
    assert public_ordered_visit(MISSION) is None
    assert (
        public_ordered_visit(ORDERED.model_copy(update={"instruction": "Find red and blue"}))
        is None
    )
