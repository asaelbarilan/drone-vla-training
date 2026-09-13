"""Contract tests: every plugin honours the interface it claims.

These run over the *registry*, not over a hand-written list, so a newly added
plugin is covered the moment it registers itself.  That is the point: the
comparison is only fair if every implementation of an interface is genuinely
substitutable, and a plugin that quietly returns something slightly different
would break the fairness silently.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect

import pytest

from uavlab.contracts import (
    ControlCommand,
    DecisionEnvelope,
    EpisodeEvent,
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    ProgressState,
    SafetyDecision,
    TaskFamily,
    Trajectory,
    Vec3,
    WaypointGoal,
)
from uavlab.contracts.env_status import EnvironmentStatus
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import (
    ControllerAdapter,
    DecisionContext,
    EnvironmentAdapter,
    MemoryPlugin,
    MonitorPlugin,
    PerceptionPlugin,
    PlannerPlugin,
    RecoveryPolicy,
    SafetyShield,
    SemanticPolicy,
    VerifierPlugin,
)
from uavlab.plugins.inference.simulated import SimulatedInference

MISSION = MissionSpec(
    mission_id="contract",
    instruction="fly to the target",
    task_family=TaskFamily.LONG_HORIZON_NAV,
    allowed_skills=("goto", "hover", "scan", "stop", "back_off", "ascend", "move", "approach"),
)

ENVIRONMENT_ADAPTERS = ["grid3d", "capability_grid3d"]
"""Adapters that need no external simulator. Live ones are covered separately."""


def services() -> RuntimeServices:
    clock = SimClock()
    inference = SimulatedInference(
        latency_s={key: 0.0 for key in ("perception", "policy", "monitor", "reasoner")}
    )
    svc = RuntimeServices(
        clock=clock,
        log=EventLog("contract", None),
        feature_cache=FeatureCache(),
        inference=inference,
        episode_id="contract",
    )
    bind(inference, svc)
    inference.reset(MISSION, 0)
    return svc


def build(category: str, name: str, svc: RuntimeServices, **params):
    plugin = REGISTRY.build(category, name, params)
    bind(plugin, svc)
    if hasattr(plugin, "reset") and not inspect.iscoroutinefunction(plugin.reset):
        plugin.reset(MISSION, 0)
    return plugin


def make_ctx(obs: ObservationPacket) -> DecisionContext:
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="contract",
    )


def sample_observation() -> ObservationPacket:
    env = REGISTRY.build("environment", "grid3d", {"allow_privileged": True})
    return asyncio.run(env.reset(MISSION, 0))


# -- environment adapters ---------------------------------------------------


@pytest.mark.parametrize("name", ENVIRONMENT_ADAPTERS)
def test_environment_adapter_produces_a_valid_observation(name):
    svc = services()
    env = REGISTRY.build("environment", name, {})
    bind(env, svc)
    assert isinstance(env, EnvironmentAdapter)

    obs = asyncio.run(env.reset(MISSION, 3))
    assert isinstance(obs, ObservationPacket)
    ObservationPacket.model_validate(obs.model_dump())
    assert obs.seq >= 0 and obs.t_sim_ns >= 0
    assert obs.position.frame.value == "enu", "the canonical internal frame is ENU"
    assert len(obs.range_rays) == len(obs.ray_bearings_rad)


@pytest.mark.parametrize("name", ENVIRONMENT_ADAPTERS)
def test_environment_adapter_consumes_the_canonical_control_command(name):
    env = REGISTRY.build("environment", name, {})
    asyncio.run(env.reset(MISSION, 3))
    command = ControlCommand(t_sim_ns=0, velocity=Vec3(x=1.0, y=0.0, z=0.0))
    asyncio.run(env.step(command, 50_000_000))
    status = env.status()
    assert isinstance(status, EnvironmentStatus)
    EnvironmentStatus.model_validate(status.model_dump())


@pytest.mark.parametrize("name", ENVIRONMENT_ADAPTERS)
def test_observation_sequence_is_monotonic(name):
    env = REGISTRY.build("environment", name, {})
    first = asyncio.run(env.reset(MISSION, 1))
    second = asyncio.run(env.observe())
    assert second.seq > first.seq


def test_privileged_channel_is_absent_unless_explicitly_enabled():
    """Only the declared oracle configuration may see ground truth."""
    env = REGISTRY.build("environment", "grid3d", {"allow_privileged": False})
    assert asyncio.run(env.reset(MISSION, 1)).privileged is None
    env = REGISTRY.build("environment", "grid3d", {"allow_privileged": True})
    assert asyncio.run(env.reset(MISSION, 1)).privileged is not None


# -- perception -------------------------------------------------------------


@pytest.mark.parametrize("name", REGISTRY.names("perception"))
def test_perception_returns_a_valid_state(name):
    svc = services()
    plugin = build("perception", name, svc)
    assert isinstance(plugin, PerceptionPlugin)
    state = asyncio.run(plugin.perceive(sample_observation(), MISSION))
    assert isinstance(state, PerceptionState)
    PerceptionState.model_validate(state.model_dump())
    assert 0.0 <= state.uncertainty <= 1.0


# -- memory -----------------------------------------------------------------


@pytest.mark.parametrize("name", REGISTRY.names("memory"))
def test_memory_returns_a_bounded_snapshot(name):
    svc = services()
    plugin = build("memory", name, svc)
    assert isinstance(plugin, MemoryPlugin)
    obs = sample_observation()
    perception = asyncio.run(build("perception", "identity", svc).perceive(obs, MISSION))
    for _ in range(50):
        plugin.update(obs, perception, None)
    snapshot = plugin.snapshot()
    assert isinstance(snapshot, MemorySnapshot)
    MemorySnapshot.model_validate(snapshot.model_dump())
    assert len(snapshot.items) <= 64, "memory must stay bounded under repeated updates"
    if snapshot.token_budget:
        assert snapshot.tokens_used <= snapshot.token_budget * 2


@pytest.mark.parametrize("name", REGISTRY.names("memory"))
def test_memory_reset_restores_a_pristine_plugin(name):
    """Leaked memory across episodes would silently correlate independent seeds.

    The invariant is stronger than "looks empty": a plugin after ``reset()``
    must be indistinguishable from a freshly constructed one. Anything less and
    episode N+1 starts with a trace of episode N.
    """
    svc = services()
    used = build("memory", name, svc)
    obs = sample_observation()
    perception = asyncio.run(build("perception", "identity", svc).perceive(obs, MISSION))
    for _ in range(10):
        used.update(obs, perception, None)
    if name in ("no_memory", "none"):
        # The null hypothesis: it is *supposed* to retain nothing, so the
        # vacuity guard below does not apply to it.
        assert used.snapshot().is_empty
    else:
        assert used.snapshot() != build("memory", name, svc).snapshot(), (
            f"{name} ignored 10 updates, so this test would pass vacuously"
        )

    used.reset(MISSION, 1)
    pristine = build("memory", name, svc)
    assert used.snapshot() == pristine.snapshot(), f"{name} retained state across reset()"


# -- policies ---------------------------------------------------------------


def _policies_requiring_external_inputs() -> set[str]:
    """Policies the blind, cost-only generic sweep cannot execute.

    Read capability flags from each plugin rather than maintaining a name list.
    A vision policy called without pixels and a real-agent policy called on the
    simulated accounting backend should both fail closed; their dedicated
    contract tests supply the required input instead.
    """
    names = set()
    for name in REGISTRY.names("policy"):
        factory = REGISTRY._factories.get(("policy", name))
        if factory is None:
            with contextlib.suppress(Exception):
                REGISTRY.build("policy", name, {})
            factory = REGISTRY._factories.get(("policy", name))
        if getattr(factory, "requires_vision", False) or getattr(
            factory, "requires_real_inference", False
        ):
            names.add(name)
    return names


@pytest.mark.parametrize(
    "name",
    sorted(set(REGISTRY.names("policy")) - _policies_requiring_external_inputs()),
)
def test_policy_returns_a_valid_envelope_of_a_declared_kind(name):
    svc = services()
    plugin = build("policy", name, svc)
    assert isinstance(plugin, SemanticPolicy)
    obs = sample_observation()
    ctx = make_ctx(obs)
    envelope = asyncio.run(plugin.decide(ctx))
    if envelope is None:
        return  # "no decision this tick" is legitimate
    assert isinstance(envelope, DecisionEnvelope)
    DecisionEnvelope.model_validate(envelope.model_dump())
    assert envelope.kind.value in plugin.emits, (
        f"{name} emitted {envelope.kind.value} but declares emits={plugin.emits}"
    )
    assert envelope.source_observation_seq == obs.seq
    assert envelope.source_t_sim_ns == obs.t_sim_ns


@pytest.mark.parametrize("name", REGISTRY.names("policy"))
def test_policy_declares_what_it_emits(name):
    plugin = REGISTRY.build("policy", name, {})
    assert plugin.emits, f"{name} must declare emits so the config grammar can check authority"


# -- verifier, planner, shield, controller ---------------------------------


@pytest.mark.parametrize("name", REGISTRY.names("verifier"))
def test_verifier_returns_a_verification_result(name):
    svc = services()
    plugin = build("verifier", name, svc)
    assert isinstance(plugin, VerifierPlugin)
    obs = sample_observation()
    envelope = asyncio.run(build("policy", "vlm_waypoint", svc).decide(make_ctx(obs)))
    result = plugin.verify(envelope, make_ctx(obs))
    assert isinstance(result.accepted, bool)
    if result.replacement is not None:
        assert result.replacement.kind is envelope.kind, "a repair must not change the kind"


@pytest.mark.parametrize("name", REGISTRY.names("planner"))
def test_planner_returns_a_trajectory(name):
    svc = services()
    plugin = build("planner", name, svc)
    assert isinstance(plugin, PlannerPlugin)
    obs = sample_observation()
    trajectory = plugin.plan(
        WaypointGoal(target=Vec3(x=obs.position.x + 8.0, y=obs.position.y, z=obs.position.z)),
        make_ctx(obs),
    )
    assert isinstance(trajectory, Trajectory)
    Trajectory.model_validate(trajectory.model_dump())
    if trajectory.feasible:
        assert trajectory.points, "a feasible trajectory must contain points"


@pytest.mark.parametrize("name", REGISTRY.names("shield"))
def test_shield_returns_a_command_and_a_decision(name):
    svc = services()
    plugin = build("shield", name, svc)
    assert isinstance(plugin, SafetyShield)
    obs = sample_observation()
    command = ControlCommand(t_sim_ns=0, velocity=Vec3(x=3.0, y=0.0, z=0.0))
    out, decision = plugin.check(command, make_ctx(obs))
    assert isinstance(out, ControlCommand)
    assert isinstance(decision, SafetyDecision)
    SafetyDecision.model_validate(decision.model_dump())


@pytest.mark.parametrize("name", REGISTRY.names("controller"))
def test_controller_produces_the_canonical_command(name):
    from uavlab.contracts import KinematicAction

    svc = services()
    plugin = build("controller", name, svc)
    assert isinstance(plugin, ControllerAdapter)
    obs = sample_observation()
    ctx = make_ctx(obs)
    planner = build("planner", "fixed_local", svc)
    trajectory = planner.plan(
        WaypointGoal(target=Vec3(x=obs.position.x + 8.0, y=obs.position.y, z=obs.position.z)), ctx
    )
    for command in (
        plugin.track(trajectory, ctx),
        plugin.from_action(KinematicAction(velocity=Vec3(x=1.0, y=0.0, z=0.0)), ctx, "d"),
        plugin.hold(ctx),
    ):
        assert isinstance(command, ControlCommand)
        ControlCommand.model_validate(command.model_dump())
        assert command.frame.value == "enu"


# -- monitors and recovery --------------------------------------------------


@pytest.mark.parametrize("name", REGISTRY.names("monitor"))
def test_monitor_returns_a_progress_state(name):
    svc = services()
    if name == "onfly_hover_monitor":
        plugin = REGISTRY.build(
            "monitor",
            name,
            dict(
                current_grounding=True,
                target_bound_stop=True,
                structured_evidence=True,
                arrival_memory_s=4,
            ),
        )
        bind(plugin, svc)
        from uavlab.core.compose import load_environment

        task = load_environment("capability_approach_hover")
        plugin.reset(MISSION.model_copy(update={"instruction": task.instruction}), 1061)
    else:
        plugin = build("monitor", name, svc)
    assert isinstance(plugin, MonitorPlugin)
    state = asyncio.run(plugin.assess(make_ctx(sample_observation())))
    assert isinstance(state, ProgressState)
    ProgressState.model_validate(state.model_dump())


def _recoveries_requiring_external_inputs() -> set[str]:
    """Recovery plugins the cost-only generic contract cannot execute."""
    names = set()
    for name in REGISTRY.names("recovery"):
        factory = REGISTRY._factories.get(("recovery", name))
        if factory is None:
            with contextlib.suppress(Exception):
                REGISTRY.build("recovery", name, {})
            factory = REGISTRY._factories.get(("recovery", name))
        if getattr(factory, "requires_real_inference", False):
            names.add(name)
    return names


@pytest.mark.parametrize(
    "name",
    sorted(set(REGISTRY.names("recovery")) - _recoveries_requiring_external_inputs()),
)
def test_recovery_returns_a_routable_envelope(name):
    from uavlab.contracts import RecoveryRequest, RecoveryTrigger

    svc = services()
    plugin = build("recovery", name, svc)
    assert isinstance(plugin, RecoveryPolicy)
    obs = sample_observation()
    request = RecoveryRequest(
        trigger=RecoveryTrigger(
            name="test", fired_t_sim_ns=0, observation_seq=obs.seq, cause="unit test"
        ),
        state_summary="no progress",
        allowed_skills=MISSION.allowed_skills,
    )
    envelope = asyncio.run(plugin.recover(request, make_ctx(obs)))
    if envelope is None:
        return
    DecisionEnvelope.model_validate(envelope.model_dump())
    assert envelope.provenance.get("trigger"), "recovery must record why it was invoked"


# -- events -----------------------------------------------------------------


def test_every_event_carries_both_clocks():
    log = EventLog("contract", None)
    from uavlab.contracts.events import EventType

    for event_type in EventType:
        event = log.emit("component", event_type, t_sim_ns=5, t_wall_ns=7, payload={"a": 1})
        assert isinstance(event, EpisodeEvent)
        assert event.t_sim_ns == 5 and event.t_wall_ns == 7
    assert len(log) == len(EventType)
    assert [e.seq for e in log.events] == list(range(len(EventType)))


def test_the_runtime_never_reaches_for_a_concrete_environment():
    """The central claim: simulators are adapters.

    If anything in the runtime imports a specific environment or reads its
    internals, then swapping the simulator is a code change and the claim is
    false. This is the test that would fail on contact with AirSim, so it is
    worth failing here first, cheaply.

    Scoped to `core/` and `plugins/` â€” the path an episode actually runs through.
    Tooling is a separate matter and is tracked in TODO.md, because it *does*
    bind to the concrete environment and cannot move to another simulator as
    written.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "uavlab"
    forbidden = ("DeterministicEnv", "adapters.gym", "adapters.project_airsim")
    offenders = []
    for area in ("core", "plugins"):
        for path in sorted((root / area).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                if needle in text:
                    offenders.append(f"{path.relative_to(root)} mentions {needle!r}")
    assert not offenders, (
        "the runtime reaches for a concrete environment, so the simulator is not "
        "an adapter:\n  " + "\n  ".join(offenders)
    )


def test_the_tools_that_do_bind_to_one_environment_are_the_known_ones():
    """Pin the exceptions, so a new one has to be a deliberate act.

    Data collection, DAgger rollouts and video capture all monkeypatch
    `DeterministicEnv.step`. That is defensible â€” they need the frame and the
    command to correspond exactly, which only the environment can guarantee â€”
    but it means none of them runs on another simulator, and that is a
    prerequisite for the AirSim benchmark rather than a detail.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "src" / "uavlab"
    expected = {
        "adapters/dataset_replay/replay.py",  # subclasses it on purpose
        "analysis/replay_video.py",
        "analysis/flight_debugger.py",  # D-94 offline grid3d inspection
        "analysis/replay_run.py",  # re-flies a stored run's commands
        "training/dataset.py",
        "training/dagger.py",
        "training/qwen_vla_dataset.py",
    }
    found = {
        str(p.relative_to(root)).replace("\\", "/")
        for p in root.rglob("*.py")
        if "DeterministicEnv" in p.read_text(encoding="utf-8")
        and not str(p.relative_to(root)).replace("\\", "/").startswith("adapters/gym/")
    }
    assert found == expected, (
        f"the set of modules bound to one environment changed.\n"
        f"  added:   {sorted(found - expected)}\n"
        f"  removed: {sorted(expected - found)}\n"
        "Adding one is a decision about simulator portability -- record it in "
        "docs/RESEARCH_LOG.md and update this test."
    )
