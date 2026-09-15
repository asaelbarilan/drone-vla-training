"""Decision router dispatch, staleness rejection, and the motor-authority rule.

The router is the one place where "raw model output can never reach a
controller" is actually enforced, so it is tested directly rather than only
through episodes.
"""

from __future__ import annotations

import pytest

from uavlab.contracts import (
    ActionChunk,
    ControlCommand,
    DecisionEnvelope,
    DecisionKind,
    Frame,
    KinematicAction,
    MemorySnapshot,
    MissionDirective,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    ProgressLabel,
    SkillCall,
    TaskFamily,
    Trajectory,
    Vec3,
    WaypointGoal,
    s_to_ns,
)
from uavlab.core.config import ActionHorizon, ArchitectureConfig, Authority, ComponentSpec
from uavlab.core.decision_router import DecisionRouter, RouterViolation
from uavlab.core.skills import SkillRuntime, UnknownSkillError
from uavlab.interfaces import DecisionContext
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.planning.local import FixedLocalPlanner

MISSION = MissionSpec(
    mission_id="m",
    instruction="go",
    task_family=TaskFamily.LONG_HORIZON_NAV,
    allowed_skills=("goto", "hover", "stop", "scan"),
)


def make_ctx(t_sim_ns: int = 0, position=(0.0, 0.0, 3.0)) -> DecisionContext:
    obs = ObservationPacket(
        seq=1,
        t_sim_ns=t_sim_ns,
        t_wall_ns=t_sim_ns,
        position=Vec3(x=position[0], y=position[1], z=position[2]),
        velocity=Vec3(x=0.0, y=0.0, z=0.0),
        yaw_rad=0.0,
        frame=Frame.ENU,
        range_rays=tuple([25.0] * 8),
        ray_bearings_rad=tuple(i * 0.785398 - 3.14159 for i in range(8)),
    )
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=1, t_sim_ns=t_sim_ns),
        memory=MemorySnapshot(observation_seq=1, t_sim_ns=t_sim_ns),
        t_sim_ns=t_sim_ns,
        t_wall_ns=t_sim_ns,
        episode_id="test",
    )


def envelope(kind: DecisionKind, payload, source_t_sim_ns: int = 0) -> DecisionEnvelope:
    return DecisionEnvelope(
        decision_id="d1",
        kind=kind,
        payload=payload,
        source_observation_seq=1,
        source_t_sim_ns=source_t_sim_ns,
        produced_t_wall_ns=0,
        produced_t_sim_ns=source_t_sim_ns,
    )


def make_router(authority: Authority, **overrides) -> DecisionRouter:
    base = {
        "id": "t",
        "authority": authority,
        "policy": ComponentSpec(name="vlm_waypoint"),
    }
    if authority is Authority.WAYPOINT:
        base["planner"] = ComponentSpec(name="fixed_local")
    if authority is Authority.DIRECT_VLA:
        base["action_horizon"] = ActionHorizon.SINGLE
        base["policy"] = ComponentSpec(name="mock_vla")
    base.update(overrides)
    arch = ArchitectureConfig(**base)
    controller = MockVelocityController()
    controller.reset(MISSION, 0)
    planner = None
    if arch.planner is not None:
        planner = FixedLocalPlanner()
        planner.reset(MISSION, 0)
    router = DecisionRouter(
        arch,
        verifier=None,
        planner=planner,
        shield=None,
        controller=controller,
        skill_runtime=SkillRuntime(MISSION.allowed_skills),
    )
    router.reset(MISSION, 0)
    return router


# -- dispatch ---------------------------------------------------------------


def test_waypoint_routes_through_the_planner():
    router = make_router(Authority.WAYPOINT)
    outcome = router.accept(
        envelope(DecisionKind.WAYPOINT, WaypointGoal(target=Vec3(x=10.0, y=0.0, z=3.0))),
        make_ctx(),
    )
    assert outcome.accepted
    assert isinstance(outcome.trajectory, Trajectory)
    assert router.active_kind is DecisionKind.WAYPOINT


def test_kinematic_action_bypasses_the_planner():
    router = make_router(Authority.DIRECT_VLA)
    outcome = router.accept(
        envelope(
            DecisionKind.KINEMATIC_ACTION,
            KinematicAction(velocity=Vec3(x=2.0, y=0.0, z=0.0), duration_s=0.5),
        ),
        make_ctx(),
    )
    assert outcome.accepted and outcome.trajectory is None
    command, _, _ = router.command_for_tick(make_ctx())
    assert command.velocity.x == pytest.approx(2.0)


def test_action_chunk_is_consumed_one_step_per_tick():
    router = make_router(
        Authority.DIRECT_VLA,
        action_horizon=ActionHorizon.CHUNK,
        chunk_length=3,
        policy=ComponentSpec(name="chunk_vla"),
    )
    chunk = ActionChunk(
        actions=tuple(
            KinematicAction(velocity=Vec3(x=float(i + 1), y=0.0, z=0.0), duration_s=1.0)
            for i in range(3)
        )
    )
    assert router.accept(envelope(DecisionKind.ACTION_CHUNK, chunk), make_ctx()).accepted
    speeds = [router.command_for_tick(make_ctx(t)).__getitem__(0).velocity.x for t in (0, 1, 2)]
    assert speeds == [pytest.approx(1.0), pytest.approx(2.0), pytest.approx(3.0)]


def test_skill_expands_into_a_subgoal_and_then_a_plan():
    router = make_router(Authority.SKILL, policy=ComponentSpec(name="scripted_skill"),
                         planner=ComponentSpec(name="fixed_local"))
    outcome = router.accept(
        envelope(
            DecisionKind.SKILL,
            SkillCall(skill_name="goto", args={"x": 10.0, "y": 0.0, "z": 3.0}),
        ),
        make_ctx(),
    )
    assert outcome.accepted
    assert outcome.expanded_kind is DecisionKind.WAYPOINT
    assert outcome.trajectory is not None


def test_skill_outside_the_bounded_vocabulary_is_refused():
    router = make_router(Authority.SKILL, policy=ComponentSpec(name="scripted_skill"),
                         planner=ComponentSpec(name="fixed_local"))
    outcome = router.accept(
        envelope(DecisionKind.SKILL, SkillCall(skill_name="fly_to_the_moon")), make_ctx()
    )
    assert not outcome.accepted
    assert "outside the bounded vocabulary" in outcome.reason
    assert router.counters.unknown_skill == 1


def test_skill_runtime_raises_on_unknown_skill():
    with pytest.raises(UnknownSkillError):
        SkillRuntime(("goto",)).expand(SkillCall(skill_name="teleport"), make_ctx())


# -- the motor-authority rule ----------------------------------------------


def test_mission_directive_never_becomes_motion():
    """The single most important safety invariant in the router."""
    router = make_router(Authority.WAYPOINT)
    outcome = router.accept(
        envelope(
            DecisionKind.MISSION_DIRECTIVE,
            MissionDirective(label=ProgressLabel.CONTINUE, subgoal="keep going"),
        ),
        make_ctx(),
    )
    assert outcome.accepted, "a directive is recorded..."
    assert outcome.directive is not None
    assert router.active_kind is None, "...but it must not become the motion source"
    command, _, _ = router.command_for_tick(make_ctx())
    assert command.is_hold


def test_stop_directive_requests_termination_without_commanding_motion():
    router = make_router(Authority.WAYPOINT)
    router.accept(
        envelope(DecisionKind.MISSION_DIRECTIVE, MissionDirective(label=ProgressLabel.STOP)),
        make_ctx(),
    )
    assert router.stop_requested is True
    assert router.command_for_tick(make_ctx())[0].is_hold


def test_waypoint_without_a_planner_is_a_router_violation():
    """The grammar should have caught this; the router refuses as a backstop."""
    # The grammar refuses to build this directly, so construct the declared
    # ablation and then strip the declaration, simulating a config that reached
    # the runtime without validation.
    arch = ArchitectureConfig(
        id="t",
        authority=Authority.WAYPOINT,
        policy=ComponentSpec(name="vlm_waypoint"),
        planner=None,
        unsafe_ablation=True,
    ).model_copy(update={"unsafe_ablation": False})
    controller = MockVelocityController()
    controller.reset(MISSION, 0)
    router = DecisionRouter(
        arch, verifier=None, planner=None, shield=None, controller=controller
    )
    router.reset(MISSION, 0)
    with pytest.raises(RouterViolation, match="grammar should have rejected"):
        router.accept(
            envelope(DecisionKind.WAYPOINT, WaypointGoal(target=Vec3(x=5.0, y=0.0, z=3.0))),
            make_ctx(),
        )


# -- staleness --------------------------------------------------------------


def test_stale_decisions_are_rejected_at_the_configured_bound():
    router = make_router(Authority.WAYPOINT)
    router.max_age_ns = s_to_ns(1.0)
    stale = envelope(
        DecisionKind.WAYPOINT,
        WaypointGoal(target=Vec3(x=10.0, y=0.0, z=3.0)),
        source_t_sim_ns=0,
    )
    outcome = router.accept(stale, make_ctx(t_sim_ns=s_to_ns(1.5)))
    assert not outcome.accepted
    assert outcome.stale and "stale" in outcome.reason
    assert router.counters.rejected_stale == 1


def test_staleness_can_be_measured_instead_of_rejected():
    """An ablation that measures what staleness costs rather than hiding it."""
    router = make_router(Authority.WAYPOINT)
    router.max_age_ns = s_to_ns(1.0)
    router.reject_stale = False
    outcome = router.accept(
        envelope(
            DecisionKind.WAYPOINT,
            WaypointGoal(target=Vec3(x=10.0, y=0.0, z=3.0)),
            source_t_sim_ns=0,
        ),
        make_ctx(t_sim_ns=s_to_ns(1.5)),
    )
    assert outcome.accepted and outcome.stale
    assert router.counters.rejected_stale == 0


def test_motion_source_is_rejected_when_it_becomes_stale_during_execution():
    """A fresh proposal must not grant indefinite trajectory authority."""
    router = make_router(Authority.WAYPOINT)
    router.max_age_ns = s_to_ns(1.0)
    accepted = router.accept(
        envelope(
            DecisionKind.WAYPOINT,
            WaypointGoal(target=Vec3(x=10.0, y=0.0, z=3.0)),
            source_t_sim_ns=0,
        ),
        make_ctx(),
    )
    assert accepted.accepted

    command, _, age = router.command_for_tick(make_ctx(t_sim_ns=s_to_ns(1.5)))

    assert age == s_to_ns(1.5)
    assert command.source_decision_id is None
    assert command.velocity == Vec3(x=0.0, y=0.0, z=0.0)
    assert router.source is None
    assert router.counters.stale_commands_rejected == 1
    assert router.counters.stale_commands_executed == 0


def test_stale_motion_source_executes_only_in_declared_measurement_ablation():
    router = make_router(Authority.WAYPOINT)
    router.max_age_ns = s_to_ns(1.0)
    router.reject_stale = False
    router.accept(
        envelope(
            DecisionKind.WAYPOINT,
            WaypointGoal(target=Vec3(x=10.0, y=0.0, z=3.0)),
            source_t_sim_ns=0,
        ),
        make_ctx(),
    )

    command, _, age = router.command_for_tick(make_ctx(t_sim_ns=s_to_ns(1.5)))

    assert age == s_to_ns(1.5)
    assert command.source_decision_id == "d1"
    assert router.counters.stale_commands_executed == 1
    assert router.counters.stale_commands_rejected == 0


def test_fixed_lost_reorientation_holds_then_yaws_without_translation():
    router = make_router(Authority.WAYPOINT)
    router.begin_fixed_reorientation(
        target_yaw_rad=1.0,
        t_sim_ns=0,
        hold_s=0.25,
        max_duration_s=2.0,
        yaw_rate_rps=0.8,
    )

    held, _, held_age = router.command_for_tick(make_ctx(t_sim_ns=s_to_ns(0.1)))
    turning, _, turning_age = router.command_for_tick(make_ctx(t_sim_ns=s_to_ns(0.3)))
    finished, _, _ = router.command_for_tick(make_ctx(t_sim_ns=s_to_ns(2.1)))

    assert held.is_hold and held.metadata["recovery"] == "lost_hold"
    assert held_age is None
    assert turning.velocity == Vec3(x=0.0, y=0.0, z=0.0)
    assert turning.yaw_rate_rps > 0.0
    assert turning.source_decision_id == "onfly-lost-reorientation"
    assert turning_age is None
    assert finished.is_hold
    assert not router.reorientation_active


def test_recovered_viewpoint_holds_only_until_bounded_recovery_deadline():
    router = make_router(Authority.WAYPOINT)
    router.begin_fixed_reorientation(
        target_yaw_rad=1.0,
        t_sim_ns=0,
        hold_s=0.25,
        max_duration_s=2.0,
        yaw_rate_rps=0.8,
    )
    settled_ctx = make_ctx(t_sim_ns=s_to_ns(1.0))
    settled_ctx.observation = settled_ctx.observation.model_copy(
        update={"yaw_rad": 1.0}
    )

    settled, _, _ = router.command_for_tick(settled_ctx)
    later_ctx = make_ctx(t_sim_ns=s_to_ns(3.0))
    later_ctx.observation = later_ctx.observation.model_copy(update={"yaw_rad": 1.0})
    expired, _, _ = router.command_for_tick(later_ctx)

    assert settled.is_hold
    assert settled.metadata["recovery"] == "awaiting_reacquisition"
    assert expired.is_hold
    assert expired.metadata["recovery"] == "reorientation_expired"
    assert not router.reorientation_active


def test_self_declared_expiry_is_honoured():
    router = make_router(Authority.WAYPOINT)
    expiring = envelope(
        DecisionKind.WAYPOINT, WaypointGoal(target=Vec3(x=10.0, y=0.0, z=3.0))
    ).model_copy(update={"valid_until_t_sim_ns": s_to_ns(0.5)})
    assert not router.accept(expiring, make_ctx(t_sim_ns=s_to_ns(0.6))).accepted


def test_every_command_carries_its_source_observation_time():
    """Acceptance criterion: every executed decision exposes its source time."""
    router = make_router(Authority.WAYPOINT)
    router.accept(
        envelope(DecisionKind.WAYPOINT, WaypointGoal(target=Vec3(x=10.0, y=0.0, z=3.0))),
        make_ctx(),
    )
    command, _, age = router.command_for_tick(make_ctx(t_sim_ns=s_to_ns(0.4)))
    assert isinstance(command, ControlCommand)
    assert command.source_decision_id == "d1"
    assert command.source_observation_seq == 1
    assert command.source_t_sim_ns == 0
    assert age == s_to_ns(0.4)


def test_a_new_chunk_supersedes_the_previous_one():
    router = make_router(
        Authority.DIRECT_VLA,
        action_horizon=ActionHorizon.CHUNK,
        chunk_length=4,
        policy=ComponentSpec(name="chunk_vla"),
    )
    chunk = ActionChunk(
        actions=tuple(
            KinematicAction(velocity=Vec3(x=1.0, y=0.0, z=0.0), duration_s=1.0) for _ in range(4)
        )
    )
    router.accept(envelope(DecisionKind.ACTION_CHUNK, chunk), make_ctx())
    router.accept(envelope(DecisionKind.ACTION_CHUNK, chunk), make_ctx())
    assert router.counters.chunk_actions_discarded >= 4


@pytest.mark.parametrize("fresh_required", [False, True])
def test_lost_turn_expiry_does_not_resume_or_accept_pre_end_images(fresh_required):
    router = make_router(
        Authority.WAYPOINT,
        semantic_supervision="periodic_monitor",
        scheduler={"monitor_hz": 1.0},
        monitor=ComponentSpec(name="onfly_monitor", params={
            "fresh_after_lost_reorientation": fresh_required,
        }),
    )
    router.begin_fixed_reorientation(
        target_yaw_rad=1.0, t_sim_ns=0, hold_s=0.25,
        max_duration_s=2.0, yaw_rate_rps=0.4,
    )
    waypoint = WaypointGoal(target=Vec3(x=10.0, y=0.0, z=3.0))
    during = envelope(DecisionKind.WAYPOINT, waypoint, s_to_ns(1.0))
    assert router.accept(during, make_ctx(s_to_ns(1.8))).accepted
    expired, _, _ = router.command_for_tick(make_ctx(s_to_ns(2.0)))
    assert expired.is_hold
    next_tick, _, _ = router.command_for_tick(make_ctx(s_to_ns(2.05)))
    assert next_tick.is_hold == fresh_required
    late = envelope(DecisionKind.WAYPOINT, waypoint, s_to_ns(1.9))
    assert router.accept(late, make_ctx(s_to_ns(2.1))).accepted != fresh_required
    fresh = envelope(DecisionKind.WAYPOINT, waypoint, s_to_ns(2.1))
    assert router.accept(fresh, make_ctx(s_to_ns(2.2))).accepted
    resumed, _, _ = router.command_for_tick(make_ctx(s_to_ns(2.25)))
    assert not resumed.is_hold
