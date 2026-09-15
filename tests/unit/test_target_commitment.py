"""A bounded execution lease never invents fresh visual target evidence."""

import asyncio

import pytest

from tests.unit.test_onfly import StubModel, context, services
from tests.unit.test_router import MISSION, envelope, make_ctx
from uavlab.contracts import DecisionKind, Trajectory, Vec3, WaypointGoal, s_to_ns
from uavlab.core.compose import load_architecture
from uavlab.core.decision_router import DecisionRouter
from uavlab.core.services import bind
from uavlab.interfaces import RoutingFeedback, VerificationResult
from uavlab.plugins.control.mock import MockVelocityController
from uavlab.plugins.planning.local import FixedLocalPlanner
from uavlab.plugins.reasoning.onfly import OnFlyDecisionAgent


class Verifier:
    accepted = True

    def verify(self, envelope, ctx):
        return VerificationResult(accepted=self.accepted, reason="fixture geometry")


def setup():
    arch = load_architecture("c5_target_commitment_qwen4_dev")
    planner = FixedLocalPlanner()
    planner.reset(MISSION, 0)
    controller = MockVelocityController()
    controller.reset(MISSION, 0)
    router = DecisionRouter(
        arch, verifier=Verifier(), planner=planner, controller=controller, shield=None
    )
    router.reset(MISSION, 0)
    return router


def proposal(kind="target", t=0, x=10, identity="target-original"):
    e = envelope(
        DecisionKind.WAYPOINT,
        WaypointGoal(
            target=Vec3(x=x, y=0, z=3), target_label="target" if kind == "target" else None
        ),
        source_t_sim_ns=s_to_ns(t),
    )
    return e.model_copy(update={"decision_id": identity, "provenance": {"waypoint_kind": kind}})


def armed():
    r = setup()
    assert r.accept(proposal(), make_ctx()).accepted
    out = r.accept(proposal("exploration", 1, 20, "explore"), make_ctx(s_to_ns(1)))
    return r, out


def test_old_goal_replans_without_executing_or_retimestamping_exploration():
    r, out = armed()
    assert not out.accepted and out.reason.startswith("target commitment retained:")
    assert r.source.decision_id == "target-original"
    assert r.source.source_t_sim_ns == 0
    assert out.trajectory.metadata["target_commitment_source_t_ns"] == "0"
    cmd, _, age = r.command_for_tick(make_ctx(s_to_ns(10)))
    assert cmd.velocity.norm() > 0 and age == s_to_ns(10)
    assert cmd.source_decision_id == "target-original"
    assert r.counters.target_commitment_commands == 1
    assert r.counters.stale_commands_executed == 0


def test_repeated_exploration_never_extends_deadline():
    r, _ = armed()
    r.accept(proposal("exploration", 15, 20, "again"), make_ctx(s_to_ns(15)))
    assert r._target_commitment.deadline_ns == s_to_ns(21)
    cmd, _, _ = r.command_for_tick(make_ctx(s_to_ns(21)))
    assert cmd.velocity.norm() == 0 and r.source is None
    assert not r.target_commitment_active(make_ctx(s_to_ns(21)), activate=True)


def test_lost_arbitration_requires_verified_recent_target_and_yields_at_expiry():
    r = setup()
    ctx = make_ctx()
    assert not r.target_commitment_active(ctx, activate=True)
    r.verifier.accepted = False
    assert not r.accept(proposal(), ctx).accepted
    assert not r.target_commitment_active(ctx, activate=True)
    r.verifier.accepted = True
    r.accept(proposal(), ctx)
    assert r.target_commitment_active(make_ctx(s_to_ns(2)), activate=True)
    assert not r.target_commitment_active(make_ctx(s_to_ns(22)), activate=True)


def test_stale_target_cannot_start_lease():
    r = setup()
    r.accept(proposal(), make_ctx())
    assert not r.target_commitment_active(make_ctx(s_to_ns(5)), activate=True)
    cmd, _, _ = r.command_for_tick(make_ctx(s_to_ns(5)))
    assert cmd.velocity.norm() == 0


def test_fresh_verified_target_supersedes_old_lease():
    r, _ = armed()
    assert r.accept(proposal(t=8, x=15, identity="fresh-target"), make_ctx(s_to_ns(8))).accepted
    assert r.source.decision_id == "fresh-target"
    assert r._target_commitment.deadline_ns is None
    assert r._target_commitment.goal.target.x == 15


def test_geometric_failure_ends_lease_and_holds():
    r, _ = armed()
    r.planner.plan = lambda goal, ctx: Trajectory(
        start_t_sim_ns=ctx.t_sim_ns,
        points=(),
        feasible=False,
        reason="blocked",
        planner_name="fixture",
    )
    out = r.accept(proposal("exploration", 2, 20, "blocked"), make_ctx(s_to_ns(2)))
    assert not out.accepted and "ended" in out.reason
    assert r.source is None and r._target_commitment is None


@pytest.mark.parametrize("stop", [False, True])
def test_arrival_or_terminal_stop_ends_execution_without_false_mission_success(stop):
    r, _ = armed()
    r.stop_requested = stop
    ctx = make_ctx(s_to_ns(3), position=(0, 0, 3) if stop else (10, 0, 3))
    cmd, _, _ = r.command_for_tick(ctx)
    assert cmd.velocity.norm() == 0 and r._target_commitment is None
    assert r.stop_requested is stop


def test_disabled_profile_preserves_normal_exploration_and_staleness():
    r = setup()
    r.target_commitment_s = 0
    r.accept(proposal(), make_ctx())
    assert r._target_commitment is None
    assert r.accept(proposal("exploration", 1, 20, "explore"), make_ctx(s_to_ns(1))).accepted
    assert r.source.decision_id == "explore"
    assert r.command_for_tick(make_ctx(s_to_ns(6)))[0].velocity.norm() == 0


def test_deferred_proposal_is_not_reported_to_model_as_obstacle_rejection():
    model = StubModel(['{"evidence":"open ground","kind":"exploration","u":500,"v":500}'])
    policy = OnFlyDecisionAgent(grounded_waypoints=True, coordinate_contract="qwen_relative_1000")
    policy.reset(MISSION, 0)
    bind(policy, services(model))
    ctx = context()
    ctx.last_routing_feedback = RoutingFeedback(
        "explore",
        False,
        "target commitment retained: exploratory replacement deferred",
        DecisionKind.WAYPOINT,
        None,
        ctx.t_sim_ns,
    )
    asyncio.run(policy.decide(ctx))
    assert "bounded detour" in model.requests[0].prompt
    assert "flight verifier or planner rejected" not in model.requests[0].prompt


@pytest.mark.parametrize("value", [-1, 21, float("nan"), float("inf")])
def test_commitment_bounds_are_validated(value):
    arch = load_architecture("c5_target_commitment_qwen4_dev")
    arch.policy.params["target_commitment_s"] = value
    with pytest.raises(ValueError, match="target_commitment_s"):
        DecisionRouter(
            arch,
            verifier=Verifier(),
            planner=FixedLocalPlanner(),
            controller=MockVelocityController(),
            shield=None,
        )


def test_rejected_new_target_does_not_overwrite_existing_lease():
    r, _ = armed()
    r.verifier.accepted = False
    assert not r.accept(proposal(t=5, identity="invalid-new"), make_ctx(s_to_ns(5))).accepted
    assert r.source.decision_id == "target-original"
    assert r._target_commitment.deadline_ns == s_to_ns(21)


def test_expired_lease_allows_fresh_exploration_and_cannot_rearm_old_goal():
    r, _ = armed()
    assert r.accept(proposal("exploration", 21, 20, "new"), make_ctx(s_to_ns(21))).accepted
    assert r.source.decision_id == "new"
    assert not r.target_commitment_active(make_ctx(s_to_ns(22)), activate=True)


def test_stale_exploration_cannot_refresh_geometry_or_lease():
    r, _ = armed()
    deadline = r._target_commitment.deadline_ns
    out = r.accept(proposal("exploration", 0, 20, "stale"), make_ctx(s_to_ns(10)))
    assert out.stale and not out.accepted and out.trajectory is None
    assert r._target_commitment.deadline_ns == deadline


def test_existing_recovery_turn_keeps_ownership():
    r = setup()
    r.accept(proposal(), make_ctx())
    r.begin_fixed_reorientation(
        target_yaw_rad=1, t_sim_ns=0, hold_s=0.25, max_duration_s=2, yaw_rate_rps=0.4
    )
    assert not r.target_commitment_active(make_ctx(s_to_ns(1)), activate=True)


def test_reset_clears_target_authorization():
    r, _ = armed()
    r.reset(MISSION, 1)
    assert r._target_commitment is None and r.source is None


def test_orchestrator_records_lost_but_defers_turn_until_lease_expiry():
    from types import SimpleNamespace

    from uavlab.contracts import ProgressLabel, ProgressState
    from uavlab.core.orchestrator import Orchestrator

    r = setup()
    r.accept(proposal(), make_ctx())
    ctx = make_ctx(s_to_ns(1))
    events = []

    class LostMonitor:
        name = "onfly_monitor"
        target_bound_stop = True

        async def assess(self, ctx):
            return ProgressState(
                label=ProgressLabel.LOST, observation_seq=ctx.observation.seq, t_sim_ns=ctx.t_sim_ns
            )

    h = SimpleNamespace(
        router=r,
        monitor=LostMonitor(),
        latest_obs=ctx.observation,
        _ctx=lambda: ctx,
        clock=SimpleNamespace(now_ns=lambda: ctx.t_sim_ns),
        _last_normal_yaw_rad=0.0,
        _onfly_loss_episode_active=False,
        _emit=lambda component, kind, payload: events.append((kind.value, payload)),
    )
    asyncio.run(Orchestrator._run_supervision(h, "monitor", False))
    assert h.last_progress.label is ProgressLabel.LOST
    assert events[-1][1]["target_commitment_deferred_lost"]
    assert not r.reorientation_active
    ctx = make_ctx(s_to_ns(21))
    h.latest_obs = ctx.observation
    asyncio.run(Orchestrator._run_supervision(h, "monitor", False))
    assert r.reorientation_active
    assert any(kind == "recovery_trigger" for kind, payload in events)
