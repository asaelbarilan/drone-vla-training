"""Contract-level unit tests.

The contracts are the neutral ground the whole comparison stands on, so their
invariants are tested directly rather than only through episodes.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from uavlab.contracts import (
    REQUIRED_CONTRACTS,
    ActionChunk,
    ControlCommand,
    DecisionEnvelope,
    DecisionKind,
    EpisodeEvent,
    EventType,
    KinematicAction,
    MemorySnapshot,
    MissionDirective,
    MissionSpec,
    ProgressLabel,
    SkillCall,
    TaskFamily,
    Vec3,
    WaypointGoal,
    ns_to_s,
    s_to_ns,
)
import uavlab.contracts as contracts_module


def make_envelope(kind: DecisionKind, payload, **overrides) -> DecisionEnvelope:
    base = {
        "decision_id": "d1",
        "kind": kind,
        "payload": payload,
        "source_observation_seq": 4,
        "source_t_sim_ns": s_to_ns(1.0),
        "produced_t_wall_ns": 999,
        "produced_t_sim_ns": s_to_ns(1.3),
    }
    base.update(overrides)
    return DecisionEnvelope(**base)


def test_every_required_contract_is_exported():
    for name in REQUIRED_CONTRACTS:
        assert hasattr(contracts_module, name), f"contract {name} is missing from uavlab.contracts"


def test_contracts_reject_unknown_fields():
    """Extra fields are forbidden so a plugin cannot smuggle private state."""
    with pytest.raises(ValidationError):
        MemorySnapshot(observation_seq=1, t_sim_ns=0, secret_model_state="oops")


def test_contracts_are_immutable():
    goal = WaypointGoal(target=Vec3(x=1.0, y=2.0, z=3.0))
    with pytest.raises(ValidationError):
        goal.tolerance_m = 5.0


def test_time_conversion_roundtrip():
    assert s_to_ns(1.5) == 1_500_000_000
    assert ns_to_s(1_500_000_000) == pytest.approx(1.5)


def test_vec3_refuses_cross_frame_distance():
    from uavlab.contracts import Frame

    a = Vec3(x=0.0, y=0.0, z=0.0, frame=Frame.ENU)
    b = Vec3(x=1.0, y=0.0, z=0.0, frame=Frame.NED)
    with pytest.raises(ValueError, match="refusing to compare"):
        a.distance_to(b)


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        (DecisionKind.SKILL, SkillCall(skill_name="hover")),
        (DecisionKind.WAYPOINT, WaypointGoal(target=Vec3(x=1.0, y=1.0, z=3.0))),
        (
            DecisionKind.KINEMATIC_ACTION,
            KinematicAction(velocity=Vec3(x=1.0, y=0.0, z=0.0)),
        ),
        (
            DecisionKind.ACTION_CHUNK,
            ActionChunk(actions=(KinematicAction(velocity=Vec3(x=1.0, y=0.0, z=0.0)),)),
        ),
        (DecisionKind.MISSION_DIRECTIVE, MissionDirective(label=ProgressLabel.CONTINUE)),
    ],
)
def test_every_decision_kind_round_trips(kind, payload):
    envelope = make_envelope(kind, payload)
    restored = DecisionEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored.kind is kind
    assert restored.payload.kind is kind


def test_envelope_rejects_kind_payload_mismatch():
    """A mislabelled envelope would route a decision down the wrong path."""
    with pytest.raises(ValidationError):
        make_envelope(DecisionKind.WAYPOINT, SkillCall(skill_name="hover"))


def test_envelope_carries_mandatory_provenance():
    for field in (
        "decision_id",
        "source_observation_seq",
        "source_t_sim_ns",
        "produced_t_wall_ns",
        "valid_until_t_sim_ns",
        "confidence",
        "provenance",
    ):
        assert field in DecisionEnvelope.model_fields, f"DecisionEnvelope must expose {field}"


def test_decision_age_is_measured_from_the_source_observation():
    envelope = make_envelope(
        DecisionKind.WAYPOINT, WaypointGoal(target=Vec3(x=1.0, y=1.0, z=3.0))
    )
    # Produced at t=1.3s from an observation at t=1.0s, executed at t=2.0s:
    # the age is 1.0s, not the 0.7s of inference latency.
    assert envelope.age_ns(s_to_ns(2.0)) == s_to_ns(1.0)


def test_expiry_is_independent_of_age():
    envelope = make_envelope(
        DecisionKind.WAYPOINT,
        WaypointGoal(target=Vec3(x=1.0, y=1.0, z=3.0)),
        valid_until_t_sim_ns=s_to_ns(1.8),
    )
    assert not envelope.is_expired(s_to_ns(1.7))
    assert envelope.is_expired(s_to_ns(1.9))


def test_action_chunk_must_not_be_empty():
    with pytest.raises(ValidationError):
        ActionChunk(actions=())


def test_control_command_reports_decision_age():
    command = ControlCommand(
        t_sim_ns=s_to_ns(2.0),
        velocity=Vec3(x=1.0, y=0.0, z=0.0),
        source_t_sim_ns=s_to_ns(1.2),
    )
    assert command.decision_age_ns(s_to_ns(2.0)) == s_to_ns(0.8)
    assert ControlCommand(t_sim_ns=0, velocity=Vec3(x=0.0, y=0.0, z=0.0)).decision_age_ns(5) is None


def test_episode_event_requires_both_clocks():
    event = EpisodeEvent(
        episode_id="e",
        seq=0,
        component="test",
        event_type=EventType.CONTROL,
        t_sim_ns=1,
        t_wall_ns=2,
    )
    row = event.flat_row()
    assert row["t_sim_ns"] == 1 and row["t_wall_ns"] == 2
    with pytest.raises(ValidationError):
        EpisodeEvent(episode_id="e", seq=0, component="c", event_type=EventType.CONTROL, t_sim_ns=1)


def test_mission_spec_defaults_are_conservative():
    mission = MissionSpec(mission_id="m", instruction="go", task_family=TaskFamily.LONG_HORIZON_NAV)
    assert mission.goal_hint is None, "a search regime must not leak the goal by default"
    assert mission.success.require_terminal_stop is True
    assert mission.allowed_skills == ()
