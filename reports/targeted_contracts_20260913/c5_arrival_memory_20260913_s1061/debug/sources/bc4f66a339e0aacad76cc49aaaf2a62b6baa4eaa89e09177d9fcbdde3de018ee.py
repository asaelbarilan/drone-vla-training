"""The experiment orchestrator: config, seeds, clock, scheduling, lifecycle.

One episode is a set of concurrently scheduled roles sharing a simulation
clock:

* **control** samples the vehicle state and issues one shielded command per
  tick.  It runs fastest and never waits for semantics.
* **decision** runs perception, memory and the semantic policy at its own rate.
  Whatever compute that costs is charged to the clock, so a slow policy really
  does leave the vehicle flying on an older intent.
* **monitor** and **reasoner** run beside the decision loop when the
  architecture says they are asynchronous, and *inside* it when the architecture
  says they are a periodic hierarchy.  That structural difference is the C10
  versus C12 contrast, and it is the reason both must be expressible without
  changing any component.
* **trigger** evaluates the admission condition for event-invoked reasoning.

None of these roles know which architecture they are part of.  They read the
config, build plugins from the registry, and route everything through the same
typed contracts.
"""

from __future__ import annotations

import asyncio
import math
import time
import uuid
from pathlib import Path

from uavlab.contracts import (
    AdmissionRuntime,
    DecisionEnvelope,
    EventType,
    MemorySnapshot,
    MissionConstraints,
    MissionSpec,
    PerceptionState,
    ProgressLabel,
    ProgressState,
    RecoveryRequest,
    RecoveryTrigger,
    SuccessCriteria,
    TerminationReason,
    ns_to_s,
    s_to_ns,
)
from uavlab.core.clock import (
    CURRENT_ROLE,
    HarnessError,
    SimClock,
    WallClock,
    pump_until_done,
)
from uavlab.core.config import (
    ArchitectureConfig,
    Authority,
    EnvironmentConfig,
    EpisodeSpec,
)
from uavlab.core.decision_router import DecisionRouter
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.registry import REGISTRY, PluginRegistry
from uavlab.core.results import EpisodeResult
from uavlab.core.scheduler import RoleSchedule, Scheduler
from uavlab.core.services import RuntimeServices, bind
from uavlab.core.skills import SkillRuntime
from uavlab.interfaces import DecisionContext, RoutingFeedback

DEFAULT_ROLE_ORDER = ("control", "decision", "monitor", "reasoner", "trigger")
"""Fixed spawn order. Determinism of the whole runtime depends on it."""


def _onfly_recovery_heading(last_normal_yaw_rad: float | None, current_yaw_rad: float) -> float:
    """Return the paper-defined heading used after an OnFly LOST signal.

    The last normal *point* is a stored pose.  Recovery restores that pose's
    heading; it does not face the point's position, which would usually turn
    the vehicle backwards along its travelled path.
    """
    target = last_normal_yaw_rad if last_normal_yaw_rad is not None else current_yaw_rad + math.pi
    return math.atan2(math.sin(target), math.cos(target))


def _onfly_monitor_anchor(ctx: DecisionContext):
    """Return the pose synchronized with the latest visual monitor evidence."""
    for item in reversed(ctx.memory.items):
        if item.image_uri is not None and item.position is not None and item.yaw_rad is not None:
            return item.position, item.yaw_rad, item.observation_seq
    return ctx.observation.position, ctx.observation.yaw_rad, ctx.observation.seq


class Orchestrator:
    """Runs exactly one episode of one architecture in one environment."""

    def __init__(
        self,
        arch: ArchitectureConfig,
        env_cfg: EnvironmentConfig,
        episode: EpisodeSpec,
        *,
        out_dir: Path | None = None,
        debug_capture: bool = False,
        registry: PluginRegistry | None = None,
        wall_clock: WallClock | None = None,
    ) -> None:
        self.arch = arch
        self.env_cfg = env_cfg
        self.episode = episode
        self.out_dir = out_dir
        self.registry = registry or REGISTRY

        self.clock = SimClock(wall=wall_clock)
        self.log = EventLog(episode.episode_id, out_dir, debug_capture=debug_capture)
        self.feature_cache = FeatureCache(
            enabled=arch.feature_cache.enabled, capacity=arch.feature_cache.capacity
        )
        self.scheduler = Scheduler(arch.scheduler, self.clock)

        self.mission = self._build_mission()
        self.max_sim_ns = s_to_ns(env_cfg.max_episode_s)

        # Latest state, published by whichever role produced it.
        self.latest_obs = None
        self.last_perception: PerceptionState | None = None
        self.last_memory: MemorySnapshot | None = None
        self.last_progress: ProgressState | None = None
        self.last_decision: DecisionEnvelope | None = None
        self.last_routing_feedback: RoutingFeedback | None = None
        self.scratch: dict[str, object] = {}

        self._error: BaseException | None = None
        self._termination: TerminationReason | None = None
        self._termination_detail = ""
        self._decision_ticks = 0
        self._reached_goal_t_ns: int | None = None
        self._last_normal_position = None
        self._last_normal_yaw_rad: float | None = None
        self._onfly_loss_episode_active = False
        self._stop = asyncio.Event()

    # -- construction -------------------------------------------------------

    def _build_mission(self) -> MissionSpec:
        params = dict(self.env_cfg.params)
        success = SuccessCriteria.model_validate(params.get("success", {}))
        constraints = MissionConstraints.model_validate(params.get("constraints", {}))
        return MissionSpec(
            mission_id=f"{self.env_cfg.id}:{self.episode.episode_id}",
            instruction=self.env_cfg.instruction,
            task_family=self.env_cfg.task_family,
            success=success,
            constraints=constraints,
            allowed_skills=tuple(params.get("allowed_skills", ())),
            metadata={"environment": self.env_cfg.id, "scene": self.episode.scene},
        )

    def _build_components(self) -> None:
        arch, reg = self.arch, self.registry
        env_params = dict(self.env_cfg.params)
        env_params.update(self.env_cfg.adapter.params)
        env_params["allow_privileged"] = arch.allow_privileged_observations
        # The environment declares the failures that define its regime; the
        # episode may add more. Episode failures extend rather than replace, so
        # a recovery scenario cannot be silently disarmed by an episode spec.
        env_params["failures"] = list(env_params.get("failures", ())) + [
            f.model_dump() for f in self.episode.failures
        ]

        self.env = reg.build("environment", self.env_cfg.adapter.name, env_params)
        self.perception = reg.build("perception", arch.perception.name, arch.perception.params)
        self.memory = reg.build("memory", arch.memory.name, arch.memory.params)
        self.policy = reg.build("policy", arch.policy.name, arch.policy.params)
        self.controller = reg.build("controller", arch.controller.name, arch.controller.params)
        self.inference = reg.build("inference", arch.inference.name, arch.inference.params)

        self.verifier = (
            reg.build("verifier", arch.verifier.name, arch.verifier.params)
            if arch.verifier
            else None
        )
        self.planner = (
            reg.build("planner", arch.planner.name, arch.planner.params) if arch.planner else None
        )
        self.shield = (
            reg.build("shield", arch.shield.name, arch.shield.params) if arch.shield else None
        )
        self.monitor = (
            reg.build("monitor", arch.monitor.name, arch.monitor.params) if arch.monitor else None
        )
        self.admission = (
            reg.build("admission", arch.admission.name, arch.admission.params)
            if arch.admission
            else None
        )
        self.recovery = (
            reg.build("recovery", arch.recovery.name, arch.recovery.params)
            if arch.recovery
            else None
        )

        self.router = DecisionRouter(
            arch,
            verifier=self.verifier,
            planner=self.planner,
            shield=self.shield,
            controller=self.controller,
            skill_runtime=SkillRuntime(self.mission.allowed_skills),
        )

        if self.log.debug_capture is not None:
            from uavlab.core.debug_capture import RecordingInference

            self.inference = RecordingInference(self.inference, self.log.debug_capture)

        services = RuntimeServices(
            clock=self.clock,
            log=self.log,
            feature_cache=self.feature_cache,
            inference=self.inference,
            episode_id=self.episode.episode_id,
            seed=self.episode.seed,
        )
        self.components = [
            self.env,
            self.perception,
            self.memory,
            self.policy,
            self.controller,
            self.inference,
            self.verifier,
            self.planner,
            self.shield,
            self.monitor,
            self.admission,
            self.recovery,
        ]
        for component in self.components:
            if component is not None:
                bind(component, services)

        self._check_policy_authority()

    def _check_policy_authority(self) -> None:
        """Fail before launch if the policy cannot exercise the declared authority."""
        emits = tuple(getattr(self.policy, "emits", ()))
        if not emits:
            return
        expected = {
            Authority.SKILL: {"skill", "mission_directive"},
            Authority.WAYPOINT: {"waypoint", "mission_directive"},
            Authority.DIRECT_VLA: {"kinematic_action", "action_chunk", "mission_directive"},
        }[self.arch.authority]
        illegal = sorted(set(emits) - expected)
        if illegal:
            raise HarnessError(
                f"policy {self.arch.policy.name!r} emits {illegal}, which authority="
                f"{self.arch.authority.value} does not permit (allowed: {sorted(expected)})"
            )

    # -- context ------------------------------------------------------------

    def _ctx(self) -> DecisionContext:
        assert self.latest_obs is not None, "context requested before the first observation"
        return DecisionContext(
            mission=self.mission,
            observation=self.latest_obs,
            perception=self.last_perception
            or PerceptionState(observation_seq=self.latest_obs.seq, t_sim_ns=self.clock.now_ns()),
            memory=self.last_memory
            or MemorySnapshot(observation_seq=self.latest_obs.seq, t_sim_ns=self.clock.now_ns()),
            t_sim_ns=self.clock.now_ns(),
            t_wall_ns=self.clock.wall_ns(),
            episode_id=self.episode.episode_id,
            last_progress=self.last_progress,
            last_decision=self.last_decision,
            last_directive=self.router.last_directive if hasattr(self, "router") else None,
            last_routing_feedback=self.last_routing_feedback,
            scratch=self.scratch,
        )

    def _emit(self, component: str, event_type: EventType, payload: dict, trace: str | None = None):
        return self.log.emit(
            component,
            event_type,
            self.clock.now_ns(),
            self.clock.wall_ns(),
            payload=payload,
            trace_id=trace,
        )

    # -- roles --------------------------------------------------------------

    async def _control_loop(self, sched: RoleSchedule) -> None:
        """Sense, command, step. The only role that touches the environment."""
        dt_ns = sched.period_ns or s_to_ns(0.05)
        while not self._stop.is_set():
            self.latest_obs = await self.env.observe()
            ctx = self._ctx()
            command, safety, age_ns = self.router.command_for_tick(ctx)

            if safety is not None and safety.verdict.value != "accept":
                self._emit(
                    "shield",
                    EventType.SAFETY,
                    {
                        "verdict": safety.verdict.value,
                        "reason": safety.reason,
                        "risk": safety.risk,
                        "magnitude": safety.intervention_magnitude,
                    },
                    trace=command.source_decision_id,
                )

            self._emit(
                "controller",
                EventType.CONTROL,
                {
                    # Onboard pose at the instant the command was issued. This
                    # is the audit-grade trajectory source for end maps; it is
                    # already present in the ordinary observation and does not
                    # expose simulator-only scene truth to the policy.
                    "position_x": ctx.observation.position.x,
                    "position_y": ctx.observation.position.y,
                    "position_z": ctx.observation.position.z,
                    "vx": command.velocity.x,
                    "vy": command.velocity.y,
                    "vz": command.velocity.z,
                    "yaw_rate": command.yaw_rate_rps,
                    "decision_age_s": ns_to_s(age_ns) if age_ns is not None else None,
                    "safety_modified": command.safety_modified,
                    "source_observation_seq": command.source_observation_seq,
                },
                trace=command.source_decision_id,
            )

            await self.env.step(command, dt_ns)
            if self._check_termination():
                self._stop.set()
                return
            await self.scheduler.tick(sched)

    async def _decision_loop(self, sched: RoleSchedule, inline: list[RoleSchedule]) -> None:
        """Perception, memory, policy — and any inline supervision."""
        while not self._stop.is_set():
            if self.latest_obs is None:
                await self.scheduler.tick(sched)
                continue
            obs = self.latest_obs

            perception = await self.perception.perceive(obs, self.mission)
            self.last_perception = perception
            self._emit(
                "perception",
                EventType.PERCEPTION,
                {
                    "observation_seq": obs.seq,
                    "detections": len(perception.detections),
                    "uncertainty": perception.uncertainty,
                },
            )

            self.memory.update(obs, perception, self.last_decision)
            snapshot = self.memory.snapshot()
            self.last_memory = snapshot
            self._emit(
                "memory",
                EventType.MEMORY_UPDATE,
                {
                    "policy": snapshot.policy_name,
                    "items": len(snapshot.items),
                    "tokens_used": snapshot.tokens_used,
                },
            )

            for role in inline:
                if self._decision_ticks % max(1, role.every_n_decisions) == 0:
                    await self._run_supervision(role.role, blocking=True)
                if self._stop.is_set():
                    return

            ctx = self._ctx()
            envelope = await self.policy.decide(ctx)
            if envelope is not None:
                self._handle_envelope(envelope, "policy")
            self.last_decision = envelope or self.last_decision

            self._decision_ticks += 1
            if self._stop.is_set():
                return
            await self.scheduler.tick(sched)

    async def _monitor_loop(self, sched: RoleSchedule) -> None:
        while not self._stop.is_set():
            if self.latest_obs is not None:
                await self._run_supervision("monitor", blocking=False)
            if self._stop.is_set():
                return
            await self.scheduler.tick(sched)

    async def _reasoner_loop(self, sched: RoleSchedule) -> None:
        while not self._stop.is_set():
            if self.latest_obs is not None:
                await self._run_supervision("reasoner", blocking=False)
            if self._stop.is_set():
                return
            await self.scheduler.tick(sched)

    async def _trigger_loop(self, sched: RoleSchedule) -> None:
        """Evaluate the admission condition; call the reasoner only if admitted.

        This is the whole point of the event-triggered family: during nominal
        execution the expensive reasoner is *absent*, and the log shows zero
        calls rather than cheap ones.
        """
        gate = self.scheduler.gate
        while not self._stop.is_set():
            if gate is not None and self.latest_obs is not None:
                admission_decision = None
                if self.admission is not None:
                    admission_decision = await self.admission.assess(
                        self._ctx(),
                        AdmissionRuntime(
                            t_sim_ns=self.clock.now_ns(),
                            call_count=gate.calls,
                            max_calls=gate.max_calls,
                            last_call_t_sim_ns=gate.last_fired_ns,
                            cooldown_s=ns_to_s(gate.cooldown_ns),
                            planner_failed=self._last_plan_failed(),
                            safety_interventions=self.log.count(EventType.SAFETY),
                        ),
                    )
                    cause = admission_decision.reason if admission_decision.admit else None
                else:
                    cause = gate.condition_met(
                        self.last_progress,
                        self.last_perception,
                        stall_threshold_s=float(
                            self.arch.recovery.params.get("stall_threshold_s", 2.0)
                            if self.arch.recovery
                            else 2.0
                        ),
                        uncertainty_threshold=float(
                            self.arch.recovery.params.get("uncertainty_threshold", 0.6)
                            if self.arch.recovery
                            else 0.6
                        ),
                    )
                admitted = gate.admit(self.clock.now_ns(), cause)
                if admission_decision is not None:
                    self._emit(
                        "admission",
                        EventType.ADMISSION,
                        {
                            "policy": self.admission.name,
                            "score": admission_decision.score,
                            "threshold": admission_decision.threshold,
                            "hard_stuck": admission_decision.hard_stuck,
                            "candidate": admission_decision.admit,
                            "admitted": admitted is not None,
                            "reason": admission_decision.reason,
                            "guards": admission_decision.guards,
                            "features": dict(
                                zip(
                                    admission_decision.feature_names,
                                    admission_decision.features,
                                    strict=True,
                                )
                            ),
                        },
                    )
                if admitted is not None:
                    self._emit(
                        "trigger",
                        EventType.RECOVERY_TRIGGER,
                        {"trigger": gate.name, "cause": admitted, "call_index": gate.calls},
                    )
                    await self._run_recovery(admitted, gate.calls - 1)
            if self._stop.is_set():
                return
            await self.scheduler.tick(sched)
        return

    def _last_plan_failed(self) -> bool:
        """Return only the latest local-planner outcome, never simulator truth."""
        plans = self.log.of_type(EventType.PLAN)
        if not plans:
            return False
        return plans[-1].payload.get("feasible") is False

    async def _run_supervision(self, role: str, blocking: bool) -> None:
        """Run the monitor or the slow reasoner once."""
        ctx = self._ctx()
        if role == "monitor" and self.monitor is not None:
            progress = await self.monitor.assess(ctx)
            stop_check = getattr(self.monitor, "stop_still_supported", None)
            if (
                progress.label is ProgressLabel.STOP
                and stop_check is not None
                and not stop_check(self.latest_obs or ctx.observation)
            ):
                progress = progress.model_copy(
                    update={
                        "label": ProgressLabel.CONTINUE,
                        "evidence": progress.evidence + "; stop rejected by live arrival recheck",
                    }
                )
            self.last_progress = progress
            anchor_position, anchor_yaw, anchor_seq = _onfly_monitor_anchor(ctx)
            if getattr(self.monitor, "target_bound_stop", False):
                anchor_position = ctx.observation.position
                anchor_yaw, anchor_seq = ctx.observation.yaw_rad, ctx.observation.seq
            self._emit(
                "monitor",
                EventType.MONITOR,
                {
                    "label": progress.label.value,
                    "confidence": progress.confidence,
                    "stalled_for_s": progress.stalled_for_s,
                    "evidence": progress.evidence,
                    "recovery_anchor_valid": progress.recovery_anchor_valid,
                    "recovery_reacquired": progress.recovery_reacquired,
                    "evidence_observation_seq": progress.observation_seq,
                    "recovery_anchor_observation_seq": anchor_seq,
                    "recovery_anchor_yaw_rad": anchor_yaw,
                    "blocking": blocking,
                },
            )
            if progress.label is ProgressLabel.STOP:
                self.router.stop_requested = True
                self.router.stop_reason = f"monitor: {progress.evidence or 'stop'}"
            elif progress.label is ProgressLabel.LOST and self.monitor.name == "onfly_monitor":
                current = self.latest_obs or ctx.observation
                target_yaw = _onfly_recovery_heading(self._last_normal_yaw_rad, current.yaw_rad)
                if not self._onfly_loss_episode_active and not self.router.reorientation_active:
                    self._onfly_loss_episode_active = True
                    self.router.begin_fixed_reorientation(
                        target_yaw_rad=target_yaw,
                        t_sim_ns=self.clock.now_ns(),
                        hold_s=float(getattr(self.monitor, "lost_hold_s", 0.25)),
                        max_duration_s=float(getattr(self.monitor, "lost_reorient_s", 2.0)),
                        yaw_rate_rps=float(getattr(self.monitor, "lost_yaw_rate_rps", 0.8)),
                    )
                    self._emit(
                        "monitor",
                        EventType.RECOVERY_TRIGGER,
                        {
                            "trigger": "onfly_lost",
                            "cause": progress.evidence,
                            "target_yaw_rad": target_yaw,
                        },
                    )
                    self._emit(
                        "recovery",
                        EventType.RECOVERY_DECISION,
                        {
                            "kind": "fixed_reorientation",
                            "cause": "monitor_lost",
                            "producer": "onfly_lost_executive",
                        },
                    )
            elif progress.label is ProgressLabel.CONTINUE:
                if progress.recovery_anchor_valid:
                    self._last_normal_position = anchor_position
                    self._last_normal_yaw_rad = anchor_yaw
                if (
                    self.monitor.name == "onfly_monitor"
                    and self.router.reorientation_active
                    and not self.router.fence_reorientation_active
                    and (progress.recovery_anchor_valid or progress.recovery_reacquired)
                ):
                    self.router.cancel_fixed_reorientation()
                if progress.recovery_anchor_valid or progress.recovery_reacquired:
                    self._onfly_loss_episode_active = False
        elif role == "reasoner" and self.recovery is not None:
            await self._run_recovery("periodic schedule", call_index=-1)

    async def _run_recovery(self, cause: str, call_index: int) -> None:
        if self.recovery is None:
            return
        ctx = self._ctx()
        request = RecoveryRequest(
            trigger=RecoveryTrigger(
                name=self.arch.scheduler.trigger or "periodic",
                fired_t_sim_ns=self.clock.now_ns(),
                observation_seq=ctx.observation.seq,
                cause=cause,
            ),
            state_summary=(ctx.memory.semantic_summary or "")[:512],
            allowed_skills=self.mission.allowed_skills,
            last_known_target=None,
            call_index=max(0, call_index),
        )
        envelope = await self.recovery.recover(request, ctx)
        if envelope is not None:
            self._emit(
                "recovery",
                EventType.RECOVERY_DECISION,
                {"kind": envelope.kind.value, "cause": cause, "producer": envelope.producer},
                trace=envelope.decision_id,
            )
            self._handle_envelope(envelope, "recovery")

    def _handle_envelope(self, envelope: DecisionEnvelope, origin: str) -> None:
        """Route one proposal and log what happened to it."""
        ctx = self._ctx()
        proposed_payload = {
            "kind": envelope.kind.value,
            "producer": envelope.producer,
            "confidence": envelope.confidence,
            "source_observation_seq": envelope.source_observation_seq,
            "production_latency_s": ns_to_s(envelope.produced_t_sim_ns - envelope.source_t_sim_ns),
            # Typed provenance contains bounded model/config identifiers and
            # structured intermediate decisions (for example SPF's u/v/label),
            # never raw model prose. Persisting it is required to audit whether
            # a paper-defining mechanism actually ran rather than merely sharing
            # the same final authority type.
            "provenance": dict(envelope.provenance),
        }
        if self.log.debug_capture is not None:
            proposed_payload["decision_payload"] = envelope.payload.model_dump(mode="json")
        # Typed, bounded decision fields are safe and scientifically necessary
        # to log. Raw model text is intentionally never put on the event bus.
        skill_name = getattr(envelope.payload, "skill_name", None)
        if skill_name is not None:
            proposed_payload["skill_name"] = skill_name
            proposed_payload["skill_args"] = dict(getattr(envelope.payload, "args", {}))
        self._emit(
            origin,
            EventType.DECISION_PROPOSED,
            proposed_payload,
            trace=envelope.decision_id,
        )
        fence_recoveries_before = self.router.counters.fence_recoveries
        outcome = self.router.accept(envelope, ctx)
        if self.router.counters.fence_recoveries > fence_recoveries_before:
            self._emit(
                "verifier",
                EventType.RECOVERY_TRIGGER,
                {
                    "trigger": "geofence_rejections",
                    "cause": outcome.reason,
                    "target_yaw_rad": math.atan2(
                        -ctx.observation.position.y, -ctx.observation.position.x
                    ),
                    "recovery_count": self.router.counters.fence_recoveries,
                },
            )
        self.last_routing_feedback = RoutingFeedback(
            decision_id=envelope.decision_id,
            accepted=outcome.accepted,
            reason=outcome.reason,
            proposed_kind=envelope.kind,
            expanded_kind=outcome.expanded_kind,
            t_sim_ns=self.clock.now_ns(),
        )
        if outcome.accepted:
            self._emit(
                origin,
                EventType.DECISION_EXECUTED,
                {
                    "kind": (outcome.expanded_kind or envelope.kind).value,
                    "reason": outcome.reason,
                    "decision_age_s": ns_to_s(outcome.decision_age_ns or 0),
                    "stale": outcome.stale,
                },
                trace=envelope.decision_id,
            )
        else:
            event = (
                EventType.DECISION_REJECTED_STALE if outcome.stale else EventType.DECISION_PROPOSED
            )
            self._emit(
                origin,
                event,
                {
                    "kind": envelope.kind.value,
                    "rejected": True,
                    "reason": outcome.reason,
                    "decision_age_s": ns_to_s(outcome.decision_age_ns or 0),
                },
                trace=envelope.decision_id,
            )
        if outcome.verification is not None:
            self._emit(
                "verifier",
                EventType.VERIFIER,
                {
                    "accepted": outcome.verification.accepted,
                    "modified": outcome.verification.modified,
                    "reason": outcome.verification.reason,
                },
                trace=envelope.decision_id,
            )
        if outcome.trajectory is not None:
            self._emit(
                "planner",
                EventType.PLAN,
                {
                    "feasible": outcome.trajectory.feasible,
                    "points": len(outcome.trajectory.points),
                    "planner": outcome.trajectory.planner_name,
                    "reason": outcome.trajectory.reason,
                    "planner_metadata": outcome.trajectory.metadata,
                    **(
                        {"trajectory": outcome.trajectory.model_dump(mode="json")}
                        if self.log.debug_capture is not None
                        else {}
                    ),
                },
                trace=envelope.decision_id,
            )

    # -- termination --------------------------------------------------------

    def _check_termination(self) -> bool:
        status = self.env.status()
        now = self.clock.now_ns()

        if status.collided:
            self._finish(TerminationReason.COLLISION, "vehicle collided")
            return True
        if status.out_of_bounds:
            self._finish(TerminationReason.OUT_OF_BOUNDS, "left the geofence")
            return True

        criteria = self.mission.success
        within = status.distance_to_goal_m <= criteria.goal_radius_m
        if within and self._reached_goal_t_ns is None:
            self._reached_goal_t_ns = now

        if self.router.stop_requested:
            self._finish(TerminationReason.AGENT_STOPPED, self.router.stop_reason)
            return True
        if (
            within if status.task_complete is None else status.task_complete
        ) and not criteria.require_terminal_stop:
            self._finish(TerminationReason.GOAL_REACHED, "goal radius reached")
            return True
        if now >= self.max_sim_ns:
            self._finish(TerminationReason.TIMEOUT, "episode time limit reached")
            return True
        return False

    def _finish(self, reason: TerminationReason, detail: str) -> None:
        self._termination = reason
        self._termination_detail = detail

    def _succeeded(self) -> bool:
        """Success is judged from ground truth, never from the agent's belief."""
        status = self.env.status()
        criteria = self.mission.success
        if self._termination in (TerminationReason.COLLISION, TerminationReason.OUT_OF_BOUNDS):
            return False
        if status.subgoals_total and status.subgoals_completed < criteria.required_subgoals:
            return False
        within = status.distance_to_goal_m <= criteria.goal_radius_m
        if not (within if status.task_complete is None else status.task_complete):
            return False
        if criteria.require_terminal_stop:
            return self._termination in (
                TerminationReason.AGENT_STOPPED,
                TerminationReason.GOAL_REACHED,
            )
        return True

    # -- run ----------------------------------------------------------------

    async def run(self) -> EpisodeResult:
        wall_start = time.perf_counter()
        self._build_components()

        seed = self.episode.seed
        for component in self.components:
            # The environment resets asynchronously, just below.
            if component is not None and component is not self.env and hasattr(component, "reset"):
                component.reset(self.mission, seed)
        self.router.reset(self.mission, seed)

        self.latest_obs = await self.env.reset(self.mission, seed)
        self._emit(
            "orchestrator",
            EventType.EPISODE_START,
            {
                "architecture": self.arch.id,
                "environment": self.env_cfg.id,
                "seed": seed,
                "authority": self.arch.authority.value,
                "supervision": self.arch.semantic_supervision.value,
                "memory": self.arch.semantic_memory.value,
                "scheduler": self.arch.scheduler.kind.value,
                "config_hash": self.arch.config_hash(),
            },
        )

        schedules = self.scheduler.build(
            has_monitor=self.monitor is not None, has_recovery=self.recovery is not None
        )
        by_role = {s.role: s for s in schedules}
        inline = [s for s in schedules if not s.concurrent]

        tasks: list[asyncio.Task] = []
        for role in DEFAULT_ROLE_ORDER:
            sched = by_role.get(role)
            if sched is None or not sched.concurrent:
                continue
            self.clock.register_role(role)
            tasks.append(asyncio.create_task(self._guarded(role, sched, inline), name=role))

        try:
            await pump_until_done(self.clock, self._stop, max_sim_ns=self.max_sim_ns)
        except HarnessError as exc:
            self._error = exc
        finally:
            self._stop.set()
            self.clock.cancel_all()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if self._termination is None:
            self._termination = (
                TerminationReason.RUNTIME_ERROR if self._error else TerminationReason.TIMEOUT
            )
            self._termination_detail = str(self._error) if self._error else "horizon reached"

        result = self._result(wall_start)
        self._emit(
            "orchestrator",
            EventType.EPISODE_END,
            {
                "success": result.success,
                "reason": result.termination_reason.value,
                "detail": result.termination_detail,
                "sim_duration_s": result.sim_duration_s,
            },
        )
        await self.env.close()
        self.log.write_parquet()
        self.log.close()
        return result

    async def _guarded(self, role: str, sched: RoleSchedule, inline: list[RoleSchedule]) -> None:
        """Run one role loop, converting any failure into a clean episode abort."""
        CURRENT_ROLE.set(role)
        try:
            match role:
                case "control":
                    await self._control_loop(sched)
                case "decision":
                    await self._decision_loop(sched, inline)
                case "monitor":
                    await self._monitor_loop(sched)
                case "reasoner":
                    await self._reasoner_loop(sched)
                case "trigger":
                    await self._trigger_loop(sched)
                case _:
                    raise HarnessError(f"no loop implemented for role {role!r}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._error = exc
            self._finish(TerminationReason.RUNTIME_ERROR, f"{role}: {exc!r}")
            self._emit("orchestrator", EventType.WARNING, {"role": role, "error": repr(exc)})
            self._stop.set()
        finally:
            self.clock.unregister_role(role)

    def _result(self, wall_start: float) -> EpisodeResult:
        from uavlab.analysis.metrics import compute_metrics

        status = self.env.status()
        metrics = compute_metrics(
            log=self.log,
            router=self.router,
            scheduler=self.scheduler,
            status=status,
            inference=self.inference,
            feature_cache=self.feature_cache,
            sim_duration_ns=self.clock.now_ns(),
            arch=self.arch,
            reached_goal_t_ns=self._reached_goal_t_ns,
            components=[
                self.policy,
                self.monitor,
                self.admission,
                self.recovery,
                self.verifier,
            ],
        )
        return EpisodeResult(
            episode_id=self.episode.episode_id,
            architecture_id=self.arch.id,
            environment_id=self.env_cfg.id,
            task_family=self.env_cfg.task_family,
            seed=self.episode.seed,
            success=self._succeeded() and self._error is None,
            termination_reason=self._termination or TerminationReason.TIMEOUT,
            termination_detail=self._termination_detail,
            sim_duration_s=self.clock.now_s(),
            wall_duration_s=time.perf_counter() - wall_start,
            metrics=metrics,
            status=status,
            config_hash=self.arch.config_hash(),
            used_privileged_observations=self.arch.allow_privileged_observations,
            error=repr(self._error) if self._error else None,
        )


async def run_episode(
    arch: ArchitectureConfig,
    env_cfg: EnvironmentConfig,
    episode: EpisodeSpec | None = None,
    *,
    out_dir: Path | None = None,
    registry: PluginRegistry | None = None,
) -> EpisodeResult:
    """Convenience entry point used by the CLI, the sweeps and the tests."""
    episode = episode or EpisodeSpec(episode_id=uuid.uuid4().hex[:12])
    orchestrator = Orchestrator(arch, env_cfg, episode, out_dir=out_dir, registry=registry)
    return await orchestrator.run()
