"""The acceptance criteria, as executable tests.

These are the claims that make the testbed worth building.  If any of them
stops holding, architectures have stopped being configuration and the
comparison has stopped being fair — so each is asserted rather than asserted
about in prose.
"""

from __future__ import annotations

import asyncio

import pytest

from uavlab.contracts import ControlCommand, EventType, TerminationReason
from uavlab.core.config import ActionHorizon, Authority, EpisodeSpec, SchedulerKind
from uavlab.core.orchestrator import Orchestrator

from tests.conftest import run_one


# -- 1. changing architecture is a YAML edit, not a code change -------------


def test_c2_to_c7_differ_only_in_configuration(arch_factory):
    """Waypoint authority to direct learned action, with no code path change."""
    c2, c7 = arch_factory("c2"), arch_factory("c7")
    assert c2.authority is Authority.WAYPOINT
    assert c7.authority is Authority.DIRECT_VLA
    assert c7.action_horizon is ActionHorizon.SINGLE
    assert c2.planner is not None and c7.planner is None
    # Both are the same Python type; only their data differs.
    assert type(c2) is type(c7)
    assert c2.config_hash() != c7.config_hash()


def test_every_sentinel_architecture_is_a_distinct_configuration(arch_factory):
    from tests.conftest import SENTINEL_ARCHITECTURES

    hashes = {name: arch_factory(name).config_hash() for name in SENTINEL_ARCHITECTURES}
    assert len(set(hashes.values())) == len(hashes), f"duplicate configurations: {hashes}"


# -- 2. one policy graph, multiple environment adapters ---------------------


def test_the_same_architecture_runs_on_two_environment_adapters(arch_factory, env_factory, tmp_path):
    """Acceptance criterion: the C2 policy graph runs on multiple adapters."""
    import json

    from uavlab.adapters.dataset_replay.replay import write_scene
    from uavlab.core.config import ComponentSpec, EnvironmentConfig
    from uavlab.core.registry import REGISTRY

    arch = arch_factory("c2")
    grid_env = env_factory("grid_nav")

    # Freeze the procedurally generated scene into a replayable file.
    generator = REGISTRY.build("environment", "grid3d", dict(grid_env.params))
    from uavlab.contracts import MissionSpec, TaskFamily

    mission = MissionSpec(
        mission_id="m", instruction="go", task_family=TaskFamily.LONG_HORIZON_NAV
    )
    asyncio.run(generator.reset(mission, 4))
    scene_path = write_scene(generator, tmp_path / "scene.json")
    assert json.loads(scene_path.read_text())["goal"]

    replay_params = dict(grid_env.params)
    replay_params["scene_path"] = str(scene_path)
    replay_env = EnvironmentConfig(
        id="scene_replay_env",
        adapter=ComponentSpec(name="scene_replay", params={"scene_path": str(scene_path)}),
        task_family=grid_env.task_family,
        instruction=grid_env.instruction,
        max_episode_s=30.0,
        params=replay_params,
    )

    grid_result, _ = run_one(arch, grid_env.model_copy(update={"max_episode_s": 30.0}), seed=4)
    replay_result, _ = run_one(arch, replay_env, seed=4)

    # The same architecture ran on both without any change to the architecture.
    assert grid_result.error is None and replay_result.error is None
    assert grid_result.config_hash == replay_result.config_hash
    assert replay_result.metrics["control_updates"] > 0


# -- 3. every executed decision exposes its source observation time ---------


def test_every_control_event_reports_its_decision_age(arch_factory, env_factory):
    arch = arch_factory("c2")
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 20.0})
    _, orchestrator = run_one(arch, env, seed=2)

    controls = orchestrator.log.of_type(EventType.CONTROL)
    assert controls, "an episode must produce control events"
    with_source = [e for e in controls if e.payload.get("source_observation_seq") is not None]
    assert with_source, "no control command carried its source observation"
    for event in with_source:
        assert event.payload["decision_age_s"] is not None
        assert event.payload["decision_age_s"] >= 0.0


# -- 4. asynchronous means genuinely concurrent -----------------------------


def test_c5_runs_decision_and_monitor_as_independent_loops(arch_factory, env_factory):
    """Acceptance criterion: C5 truly runs decision and monitor asynchronously."""
    arch = arch_factory("c5")
    assert arch.scheduler.kind is SchedulerKind.ASYNC_MULTI_RATE
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 30.0})
    _, orchestrator = run_one(arch, env, seed=2)

    decisions = orchestrator.log.of_type(EventType.DECISION_PROPOSED)
    monitors = orchestrator.log.of_type(EventType.MONITOR)
    assert decisions and monitors, "both loops must produce events"

    # Independent rates: the monitor is configured far slower than the policy.
    assert len(monitors) < len(decisions), (
        f"monitor produced {len(monitors)} assessments against {len(decisions)} decisions; "
        "these should not be running at the same rate"
    )
    # Interleaved in simulated time, i.e. neither loop waits for the other.
    monitor_times = [e.t_sim_ns for e in monitors]
    decision_times = [e.t_sim_ns for e in decisions]
    interleaved = [
        m for m in monitor_times if min(decision_times) < m < max(decision_times)
    ]
    assert interleaved, "monitor events never fell between decision events"
    assert not set(monitor_times) & set(decision_times) or len(interleaved) > 1


def test_monitor_events_report_non_blocking_execution(arch_factory, env_factory):
    arch = arch_factory("c5")
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 20.0})
    _, orchestrator = run_one(arch, env, seed=2)
    monitors = orchestrator.log.of_type(EventType.MONITOR)
    assert all(e.payload["blocking"] is False for e in monitors), (
        "an async_multi_rate architecture must not run its monitor inline"
    )


def test_c10_runs_its_reasoner_inline_unlike_c12(arch_factory, env_factory):
    """The C10 vs C12 contrast must be structural, not a rate difference."""
    c10, c12 = arch_factory("c10"), arch_factory("c12")
    assert c10.scheduler.kind is SchedulerKind.PERIODIC
    assert c12.scheduler.kind is SchedulerKind.ASYNC_MULTI_RATE
    assert c10.scheduler.reasoner_hz == c12.scheduler.reasoner_hz
    assert c10.scheduler.decision_hz == c12.scheduler.decision_hz
    assert c10.recovery == c12.recovery, "the reasoner itself must be identical"

    from uavlab.core.clock import SimClock
    from uavlab.core.scheduler import Scheduler

    inline_10 = [
        s.role for s in Scheduler(c10.scheduler, SimClock()).build(has_monitor=False, has_recovery=True)
        if not s.concurrent
    ]
    inline_12 = [
        s.role for s in Scheduler(c12.scheduler, SimClock()).build(has_monitor=False, has_recovery=True)
        if not s.concurrent
    ]
    assert inline_10 == ["reasoner"], "C10's reasoner must block the decision loop"
    assert inline_12 == [], "C12's reasoner must run concurrently"


# -- 5. event-triggered reasoning is genuinely absent until admitted --------


def test_c6_makes_no_reasoner_calls_when_the_trigger_never_fires(arch_factory, env_factory):
    """Acceptance criterion: C6 invokes recovery only after configured triggers."""
    arch = arch_factory("c6")
    never = arch.model_copy(
        update={"scheduler": arch.scheduler.model_copy(update={"trigger": "never"})}
    )
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 30.0})
    result, orchestrator = run_one(never, env, seed=2)

    assert orchestrator.log.count(EventType.RECOVERY_TRIGGER) == 0
    assert orchestrator.log.count(EventType.RECOVERY_DECISION) == 0
    assert result.metrics.get("reasoner_calls", 0.0) == 0.0, (
        "an event-triggered architecture must cost nothing while nothing is wrong"
    )


def test_c6_invokes_recovery_once_the_trigger_fires(arch_factory, env_factory):
    arch = arch_factory("c6")
    always = arch.model_copy(
        update={
            "scheduler": arch.scheduler.model_copy(
                update={"trigger": "always", "cooldown_s": 1.0, "max_calls": 3}
            )
        }
    )
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 30.0})
    result, orchestrator = run_one(always, env, seed=2)

    assert orchestrator.log.count(EventType.RECOVERY_TRIGGER) > 0
    assert result.metrics["reasoner_calls"] > 0.0


def test_the_call_budget_is_enforced(arch_factory, env_factory):
    """"Selective invocation" is only a claim if the budget actually binds."""
    arch = arch_factory("c6")
    budgeted = arch.model_copy(
        update={
            "scheduler": arch.scheduler.model_copy(
                update={"trigger": "always", "cooldown_s": 0.0, "max_calls": 2}
            )
        }
    )
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 40.0})
    _, orchestrator = run_one(budgeted, env, seed=2)
    assert orchestrator.log.count(EventType.RECOVERY_TRIGGER) <= 2
    assert orchestrator.scheduler.gate is not None
    assert orchestrator.scheduler.gate.suppressed > 0, "suppressed calls must be recorded"


# -- 6. C7 and C8 isolate the safety boundary -------------------------------


def test_c7_and_c8_use_an_identical_policy(arch_factory):
    """Acceptance criterion: C7 and C8 isolate the shield with identical VLA output."""
    c7, c8 = arch_factory("c7"), arch_factory("c8")
    assert c7.policy == c8.policy, "the VLA plugin and its parameters must be identical"
    assert c7.inference == c8.inference, "identical compute cost, or it is a latency contrast too"
    assert c7.scheduler == c8.scheduler
    assert c7.memory == c8.memory
    assert c7.shield is None and c8.shield is not None
    # The shield is the only difference.
    d7 = c7.model_dump()
    d8 = c8.model_dump()
    differing = {k for k in d7 if d7[k] != d8[k]}
    # `ablation_of` is bookkeeping about the comparison, not part of it: C7 is
    # declared an ablation of C8 and C8 is the family base, so the field differs
    # by construction while the architectures still differ only in the shield.
    assert differing <= {"id", "name", "description", "shield", "tags", "ablation_of"}, (
        f"C7 and C8 differ in more than the shield: {differing}"
    )


def test_shield_blocks_an_action_aimed_at_an_obstacle():
    """Acceptance criterion: the shield blocks an injected collision action."""
    import math

    from uavlab.contracts import (
        Frame,
        MemorySnapshot,
        MissionSpec,
        ObservationPacket,
        PerceptionState,
        SafetyVerdict,
        TaskFamily,
        Vec3,
    )
    from uavlab.interfaces import DecisionContext
    from uavlab.plugins.shield.collision import SimpleCollisionShield

    mission = MissionSpec(
        mission_id="m", instruction="go", task_family=TaskFamily.LONG_HORIZON_NAV
    )
    shield = SimpleCollisionShield()
    shield.reset(mission, 0)

    bearings = tuple(i * (2 * math.pi / 8) - math.pi for i in range(8))
    # A wall directly ahead (body bearing 0) at 0.5 m, everything else clear.
    rays = tuple(0.5 if abs(b) < 1e-6 else 25.0 for b in bearings)
    obs = ObservationPacket(
        seq=1,
        t_sim_ns=0,
        t_wall_ns=0,
        position=Vec3(x=0.0, y=0.0, z=3.0),
        velocity=Vec3(x=0.0, y=0.0, z=0.0),
        yaw_rad=0.0,
        frame=Frame.ENU,
        range_rays=rays,
        ray_bearings_rad=bearings,
    )
    ctx = DecisionContext(
        mission=mission,
        observation=obs,
        perception=PerceptionState(observation_seq=1, t_sim_ns=0),
        memory=MemorySnapshot(observation_seq=1, t_sim_ns=0),
        t_sim_ns=0,
        t_wall_ns=0,
        episode_id="t",
    )

    suicidal = ControlCommand(t_sim_ns=0, velocity=Vec3(x=4.0, y=0.0, z=0.0))
    out, decision = shield.check(suicidal, ctx)
    assert decision.verdict is SafetyVerdict.REJECT
    assert out.velocity.norm() == pytest.approx(0.0)
    assert out.safety_modified is True


# -- 7. illegal architectures fail before launch ----------------------------


def test_an_illegal_architecture_cannot_be_launched(arch_factory, env_factory):
    from uavlab.core.config import ConfigError

    arch = arch_factory("c7")
    with pytest.raises(ConfigError):
        # A skill agent with a learned-action horizon is not an architecture.
        arch.model_validate({**arch.model_dump(), "authority": "skill"})


def test_a_policy_that_exceeds_its_authority_is_refused(arch_factory, env_factory):
    """A config may name a valid plugin that cannot exercise the declared authority."""
    from uavlab.core.clock import HarnessError
    from uavlab.core.config import ComponentSpec

    arch = arch_factory("c2").model_copy(update={"policy": ComponentSpec(name="mock_vla")})
    env = env_factory("grid_nav")
    orchestrator = Orchestrator(arch, env, EpisodeSpec(episode_id="bad", seed=1))
    with pytest.raises(HarnessError, match="does not permit"):
        asyncio.run(orchestrator.run())


# -- 8. raw model text can never reach a flight-control API -----------------


def test_control_command_has_no_free_form_text_field():
    """Structural guard: adding a free-text field to ControlCommand fails here.

    The DecisionEnvelope carries provenance and rationale; the ControlCommand
    carries none of it. Keeping that boundary is what makes "no free-form model
    output reaches the controller" a property of the type rather than a habit.
    """
    fields = set(ControlCommand.model_fields)
    assert fields == {
        "t_sim_ns",
        "velocity",
        "yaw_rate_rps",
        "frame",
        "expires_t_sim_ns",
        "source_decision_id",
        "source_observation_seq",
        "source_t_sim_ns",
        "safety_modified",
        "metadata",
    }, "ControlCommand gained or lost a field; check nothing free-form was added"


def test_policy_rationale_never_appears_in_a_control_event(arch_factory, env_factory):
    arch = arch_factory("c2")
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 20.0})
    _, orchestrator = run_one(arch, env, seed=2)
    allowed = {
        "position_x", "position_y", "position_z",
        "vx", "vy", "vz", "yaw_rate", "decision_age_s", "safety_modified",
        "source_observation_seq",
    }
    for event in orchestrator.log.of_type(EventType.CONTROL):
        assert set(event.payload) <= allowed, (
            f"unexpected key in a control event: {set(event.payload) - allowed}"
        )


# -- 9. determinism ---------------------------------------------------------


@pytest.mark.parametrize("arch_name", ["c2", "c7", "c12"])
def test_runs_are_deterministic_for_a_fixed_seed(arch_factory, env_factory, arch_name):
    """Without this, no paired comparison in the study means anything."""
    arch = arch_factory(arch_name)
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 25.0})
    first, _ = run_one(arch, env, seed=9)
    second, _ = run_one(arch, env, seed=9)

    assert first.success == second.success
    assert first.termination_reason == second.termination_reason
    assert first.sim_duration_s == pytest.approx(second.sim_duration_s)
    for metric in ("distance_to_goal_m", "path_length_m", "collisions", "decisions_proposed"):
        assert first.metrics[metric] == pytest.approx(second.metrics[metric]), (
            f"{metric} differed between two runs of the same seed"
        )


def test_different_seeds_produce_different_scenes(arch_factory, env_factory):
    """Guard against a seed that is silently ignored."""
    arch = arch_factory("c0")
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 25.0})
    a, _ = run_one(arch, env, seed=1)
    b, _ = run_one(arch, env, seed=2)
    assert a.metrics["path_length_m"] != pytest.approx(b.metrics["path_length_m"])


# -- 10. the control ceiling is competent -----------------------------------


def test_the_oracle_control_ceiling_reaches_the_goal(arch_factory, env_factory):
    """C0's falsification criterion, run as a test.

    If the oracle cannot fly the mission, nothing measured about foundation-model
    architecture in this environment is interpretable yet - the planner,
    controller or environment must be fixed first.
    """
    arch = arch_factory("c0")
    env = env_factory("grid_nav")
    successes = 0
    for seed in (1, 2, 3, 4, 5):
        result, _ = run_one(arch, env, seed=seed)
        successes += int(result.success)
    assert successes >= 4, (
        f"the oracle control ceiling reached the goal in only {successes}/5 episodes; "
        "fix the flight stack before drawing architecture conclusions"
    )


def test_the_oracle_beats_a_semantics_free_baseline(arch_factory, env_factory):
    """Sanity: the environment must actually require semantics."""
    from uavlab.core.config import ComponentSpec

    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 40.0})
    oracle = arch_factory("c0")
    random_arch = oracle.model_copy(
        update={
            "id": "random",
            "policy": ComponentSpec(name="random_waypoint"),
            "allow_privileged_observations": False,
        }
    )
    oracle_hits = sum(run_one(oracle, env, seed=s)[0].success for s in (1, 2, 3))
    random_hits = sum(run_one(random_arch, env, seed=s)[0].success for s in (1, 2, 3))
    assert oracle_hits > random_hits, (
        "a random-waypoint policy did as well as the oracle; the task is not "
        "measuring semantic competence"
    )


def test_an_episode_always_terminates_with_a_reason(arch_factory, env_factory):
    from tests.conftest import ALL_ARCHITECTURES

    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 15.0})
    for name in ALL_ARCHITECTURES:
        result, _ = run_one(arch_factory(name), env, seed=1)
        assert isinstance(result.termination_reason, TerminationReason)
        assert result.error is None, f"{name} raised: {result.error}"
