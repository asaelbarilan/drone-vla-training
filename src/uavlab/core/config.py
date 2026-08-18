"""The architecture configuration grammar.

This module is where "architectures are configuration, not code forks" is
actually enforced.  The grammar is *conditional*: authority determines which
downstream components are meaningful, and combinations that are not
architectures at all — a skill agent with an action horizon, a monitor rate
with no monitor, a waypoint policy with nothing to convert waypoints into
motion — are rejected before an episode can start.

The point of rejecting them is not tidiness.  An illegal configuration that
runs anyway produces a plausible number, and a plausible number from an
incoherent architecture is exactly the kind of result that survives into a
paper.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from uavlab.contracts.common import StrictModel, TaskFamily


class ConfigError(Exception):
    """Raised with *every* violation found, not just the first.

    Deliberately not a subclass of ``ValueError``: Pydantic catches ValueError
    from a validator and re-wraps it in a ValidationError, which would bury the
    violation list inside a generic message and defeat the whole point of
    collecting them.  Inheriting from ``Exception`` lets it propagate intact, so
    ``uavlab validate-config`` can print the violations as written.
    """

    def __init__(self, violations: list[str], context: str = "architecture") -> None:
        self.violations = violations
        bullets = "\n".join(f"  - {v}" for v in violations)
        super().__init__(f"invalid {context} configuration:\n{bullets}")


class Authority(str, Enum):
    """Where learned semantic intelligence hands off physical authority."""

    SKILL = "skill"
    WAYPOINT = "waypoint"
    DIRECT_VLA = "direct_vla"


class ActionHorizon(str, Enum):
    """Only meaningful under learned-action authority."""

    SINGLE = "single"
    CHUNK = "chunk"


class Supervision(str, Enum):
    """When expensive semantic computation is allowed to affect flight."""

    NONE = "none"
    PERIODIC_MONITOR = "periodic_monitor"
    PERIODIC_REASONER = "periodic_reasoner"
    ASYNC_REASONER = "async_reasoner"
    TRIGGERED_REASONER = "triggered_reasoner"


class MemoryMode(str, Enum):
    """What mission history is available to semantic reasoning."""

    NO_MEMORY = "no_memory"
    SHORT_CONTEXT = "short_context"
    COMPACT_KEYFRAME = "compact_keyframe_memory"
    COMPACT_SEMANTIC_STATE = "compact_semantic_state"


class SchedulerKind(str, Enum):
    PERIODIC = "periodic"
    ASYNC_MULTI_RATE = "async_multi_rate"
    EVENT_TRIGGERED = "event_triggered"
    HYBRID = "hybrid"


class ComponentSpec(StrictModel):
    """A registry lookup plus its constructor parameters."""

    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class SchedulerSpec(StrictModel):
    """Timing, owned centrally.

    Scheduling is never implemented privately inside a model plugin: if each
    policy built its own timer, C4, C6, C10, C12 and C13 would differ in
    implementation quality as well as in architecture, and the comparison would
    be meaningless.
    """

    kind: SchedulerKind = SchedulerKind.PERIODIC
    control_hz: float = 20.0
    """Rate at which control commands reach the vehicle."""
    decision_hz: float = 2.0
    """Rate of the primary semantic decision loop."""
    monitor_hz: float | None = None
    """Rate of the independent supervision loop; ``None`` means no monitor loop."""
    reasoner_hz: float | None = None
    """Rate of a slow high-level reasoner, when one runs on its own schedule."""

    trigger: str | None = None
    """Named trigger for event-admitted reasoning, e.g. ``no_progress``."""
    cooldown_s: float = 2.0
    max_calls: int | None = None
    """Hard budget on admitted reasoner calls per episode."""
    trigger_check_hz: float = 5.0
    """How often the trigger condition is evaluated."""


class StalenessSpec(StrictModel):
    """How the runtime treats semantic outputs that arrive late."""

    max_decision_age_s: float = 1.5
    reject_stale: bool = True
    """When false, stale decisions still execute but are logged as stale.

    Useful as a deliberate ablation: it measures what staleness *costs* rather
    than hiding it behind a rejection.
    """


class FeatureCacheSpec(StrictModel):
    enabled: bool = False
    capacity: int = 32


class ArchitectureConfig(StrictModel):
    """One architecture, entirely as data."""

    id: str
    name: str = ""
    description: str = ""

    authority: Authority
    action_horizon: ActionHorizon | None = None
    chunk_length: int = 1
    semantic_supervision: Supervision = Supervision.NONE
    semantic_memory: MemoryMode = MemoryMode.NO_MEMORY
    memory_consumers: tuple[str, ...] = ("policy",)
    """Which roles actually read semantic memory. Each must exist in this config."""

    perception: ComponentSpec = ComponentSpec(name="identity")
    memory: ComponentSpec = ComponentSpec(name="no_memory")
    policy: ComponentSpec
    verifier: ComponentSpec | None = None
    planner: ComponentSpec | None = None
    shield: ComponentSpec | None = None
    monitor: ComponentSpec | None = None
    recovery: ComponentSpec | None = None
    controller: ComponentSpec = ComponentSpec(name="mock_velocity")
    inference: ComponentSpec = ComponentSpec(name="simulated")

    scheduler: SchedulerSpec = Field(default_factory=SchedulerSpec)
    staleness: StalenessSpec = Field(default_factory=StalenessSpec)
    feature_cache: FeatureCacheSpec = Field(default_factory=FeatureCacheSpec)

    allow_privileged_observations: bool = False
    """Only the oracle control ceiling (C0) may see ground truth."""
    unsafe_ablation: bool = False
    """Explicit opt-in for architectures that are deliberately incoherent.

    OnFly's planner-removal ablation is the motivating case: it is a valid
    experiment, but it must be *declared*, so that a missing planner is never
    mistaken for an oversight.
    """
    tags: tuple[str, ...] = ()

    # -- grammar ------------------------------------------------------------

    @model_validator(mode="after")
    def _check_grammar(self) -> ArchitectureConfig:
        v: list[str] = []
        v += self._check_authority_rules()
        v += self._check_supervision_rules()
        v += self._check_memory_rules()
        v += self._check_scheduler_rules()
        if v:
            raise ConfigError(v, context=f"architecture {self.id!r}")
        return self

    def _check_authority_rules(self) -> list[str]:
        v: list[str] = []
        if self.authority is Authority.SKILL:
            if self.action_horizon is not None:
                v.append(
                    "action_horizon is only meaningful under direct_vla authority; "
                    f"authority=skill cannot set action_horizon={self.action_horizon.value!r} "
                    "(a skill call is not a learned action sequence)"
                )
        elif self.authority is Authority.WAYPOINT:
            if self.action_horizon is not None:
                v.append(
                    "action_horizon is only meaningful under direct_vla authority; "
                    "authority=waypoint cannot set it"
                )
            if self.planner is None and not self.unsafe_ablation:
                v.append(
                    "authority=waypoint produces a semantic goal with no downstream "
                    "conversion to motion: set a planner, or declare "
                    "unsafe_ablation=true if removing the planner is the experiment"
                )
        elif self.authority is Authority.DIRECT_VLA:
            if self.action_horizon is None:
                v.append(
                    "authority=direct_vla requires action_horizon=single or chunk; "
                    "the action horizon is the VLA-specific design axis"
                )
            if self.planner is not None:
                v.append(
                    f"authority=direct_vla routes learned actions straight to safety and "
                    f"the controller, so planner={self.planner.name!r} would silently turn "
                    "this into a waypoint architecture"
                )
            if self.action_horizon is ActionHorizon.CHUNK and self.chunk_length < 2:
                v.append(f"action_horizon=chunk requires chunk_length >= 2, got {self.chunk_length}")
            if self.action_horizon is ActionHorizon.SINGLE and self.chunk_length != 1:
                v.append(
                    f"action_horizon=single requires chunk_length == 1, got {self.chunk_length}"
                )
        return v

    def _check_supervision_rules(self) -> list[str]:
        v: list[str] = []
        s = self.semantic_supervision
        if s is Supervision.NONE:
            if self.monitor is not None:
                v.append(
                    f"semantic_supervision=none but monitor={self.monitor.name!r} is configured"
                )
            if self.recovery is not None:
                v.append(
                    f"semantic_supervision=none but recovery={self.recovery.name!r} is configured"
                )
        elif s is Supervision.PERIODIC_MONITOR:
            if self.monitor is None:
                v.append("semantic_supervision=periodic_monitor requires a monitor component")
            if self.scheduler.monitor_hz is None:
                v.append("semantic_supervision=periodic_monitor requires scheduler.monitor_hz")
        elif s in (Supervision.PERIODIC_REASONER, Supervision.ASYNC_REASONER):
            if self.recovery is None and self.monitor is None:
                v.append(
                    f"semantic_supervision={s.value} requires a slow reasoner: configure it as "
                    "the recovery or monitor component"
                )
            if self.scheduler.reasoner_hz is None and self.scheduler.monitor_hz is None:
                v.append(
                    f"semantic_supervision={s.value} requires scheduler.reasoner_hz "
                    "(or monitor_hz when the reasoner runs in the monitor slot)"
                )
            if s is Supervision.ASYNC_REASONER and self.scheduler.kind not in (
                SchedulerKind.ASYNC_MULTI_RATE,
                SchedulerKind.HYBRID,
            ):
                v.append(
                    "semantic_supervision=async_reasoner requires scheduler.kind of "
                    f"async_multi_rate or hybrid, got {self.scheduler.kind.value!r}; a periodic "
                    "scheduler would make the 'asynchronous' claim untestable"
                )
        elif s is Supervision.TRIGGERED_REASONER:
            if self.recovery is None:
                v.append("semantic_supervision=triggered_reasoner requires a recovery component")
            if not self.scheduler.trigger:
                v.append(
                    "semantic_supervision=triggered_reasoner requires scheduler.trigger; "
                    "the admission policy is the whole experiment"
                )
            if self.scheduler.kind not in (SchedulerKind.EVENT_TRIGGERED, SchedulerKind.HYBRID):
                v.append(
                    "semantic_supervision=triggered_reasoner requires scheduler.kind of "
                    f"event_triggered or hybrid, got {self.scheduler.kind.value!r}"
                )
        return v

    def _check_memory_rules(self) -> list[str]:
        v: list[str] = []
        declared_none = self.semantic_memory is MemoryMode.NO_MEMORY
        plugin_none = self.memory.name in ("no_memory", "none")
        if declared_none and not plugin_none:
            v.append(
                f"semantic_memory=no_memory but memory plugin is {self.memory.name!r}; "
                "the declared architecture and the wired component disagree"
            )
        if not declared_none and plugin_none:
            v.append(
                f"semantic_memory={self.semantic_memory.value} but no memory plugin is wired"
            )
        present = {
            "policy": True,
            "monitor": self.monitor is not None,
            "recovery": self.recovery is not None,
        }
        for consumer in self.memory_consumers:
            if consumer not in present:
                v.append(
                    f"memory_consumers lists {consumer!r}, which is not a semantic role; "
                    f"expected any of {sorted(present)}"
                )
            elif not present[consumer]:
                v.append(
                    f"memory is configured for {consumer!r}, but this architecture has no "
                    f"{consumer} component to consume it"
                )
        if not declared_none and not self.memory_consumers:
            v.append(
                f"semantic_memory={self.semantic_memory.value} with no memory_consumers: "
                "memory that nothing reads is dead compute, not an architecture"
            )
        return v

    def _check_scheduler_rules(self) -> list[str]:
        v: list[str] = []
        sch = self.scheduler
        if sch.control_hz <= 0:
            v.append(f"scheduler.control_hz must be positive, got {sch.control_hz}")
        if sch.decision_hz <= 0:
            v.append(f"scheduler.decision_hz must be positive, got {sch.decision_hz}")
        if sch.control_hz < sch.decision_hz:
            v.append(
                f"scheduler.control_hz ({sch.control_hz}) is below decision_hz "
                f"({sch.decision_hz}): decisions would be produced faster than they can be "
                "executed, so measured control frequency would not mean what it says"
            )
        if sch.monitor_hz is not None and self.monitor is None:
            v.append(
                f"scheduler.monitor_hz={sch.monitor_hz} is set but no monitor component exists"
            )
        if sch.reasoner_hz is not None and self.recovery is None and self.monitor is None:
            v.append(
                f"scheduler.reasoner_hz={sch.reasoner_hz} is set but no reasoner component exists"
            )
        if sch.trigger and self.recovery is None:
            v.append(f"scheduler.trigger={sch.trigger!r} is set but no recovery component exists")
        if sch.kind is SchedulerKind.EVENT_TRIGGERED and not sch.trigger:
            v.append("scheduler.kind=event_triggered requires a trigger name")
        if sch.kind is SchedulerKind.ASYNC_MULTI_RATE and (
            sch.monitor_hz is None and sch.reasoner_hz is None
        ):
            v.append(
                "scheduler.kind=async_multi_rate requires a second rate "
                "(monitor_hz or reasoner_hz); with one rate it is just periodic"
            )
        if sch.max_calls is not None and sch.max_calls < 0:
            v.append(f"scheduler.max_calls must be >= 0, got {sch.max_calls}")
        return v

    # -- identity -----------------------------------------------------------

    def config_hash(self) -> str:
        """Stable hash of the whole architecture, for the run manifest."""
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    @property
    def semantic_roles(self) -> tuple[str, ...]:
        roles = ["policy"]
        if self.monitor is not None:
            roles.append("monitor")
        if self.recovery is not None:
            roles.append("recovery")
        return tuple(roles)


class FailureInjection(StrictModel):
    """Deliberate mid-episode failures, so recovery is measured, not hoped for."""

    kind: str
    """``block_path`` | ``lure_target`` | ``sensor_dropout`` | ``wind_gust``."""
    at_s: float
    params: dict[str, float] = Field(default_factory=dict)


class EnvironmentConfig(StrictModel):
    """The world, independent of both architecture and episode."""

    id: str
    adapter: ComponentSpec = ComponentSpec(name="grid3d")
    task_family: TaskFamily = TaskFamily.LONG_HORIZON_NAV
    instruction: str = "fly to the target"
    max_episode_s: float = 120.0
    params: dict[str, Any] = Field(default_factory=dict)


class EpisodeSpec(StrictModel):
    """One trial: task, scene, seed, injected failures."""

    episode_id: str
    seed: int = 0
    scene: str = "default"
    failures: tuple[FailureInjection, ...] = ()
    overrides: dict[str, Any] = Field(default_factory=dict)


class ExperimentConfig(StrictModel):
    """A staged sweep: which architectures, on which environments, how often."""

    id: str
    description: str = ""
    architectures: tuple[str, ...]
    environments: tuple[str, ...]
    seeds: tuple[int, ...] = (0, 1, 2)
    episodes_per_cell: int = 1
    stage: str = "macro_screening"
    """Which staged screen this belongs to; ordering is part of the protocol."""
    compare: tuple[tuple[str, str], ...] = ()
    """Explicit paired contrasts, e.g. ``[["c2","c3"]]``. Analysis is paired by seed."""

    def cells(self) -> list[tuple[str, str, int]]:
        """Expand into ``(architecture, environment, seed)`` cells."""
        out: list[tuple[str, str, int]] = []
        for arch in self.architectures:
            for env in self.environments:
                for seed in self.seeds:
                    for rep in range(self.episodes_per_cell):
                        out.append((arch, env, seed * 1000 + rep))
        return out
