"""Plugin protocols.

These twelve interfaces are the entire extension surface of the testbed.  A new
architecture is a new *combination* of implementations, selected by YAML; a new
model is a new implementation of one interface.  Neither is a code fork.

Every interface takes a :class:`DecisionContext` rather than a long positional
signature, so that adding a field (say, a new perception channel) does not
force every existing plugin to change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from uavlab.contracts import (
    AdmissionDecision,
    AdmissionRuntime,
    ControlCommand,
    DecisionEnvelope,
    KinematicAction,
    MemorySnapshot,
    MissionDirective,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    ProgressState,
    RecoveryRequest,
    SafetyDecision,
    Trajectory,
    Vec3,
    WaypointGoal,
)
from uavlab.contracts.common import DecisionKind
from uavlab.contracts.env_status import EnvironmentStatus


@dataclass(frozen=True, slots=True)
class RoutingFeedback:
    """What the common runtime did with the previous semantic proposal.

    This is deliberately narrower than :class:`RoutingOutcome`: semantic
    components may learn that their proposal was accepted, repaired or rejected,
    but they do not receive the planner's private trajectory or simulator truth.
    Closed-loop skill agents need this observation to adapt after an invalid
    call; without it they are open-loop text generators despite running in a
    loop.
    """

    decision_id: str
    accepted: bool
    reason: str
    proposed_kind: DecisionKind
    expanded_kind: DecisionKind | None
    t_sim_ns: int


@dataclass(frozen=True, slots=True)
class SemanticCompletionEvidence:
    """Sensor-originated semantic evidence carried through one hard skill.

    A blocking ``fly_to`` may take longer than a short recency window. The
    runtime therefore records that an evidence-supported semantic target was
    selected and that the corresponding hard skill later completed. This is
    skill-result memory, not environment success truth.
    """

    label: str
    position: Vec3
    observed_t_sim_ns: int
    completed_t_sim_ns: int
    source_decision_id: str


@dataclass(slots=True)
class DecisionContext:
    """Everything a semantic component is allowed to see at decision time.

    Deliberately *not* a god object: it carries the mission, the current
    observation and the outputs of perception and memory, plus the last
    supervisory verdict.  It does not carry the environment, the simulator, or
    any other plugin, so no plugin can reach around the contracts.
    """

    mission: MissionSpec
    observation: ObservationPacket
    perception: PerceptionState
    memory: MemorySnapshot
    t_sim_ns: int
    t_wall_ns: int
    episode_id: str
    last_progress: ProgressState | None = None
    last_decision: DecisionEnvelope | None = None
    last_directive: MissionDirective | None = None
    """The most recent supervisory directive.

    This is the only channel by which a slow reasoner influences a fast
    executor, and it carries intent — a subgoal or a target hint — never motion.
    A hierarchical architecture is exactly this field being read; a flat one is
    exactly this field being ``None``.
    """
    last_routing_feedback: RoutingFeedback | None = None
    """Validated execution feedback for the preceding proposal, never truth."""
    scratch: dict[str, object] = field(default_factory=dict)
    """Per-episode scratch space for a plugin's own state. Cleared on reset."""


@dataclass(slots=True)
class VerificationResult:
    """Outcome of semantic/geometric validation of a proposal."""

    accepted: bool
    reason: str = ""
    replacement: DecisionEnvelope | None = None
    """A repaired proposal, when the verifier can fix rather than veto."""

    @property
    def modified(self) -> bool:
        return self.replacement is not None


@dataclass(slots=True)
class InferenceRequest:
    """One call into a (real or simulated) foundation model."""

    model_id: str
    role: str
    """"policy", "monitor", "reasoner" — attributes cost to an architectural role."""
    prompt_hash: str
    input_tokens: int = 0
    image_count: int = 0
    observation_seq: int = -1

    prompt: str = ""
    """The actual prompt. Empty for simulated backends, which only need the cost."""
    images: tuple[str, ...] = ()
    """Base64-encoded frames. Kept out of ``prompt_hash`` so the hash stays a
    cheap identifier for the *template*, which is what belongs in a manifest."""
    response_schema: dict[str, object] | None = None
    """Optional JSON schema requested from a backend that supports constrained output."""


@dataclass(slots=True)
class InferenceResult:
    """Result plus the accounting the compute metrics need."""

    payload: object
    output_tokens: int = 0
    latency_ns: int = 0
    cache_hit: bool = False


class Plugin(Protocol):
    """Common lifecycle. ``reset`` must clear all per-episode state."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...


@runtime_checkable
class EnvironmentAdapter(Protocol):
    """The simulator-independence boundary.

    The same architecture config must run against a deterministic in-process
    environment, a dataset replay, Project AirSim and PX4/Gazebo, with only
    this implementation swapped.
    """

    @property
    def name(self) -> str: ...

    async def reset(self, mission: MissionSpec, seed: int) -> ObservationPacket: ...

    async def observe(self) -> ObservationPacket: ...

    async def step(self, command: ControlCommand, dt_ns: int) -> None:
        """Advance the world by ``dt_ns`` while applying ``command``."""

    def status(self) -> EnvironmentStatus:
        """Privileged scoring truth. Never passed to a policy."""

    async def close(self) -> None: ...


@runtime_checkable
class PerceptionPlugin(Protocol):
    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    async def perceive(
        self, observation: ObservationPacket, mission: MissionSpec
    ) -> PerceptionState: ...


@runtime_checkable
class MemoryPlugin(Protocol):
    """Semantic mission memory only. Never the geometric world model."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    def update(
        self,
        observation: ObservationPacket,
        perception: PerceptionState,
        decision: DecisionEnvelope | None,
    ) -> None: ...

    def snapshot(self) -> MemorySnapshot: ...


@runtime_checkable
class SemanticPolicy(Protocol):
    """The component that holds semantic authority.

    Returning ``None`` means "no new decision this tick" — which is legitimate
    and different from returning a hold command.
    """

    @property
    def name(self) -> str: ...

    @property
    def emits(self) -> tuple[str, ...]:
        """Decision kinds this policy can produce; validated against the config."""

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None: ...


@runtime_checkable
class MonitorPlugin(Protocol):
    """Persistent progress supervision, scheduled independently of the policy."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    async def assess(self, ctx: DecisionContext) -> ProgressState: ...


@runtime_checkable
class AdmissionPolicy(Protocol):
    """Cheap policy deciding whether expensive recovery may be queried."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    async def assess(
        self, ctx: DecisionContext, runtime: AdmissionRuntime
    ) -> AdmissionDecision: ...


@runtime_checkable
class RecoveryPolicy(Protocol):
    """Bounded, event-admitted semantic reasoning."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    async def recover(
        self, request: RecoveryRequest, ctx: DecisionContext
    ) -> DecisionEnvelope | None: ...


@runtime_checkable
class VerifierPlugin(Protocol):
    """Semantic/geometric validation of a proposal, upstream of the planner."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    def verify(self, envelope: DecisionEnvelope, ctx: DecisionContext) -> VerificationResult: ...


@runtime_checkable
class PlannerPlugin(Protocol):
    """Classical local planning from a semantic waypoint."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    def plan(self, goal: WaypointGoal, ctx: DecisionContext) -> Trajectory: ...


@runtime_checkable
class SafetyShield(Protocol):
    """The last line before the controller. Independent of the semantic model."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    def check(
        self, command: ControlCommand, ctx: DecisionContext
    ) -> tuple[ControlCommand, SafetyDecision]: ...


@runtime_checkable
class ControllerAdapter(Protocol):
    """Converts either handoff form into the one canonical ControlCommand."""

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    def track(self, trajectory: Trajectory, ctx: DecisionContext) -> ControlCommand: ...

    def from_action(
        self, action: KinematicAction, ctx: DecisionContext, decision_id: str
    ) -> ControlCommand: ...

    def hold(self, ctx: DecisionContext) -> ControlCommand: ...


@runtime_checkable
class InferenceBackend(Protocol):
    """Where compute cost is incurred and measured.

    Simulated backends charge a configured latency against the simulation clock,
    which is what lets asynchronous architectures be compared deterministically
    before any real model is integrated.
    """

    @property
    def name(self) -> str: ...

    def reset(self, mission: MissionSpec, seed: int) -> None: ...

    async def invoke(self, request: InferenceRequest) -> InferenceResult: ...

    def stats(self) -> dict[str, float]: ...


@runtime_checkable
class MetricsSink(Protocol):
    """Consumes the unified event stream."""

    @property
    def name(self) -> str: ...

    def emit(self, event: object) -> None: ...

    def close(self) -> None: ...


PLUGIN_INTERFACES: tuple[str, ...] = (
    "EnvironmentAdapter",
    "PerceptionPlugin",
    "MemoryPlugin",
    "SemanticPolicy",
    "MonitorPlugin",
    "RecoveryPolicy",
    "VerifierPlugin",
    "PlannerPlugin",
    "SafetyShield",
    "ControllerAdapter",
    "InferenceBackend",
    "MetricsSink",
)
