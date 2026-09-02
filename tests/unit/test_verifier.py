"""Endpoint-versus-corridor invariants for the semantic verifier."""

from __future__ import annotations

from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    TaskFamily,
    Vec3,
    WaypointGoal,
)
from uavlab.interfaces import DecisionContext
from uavlab.plugins.verifier.bounds import SemanticGeometricVerifier

MISSION = MissionSpec(
    mission_id="verifier-test",
    instruction="reach the target",
    task_family=TaskFamily.LONG_HORIZON_NAV,
)


def _context(clearance_m: float) -> DecisionContext:
    observation = ObservationPacket(
        seq=1,
        t_sim_ns=0,
        t_wall_ns=0,
        position=Vec3(x=0.0, y=0.0, z=3.0),
        velocity=Vec3(x=0.0, y=0.0, z=0.0),
        yaw_rad=0.0,
        range_rays=(clearance_m,),
        ray_bearings_rad=(0.0,),
    )
    return DecisionContext(
        mission=MISSION,
        observation=observation,
        perception=PerceptionState(observation_seq=1, t_sim_ns=0),
        memory=MemorySnapshot(observation_seq=1, t_sim_ns=0),
        t_sim_ns=0,
        t_wall_ns=0,
        episode_id="verifier-test",
    )


def _envelope(distance_m: float) -> DecisionEnvelope:
    goal = WaypointGoal(target=Vec3(x=distance_m, y=0.0, z=3.0))
    return DecisionEnvelope(
        decision_id="waypoint",
        kind=DecisionKind.WAYPOINT,
        payload=goal,
        source_observation_seq=1,
        source_t_sim_ns=0,
        produced_t_wall_ns=0,
        produced_t_sim_ns=0,
    )


def test_verifier_delegates_a_blocked_corridor_to_the_planner() -> None:
    verifier = SemanticGeometricVerifier(min_clearance_m=1.2)
    verifier.reset(MISSION, seed=1000)

    result = verifier.verify(_envelope(10.0), _context(clearance_m=2.0))

    assert result.accepted


def test_verifier_rejects_an_endpoint_on_an_observed_obstacle() -> None:
    verifier = SemanticGeometricVerifier(min_clearance_m=1.2)
    verifier.reset(MISSION, seed=1000)

    result = verifier.verify(_envelope(2.0), _context(clearance_m=1.5))

    assert not result.accepted
    assert "target lies within" in result.reason


def test_verifier_does_not_treat_the_range_horizon_as_an_obstacle_hit() -> None:
    verifier = SemanticGeometricVerifier(
        min_clearance_m=1.2,
        sensing_horizon_m=25.0,
    )
    verifier.reset(MISSION, seed=1000)

    result = verifier.verify(_envelope(25.0), _context(clearance_m=25.0))

    assert result.accepted
