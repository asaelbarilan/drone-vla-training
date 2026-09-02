"""PMR recovery reasoning stays model-driven, symbolic, and shared-path routed."""

from __future__ import annotations

import asyncio
import json

import pytest

from uavlab.contracts import (
    DecisionKind,
    Detection,
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    OccupancyHint,
    PerceptionState,
    ProgressLabel,
    ProgressState,
    RecoveryRequest,
    RecoveryTrigger,
    SkillCall,
    TaskFamily,
    Vec3,
)
from uavlab.core.clock import SimClock
from uavlab.core.decision_router import DecisionRouter
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.core.skills import SkillRuntime
from uavlab.interfaces import DecisionContext, InferenceResult, RoutingFeedback
from uavlab.plugins.inference.role_router import RoleRoutedInference
from uavlab.plugins.inference.simulated import SimulatedInference
from uavlab.plugins.recovery.pmr import PMRRecoveryReasoner, PMRUnavailable

MISSION = MissionSpec(
    mission_id="pmr-recovery-test",
    instruction="find the red target and stop safely",
    task_family=TaskFamily.FAILURE_RECOVERY,
    allowed_skills=("goto", "approach", "hover", "scan", "back_off", "ascend", "stop"),
)


class StubReasoner:
    name = "stub_real_reasoner"
    model_id = "gpt-oss:20b"

    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = replies
        self.requests = []

    async def invoke(self, request) -> InferenceResult:
        self.requests.append(request)
        reply = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return InferenceResult(payload=reply, output_tokens=16)


def _context() -> DecisionContext:
    t_ns = 2_000_000_000
    obs = ObservationPacket(
        seq=3,
        t_sim_ns=t_ns,
        t_wall_ns=10,
        position=Vec3(x=1.0, y=2.0, z=3.0),
        velocity=Vec3(x=0.1, y=0.0, z=0.0),
        yaw_rad=0.2,
        battery_frac=0.75,
    )
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(
            observation_seq=obs.seq,
            t_sim_ns=t_ns,
            detections=(
                Detection(
                    label="target",
                    score=0.8,
                    position=Vec3(x=8.0, y=4.0, z=3.0),
                    distance_m=7.3,
                ),
            ),
            geometry=OccupancyHint(free_radius_m=0.9),
            uncertainty=0.4,
        ),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=t_ns),
        t_sim_ns=t_ns,
        t_wall_ns=10,
        episode_id="pmr-recovery-test",
        last_progress=ProgressState(
            label=ProgressLabel.BLOCKED,
            observation_seq=obs.seq,
            t_sim_ns=t_ns,
            stalled_for_s=4.0,
            evidence="path blocked",
        ),
        last_routing_feedback=RoutingFeedback(
            decision_id="previous",
            accepted=False,
            reason="planner infeasible",
            proposed_kind=DecisionKind.WAYPOINT,
            expanded_kind=None,
            t_sim_ns=t_ns,
        ),
    )


def _request() -> RecoveryRequest:
    return RecoveryRequest(
        trigger=RecoveryTrigger(
            name="learned_cvi",
            fired_t_sim_ns=2_000_000_000,
            observation_seq=3,
            cause="learned_cvi:0.999",
        ),
        state_summary="target seen before route became blocked",
        allowed_skills=MISSION.allowed_skills,
        call_index=0,
    )


def _reasoner(replies: list[str | Exception]) -> tuple[PMRRecoveryReasoner, StubReasoner]:
    backend = StubReasoner(replies)
    reasoner = PMRRecoveryReasoner(model_id=backend.model_id)
    bind(
        reasoner,
        RuntimeServices(
            clock=SimClock(start_ns=2_000_000_000),
            log=EventLog("pmr-recovery-test", None),
            feature_cache=FeatureCache(),
            inference=backend,
        ),
    )
    reasoner.reset(MISSION, 1)
    return reasoner, backend


def _reply(decision: str, option: str) -> str:
    return json.dumps(
        {
            "decision": decision,
            "reason": "bounded recovery is appropriate",
            "suggested_option": option,
            "risk": "medium",
            "confidence": 0.8,
        }
    )


def test_model_selects_symbolic_repair_and_local_code_supplies_skill_arguments() -> None:
    reasoner, backend = _reasoner([_reply("local_repair", "back_off")])

    envelope = asyncio.run(reasoner.recover(_request(), _context()))

    assert envelope is not None
    assert envelope.kind is DecisionKind.SKILL
    assert isinstance(envelope.payload, SkillCall)
    assert envelope.payload == SkillCall(skill_name="back_off", args={"distance_m": 3.0})
    assert backend.requests[0].response_schema is not None
    schema_text = json.dumps(backend.requests[0].response_schema)
    assert '"x"' not in schema_text
    assert '"velocity"' not in schema_text
    assert "Never output coordinates" in backend.requests[0].prompt
    assert "privileged" not in backend.requests[0].prompt.lower()


def test_invalid_extra_flight_fields_are_rejected_then_retried() -> None:
    invalid = json.loads(_reply("local_repair", "back_off"))
    invalid["x"] = 999
    reasoner, backend = _reasoner(
        [json.dumps(invalid), _reply("goal_alignment", "scan_right")]
    )

    envelope = asyncio.run(reasoner.recover(_request(), _context()))

    assert envelope is not None
    assert isinstance(envelope.payload, SkillCall)
    assert envelope.payload.skill_name == "scan"
    assert envelope.payload.args["yaw_rate_rps"] == -0.8
    assert len(backend.requests) == 2
    assert reasoner.stats()["pmr_reasoner_parse_failures"] == 1.0


def test_backend_failure_uses_typed_local_hold_without_fabricating_model_output() -> None:
    reasoner, _ = _reasoner([RuntimeError("offline")])

    envelope = asyncio.run(reasoner.recover(_request(), _context()))

    assert envelope is not None
    assert envelope.payload == SkillCall(skill_name="hover")
    assert envelope.provenance["agent_decision"] == "local_fallback"
    assert reasoner.stats()["pmr_reasoner_backend_failures"] == 1.0


def test_cost_only_backend_is_refused_even_when_nested_in_role_router() -> None:
    router = RoleRoutedInference(
        routes={
            "policy": {"name": "simulated", "params": {"model_id": "vision"}},
            "reasoner": {
                "name": "simulated",
                "params": {"model_id": "gpt-oss:20b"},
            },
        }
    )
    reasoner = PMRRecoveryReasoner(model_id="gpt-oss:20b")
    bind(
        reasoner,
        RuntimeServices(
            clock=SimClock(),
            log=EventLog("pmr-refusal", None),
            feature_cache=FeatureCache(),
            inference=router,
        ),
    )

    with pytest.raises(PMRUnavailable, match="cost-only"):
        asyncio.run(reasoner.recover(_request(), _context()))


def test_symbolic_pmr_skill_uses_the_shared_verifier_and_planner(
    arch_factory,
) -> None:
    reasoner, _ = _reasoner([_reply("goal_resume", "resume_target")])
    ctx = _context()
    envelope = asyncio.run(reasoner.recover(_request(), ctx))
    assert envelope is not None
    arch = arch_factory("c6")
    verifier = REGISTRY.build("verifier", arch.verifier.name, arch.verifier.params)
    planner = REGISTRY.build("planner", arch.planner.name, arch.planner.params)
    controller = REGISTRY.build("controller", arch.controller.name, arch.controller.params)
    router = DecisionRouter(
        arch,
        verifier=verifier,
        planner=planner,
        shield=None,
        controller=controller,
        skill_runtime=SkillRuntime(MISSION.allowed_skills),
    )
    router.reset(MISSION, 1)

    outcome = router.accept(envelope, ctx)

    # The minimal unit context intentionally has no range scan. Reaching
    # SUPER's geometric-data rejection proves the recovery skill did not take
    # a private execution path around the verifier or planner.
    assert not outcome.accepted
    assert "planner reported infeasible" in outcome.reason
    assert outcome.expanded_kind is DecisionKind.WAYPOINT
    assert outcome.verification is not None
    assert outcome.verification.accepted
    assert outcome.trajectory is not None
    assert not outcome.trajectory.feasible
    assert router.counters.plans_requested == 1


def test_role_router_enforces_per_role_model_identity() -> None:
    router = RoleRoutedInference(
        routes={
            "policy": {"name": "simulated", "params": {"model_id": "vision"}},
            "reasoner": {"name": "simulated", "params": {"model_id": "text"}},
        }
    )
    assert router.model_for_role("policy") == "vision"
    assert router.model_for_role("reasoner") == "text"
    with pytest.raises(RuntimeError, match="route serves 'text'"):
        asyncio.run(
            router.invoke(
                # The role must not silently execute against the policy model.
                type("Request", (), {"role": "reasoner", "model_id": "vision"})()
            )
        )


def test_direct_simulated_backend_is_refused() -> None:
    reasoner = PMRRecoveryReasoner(model_id="gpt-oss:20b")
    backend = SimulatedInference(model_id="gpt-oss:20b")
    bind(
        reasoner,
        RuntimeServices(
            clock=SimClock(),
            log=EventLog("pmr-refusal", None),
            feature_cache=FeatureCache(),
            inference=backend,
        ),
    )
    with pytest.raises(PMRUnavailable, match="cost-only"):
        asyncio.run(reasoner.recover(_request(), _context()))
