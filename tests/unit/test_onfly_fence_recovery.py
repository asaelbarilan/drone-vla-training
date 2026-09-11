"""Fence liveness without target truth or resuming pre-turn motion."""

import math
from pathlib import Path

from tests.unit.test_router import envelope, make_ctx, make_router
from uavlab.contracts import DecisionKind, Vec3, WaypointGoal, s_to_ns
from uavlab.core.compose import load_architecture
from uavlab.core.config import Authority
from uavlab.plugins.verifier.bounds import SemanticGeometricVerifier


def setup_router(enabled=True):
    router = make_router(Authority.WAYPOINT)
    router.fence_recovery = enabled
    router.verifier = SemanticGeometricVerifier(require_semantic_support=False)
    ctx = make_ctx(position=(55, 0, 3))
    router.verifier.reset(
        ctx.mission.model_copy(
            update={
                "constraints": ctx.mission.constraints.model_copy(update={"geofence_radius_m": 60})
            }
        ),
        1060,
    )
    outward = envelope(DecisionKind.WAYPOINT, WaypointGoal(target=Vec3(x=62, y=0, z=3)))
    return router, ctx, outward


def test_repeated_fence_rejections_trigger_one_inward_turn():
    router, ctx, outward = setup_router()
    for _ in range(2):
        assert not router.accept(outward, ctx).accepted
        assert not router.reorientation_active
    result = router.accept(outward, ctx)
    assert result.verification.code == "geofence"
    assert router.fence_reorientation_active
    assert router.counters.fence_recoveries == 1
    assert abs(router._reorientation.target_yaw_rad) == math.pi
    for _ in range(3):
        assert not router.accept(outward, ctx).accepted
    assert router.counters.fence_recoveries == 1
    ctx.t_sim_ns = s_to_ns(1)
    command, _, _ = router.command_for_tick(ctx)
    assert command.velocity.norm() == 0
    assert 0 < abs(command.yaw_rate_rps) <= 0.4


def test_turn_completion_requires_new_observation():
    router, ctx, outward = setup_router()
    for _ in range(3):
        router.accept(outward, ctx)
    ctx.t_sim_ns = s_to_ns(9)
    ctx.observation = ctx.observation.model_copy(update={"yaw_rad": math.pi})
    command, _, _ = router.command_for_tick(ctx)
    assert command.is_hold
    assert not router.reorientation_active
    assert router.source is None
    assert "fresh observation" in router.accept(outward, ctx).reason
    inward = envelope(
        DecisionKind.WAYPOINT,
        WaypointGoal(target=Vec3(x=50, y=0, z=3)),
        source_t_sim_ns=s_to_ns(9.1),
    )
    ctx.t_sim_ns = s_to_ns(9.1)
    assert router.accept(inward, ctx).accepted


def test_turn_timeout_is_bounded_and_drops_stale_motion():
    router, ctx, outward = setup_router()
    for _ in range(3):
        router.accept(outward, ctx)
    ctx.t_sim_ns = s_to_ns(20)
    router.command_for_tick(ctx)
    assert not router.reorientation_active
    assert router.source is None
    assert not router.accept(outward, ctx).accepted


def test_original_profile_does_not_gain_boundary_recovery():
    router, ctx, outward = setup_router(enabled=False)
    for _ in range(10):
        router.accept(outward, ctx)
    assert not router.reorientation_active
    assert router.counters.fence_recoveries == 0


def test_other_rejection_breaks_fence_streak():
    router, ctx, outward = setup_router()
    router.accept(outward, ctx)
    router.accept(outward, ctx)
    from uavlab.interfaces import VerificationResult

    router._consider_fence_recovery(VerificationResult(accepted=False, reason="obstacle"), ctx)
    router.accept(outward, ctx)
    assert not router.reorientation_active


def test_experiments_are_separate_and_baseline_is_unchanged():
    root = Path("configs")
    baseline = load_architecture("c5_onfly_qwen4_native_dynamics", root)
    arrival = load_architecture("c5_onfly_target_stop_dev", root)
    fence = load_architecture("c5_onfly_fence_dev", root)
    combined = load_architecture("c5_onfly_stop_fence_dev", root)
    assert not baseline.monitor.params.get("target_bound_stop", False)
    assert not baseline.verifier.params.get("fence_recovery", False)
    assert arrival.monitor.params["target_bound_stop"]
    assert not arrival.verifier.params.get("fence_recovery", False)
    assert fence.verifier.params["fence_recovery"]
    assert fence.monitor == baseline.monitor
    assert combined.monitor == arrival.monitor
    assert combined.verifier == fence.verifier


def test_monitor_continue_cannot_cancel_fence_turn():
    import asyncio

    from uavlab.contracts import ProgressLabel, ProgressState
    from uavlab.core.compose import load_environment
    from uavlab.core.config import EpisodeSpec
    from uavlab.core.orchestrator import Orchestrator

    root = Path("configs")
    harness = Orchestrator(
        load_architecture("c5_onfly_fence_dev", root),
        load_environment("grid_nav_onfly_native_dynamics", root),
        EpisodeSpec(episode_id="fence-monitor-test", seed=1060),
    )
    router, ctx, outward = setup_router()
    for _ in range(3):
        router.accept(outward, ctx)

    class Monitor:
        name = "onfly_monitor"

        async def assess(self, ctx):
            return ProgressState(
                label=ProgressLabel.CONTINUE,
                observation_seq=ctx.observation.seq,
                t_sim_ns=ctx.observation.t_sim_ns,
                recovery_anchor_valid=True,
            )

    harness.router = router
    harness.monitor = Monitor()
    harness._ctx = lambda: ctx
    asyncio.run(harness._run_supervision("monitor", False))
    assert router.fence_reorientation_active
