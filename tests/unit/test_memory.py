"""Focused invariants for the semantic-memory implementations."""

from __future__ import annotations

from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    TaskFamily,
    Vec3,
    WaypointGoal,
)
from uavlab.plugins.memory.stores import DECISION_KIND, ShortContext

MISSION = MissionSpec(
    mission_id="memory-test",
    instruction="find the red tower",
    task_family=TaskFamily.OBJECT_SEARCH,
    allowed_skills=("goto", "scan", "stop"),
)


def _observation(seq: int) -> ObservationPacket:
    return ObservationPacket(
        seq=seq,
        t_sim_ns=seq * 1_000_000_000,
        t_wall_ns=seq * 1_000_000_000,
        position=Vec3(x=0.0, y=0.0, z=5.0),
        velocity=Vec3(x=0.0, y=0.0, z=0.0),
        yaw_rad=0.0,
    )


def _decision(decision_id: str) -> DecisionEnvelope:
    payload = WaypointGoal(
        target=Vec3(x=10.0, y=2.0, z=5.0),
        target_label="red tower",
    )
    return DecisionEnvelope(
        decision_id=decision_id,
        kind=DecisionKind.WAYPOINT,
        payload=payload,
        source_observation_seq=1,
        source_t_sim_ns=1_000_000_000,
        produced_t_wall_ns=1_000_000_000,
        produced_t_sim_ns=1_000_000_000,
    )


def test_short_context_records_an_active_decision_only_once() -> None:
    memory = ShortContext(window=8)
    memory.reset(MISSION, seed=1000)
    decision = _decision("same-active-decision")

    for seq in range(1, 6):
        observation = _observation(seq)
        perception = PerceptionState(
            observation_seq=seq,
            t_sim_ns=observation.t_sim_ns,
        )
        memory.update(observation, perception, decision)

    decision_items = [item for item in memory.snapshot().items if item.kind == DECISION_KIND]
    assert len(decision_items) == 1


def test_short_context_accepts_same_decision_id_again_after_reset() -> None:
    memory = ShortContext(window=8)
    decision = _decision("episode-local-id")

    for seed in (1000, 1001):
        memory.reset(MISSION, seed=seed)
        observation = _observation(1)
        perception = PerceptionState(observation_seq=1, t_sim_ns=observation.t_sim_ns)
        memory.update(observation, perception, decision)
        assert sum(item.kind == DECISION_KIND for item in memory.snapshot().items) == 1
