"""Paper-defining PMR learned-CVI admission contracts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from uavlab.contracts import (
    AdmissionRuntime,
    DecisionEnvelope,
    DecisionKind,
    Detection,
    EventType,
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    OccupancyHint,
    PerceptionState,
    ProgressLabel,
    ProgressState,
    SuccessCriteria,
    TaskFamily,
    Vec3,
    WaypointGoal,
)
from uavlab.core.config import ArchitectureConfig
from uavlab.interfaces import DecisionContext, RoutingFeedback
from uavlab.plugins.admission.pmr import (
    CHECKPOINT_FORMAT,
    FEATURE_NAMES,
    PMRCVIAdmission,
)


def _write_checkpoint(path: Path, *, bias: float) -> Path:
    path.write_text(
        json.dumps(
            {
                "format": CHECKPOINT_FORMAT,
                "trained": True,
                "feature_names": list(FEATURE_NAMES),
                "mean": [0.0] * len(FEATURE_NAMES),
                "scale": [1.0] * len(FEATURE_NAMES),
                "weights": [0.0] * len(FEATURE_NAMES),
                "bias": bias,
                "threshold": 0.997,
                "training_provenance": {"purpose": "unit-test fixture"},
            }
        ),
        encoding="utf-8",
    )
    return path


def _context(
    *,
    distance_m: float = 10.0,
    stalled_for_s: float = 0.0,
    label: ProgressLabel = ProgressLabel.CONTINUE,
    clearance_m: float = 5.0,
) -> DecisionContext:
    t_ns = 12_000_000_000
    position = Vec3(x=1.0, y=2.0, z=3.0)
    target = Vec3(x=position.x + distance_m, y=position.y, z=position.z)
    mission = MissionSpec(
        mission_id="pmr-test",
        instruction="fly to the target",
        task_family=TaskFamily.FAILURE_RECOVERY,
        success=SuccessCriteria(goal_radius_m=2.0),
    )
    observation = ObservationPacket(
        seq=7,
        t_sim_ns=t_ns,
        t_wall_ns=t_ns,
        position=position,
        velocity=Vec3(x=0.2, y=0.0, z=0.0),
        yaw_rad=0.0,
        battery_frac=0.8,
    )
    perception = PerceptionState(
        observation_seq=7,
        t_sim_ns=t_ns,
        detections=(
            Detection(
                label="target",
                score=0.75,
                position=target,
                distance_m=distance_m,
            ),
        ),
        geometry=OccupancyHint(free_radius_m=clearance_m),
        uncertainty=0.2,
    )
    decision = DecisionEnvelope(
        decision_id="pmr-waypoint",
        kind=DecisionKind.WAYPOINT,
        payload=WaypointGoal(target=target, target_label="target"),
        source_observation_seq=7,
        source_t_sim_ns=t_ns,
        produced_t_wall_ns=t_ns,
        produced_t_sim_ns=t_ns,
        producer="test",
    )
    return DecisionContext(
        mission=mission,
        observation=observation,
        perception=perception,
        memory=MemorySnapshot(observation_seq=7, t_sim_ns=t_ns),
        t_sim_ns=t_ns,
        t_wall_ns=t_ns,
        episode_id="pmr-test",
        last_progress=ProgressState(
            label=label,
            observation_seq=7,
            t_sim_ns=t_ns,
            distance_to_goal_m=distance_m,
            stalled_for_s=stalled_for_s,
        ),
        last_decision=decision,
        last_routing_feedback=RoutingFeedback(
            decision_id=decision.decision_id,
            accepted=True,
            reason="accepted",
            proposed_kind=DecisionKind.WAYPOINT,
            expanded_kind=DecisionKind.KINEMATIC_ACTION,
            t_sim_ns=t_ns,
        ),
    )


def _runtime(*, planner_failed: bool = False) -> AdmissionRuntime:
    return AdmissionRuntime(
        t_sim_ns=12_000_000_000,
        call_count=0,
        max_calls=3,
        cooldown_s=4.0,
        planner_failed=planner_failed,
    )


def test_learned_cvi_emits_the_fixed_18d_contract_and_admits_high_score(tmp_path):
    gate = PMRCVIAdmission(
        checkpoint_path=str(_write_checkpoint(tmp_path / "high.json", bias=20.0))
    )

    decision = asyncio.run(gate.assess(_context(), _runtime()))

    assert decision.admit
    assert decision.score > decision.threshold
    assert decision.feature_names == FEATURE_NAMES
    assert len(decision.features) == 18
    assert all(decision.guards.values())


def test_runtime_guard_suppresses_reasoning_inside_terminal_radius(tmp_path):
    gate = PMRCVIAdmission(
        checkpoint_path=str(_write_checkpoint(tmp_path / "terminal.json", bias=20.0))
    )

    decision = asyncio.run(gate.assess(_context(distance_m=1.0), _runtime()))

    assert not decision.admit
    assert not decision.guards["outside_terminal_radius"]
    assert decision.reason.startswith("runtime_guard:")


def test_hard_stuck_guard_overrides_a_low_learned_score(tmp_path):
    gate = PMRCVIAdmission(
        checkpoint_path=str(_write_checkpoint(tmp_path / "low.json", bias=-20.0))
    )

    decision = asyncio.run(
        gate.assess(
            _context(
                stalled_for_s=12.0,
                label=ProgressLabel.BLOCKED,
                clearance_m=0.8,
            ),
            _runtime(planner_failed=True),
        )
    )

    assert decision.score < decision.threshold
    assert decision.hard_stuck
    assert decision.admit


def test_c6_routes_admitted_cvi_decisions_through_the_shared_trigger_loop(
    tmp_path,
    arch_factory,
    env_factory,
    runner,
):
    checkpoint = _write_checkpoint(tmp_path / "integration.json", bias=20.0)
    raw = arch_factory("c6").model_dump(mode="python")
    raw["admission"] = {
        "name": "pmr_cvi",
        "params": {"checkpoint_path": str(checkpoint)},
    }
    raw["scheduler"]["trigger"] = "learned_cvi"
    raw["scheduler"]["cooldown_s"] = 0.0
    raw["scheduler"]["max_calls"] = 1
    arch = ArchitectureConfig.model_validate(raw)
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 8.0})

    result, orchestrator = runner(arch, env, seed=2)

    assert result.error is None
    assert orchestrator.log.count(EventType.ADMISSION) > 0
    assert orchestrator.log.count(EventType.RECOVERY_TRIGGER) == 1
    event = orchestrator.log.of_type(EventType.ADMISSION)[0]
    assert len(event.payload["features"]) == 18
    assert event.payload["admitted"] is True
