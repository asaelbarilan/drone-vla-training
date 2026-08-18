"""The decision router: one dispatch table for every semantic authority level.

Each decision kind has exactly one legal path to the vehicle:

    skill            -> skill runtime -> subgoal -> verifier -> planner -> shield -> controller
    waypoint         ->                            verifier -> planner -> shield -> controller
    kinematic_action ->                                                   shield -> controller
    action_chunk     -> chunk executor (receding horizon)              -> shield -> controller
    mission_directive-> scheduler / monitor state only. Never motor authority.

Two invariants are enforced here rather than trusted:

* a mission directive can never become a control command;
* a semantic output is checked for staleness *at execution time*, not at
  production time, because in an asynchronous architecture those are different
  moments and only the second one describes what the vehicle actually did.
"""

from __future__ import annotations

import dataclasses
from collections import deque
from dataclasses import dataclass, field

from uavlab.contracts import (
    ActionChunk,
    ControlCommand,
    DecisionEnvelope,
    DecisionKind,
    KinematicAction,
    MissionDirective,
    MissionSpec,
    ProgressLabel,
    SafetyDecision,
    SafetyVerdict,
    SkillCall,
    Trajectory,
    Vec3,
    WaypointGoal,
    s_to_ns,
)
from uavlab.core.config import ArchitectureConfig
from uavlab.core.skills import SkillRuntime, UnknownSkillError
from uavlab.interfaces import (
    ControllerAdapter,
    DecisionContext,
    PlannerPlugin,
    SafetyShield,
    VerificationResult,
    VerifierPlugin,
)


class RouterViolation(RuntimeError):
    """A decision tried to take a path the architecture does not permit."""


@dataclass(slots=True)
class RoutingOutcome:
    """What the router did with one proposal, in full."""

    accepted: bool
    reason: str = ""
    stale: bool = False
    decision_age_ns: int | None = None
    verification: VerificationResult | None = None
    trajectory: Trajectory | None = None
    directive: MissionDirective | None = None
    expanded_kind: DecisionKind | None = None


@dataclass(slots=True)
class _MotionSource:
    """The currently authoritative source of motion, and when it expires."""

    decision_id: str
    source_observation_seq: int
    source_t_sim_ns: int
    kind: DecisionKind
    trajectory: Trajectory | None = None
    actions: deque[KinematicAction] = field(default_factory=deque)
    action_expiry_ns: int | None = None
    stop_when_done: bool = False
    was_stale: bool = False


@dataclass(slots=True)
class RouterCounters:
    proposed: int = 0
    executed: int = 0
    rejected_stale: int = 0
    verifier_rejected: int = 0
    verifier_modified: int = 0
    plans_requested: int = 0
    plans_infeasible: int = 0
    directives: int = 0
    chunk_actions_executed: int = 0
    chunk_actions_discarded: int = 0
    safety_accept: int = 0
    safety_modify: int = 0
    safety_reject: int = 0
    safety_stop: int = 0
    commands_issued: int = 0
    stale_commands_executed: int = 0
    decision_age_ns_total: int = 0
    decision_age_samples: int = 0
    unknown_skill: int = 0

    def as_dict(self) -> dict[str, float]:
        d = {
            f"router_{f.name}": float(getattr(self, f.name))
            for f in dataclasses.fields(self)
        }
        if self.decision_age_samples:
            d["router_mean_decision_age_s"] = (
                self.decision_age_ns_total / self.decision_age_samples / 1e9
            )
        return d


class DecisionRouter:
    """Routes typed decisions to motion, and issues one command per control tick."""

    def __init__(
        self,
        arch: ArchitectureConfig,
        *,
        verifier: VerifierPlugin | None,
        planner: PlannerPlugin | None,
        shield: SafetyShield | None,
        controller: ControllerAdapter,
        skill_runtime: SkillRuntime | None = None,
    ) -> None:
        self.arch = arch
        self.verifier = verifier
        self.planner = planner
        self.shield = shield
        self.controller = controller
        self.skills = skill_runtime or SkillRuntime()
        self.max_age_ns = s_to_ns(arch.staleness.max_decision_age_s)
        self.reject_stale = arch.staleness.reject_stale

        self.source: _MotionSource | None = None
        self.counters = RouterCounters()
        self.stop_requested: bool = False
        self.stop_reason: str = ""
        self.last_directive: MissionDirective | None = None

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self.source = None
        self.counters = RouterCounters()
        self.stop_requested = False
        self.stop_reason = ""
        self.last_directive = None
        self.skills.reset()
        if mission.allowed_skills:
            self.skills.allowed = mission.allowed_skills

    # -- accepting a proposal ----------------------------------------------

    def accept(self, envelope: DecisionEnvelope, ctx: DecisionContext) -> RoutingOutcome:
        """Validate a proposal and, if it survives, make it authoritative."""
        self.counters.proposed += 1
        age_ns = envelope.age_ns(ctx.t_sim_ns)
        stale = envelope.is_expired(ctx.t_sim_ns) or age_ns > self.max_age_ns

        if stale and self.reject_stale:
            self.counters.rejected_stale += 1
            return RoutingOutcome(
                accepted=False,
                reason=f"stale: decision_age={age_ns / 1e9:.3f}s exceeds "
                f"{self.max_age_ns / 1e9:.3f}s",
                stale=True,
                decision_age_ns=age_ns,
            )

        payload = envelope.payload

        # Supervisory output: never motion.
        if isinstance(payload, MissionDirective):
            return self._accept_directive(payload, envelope, age_ns, stale)

        # Skill authority expands into an ordinary subgoal first.
        if isinstance(payload, SkillCall):
            try:
                expanded = self.skills.expand(payload, ctx)
            except UnknownSkillError as exc:
                self.counters.unknown_skill += 1
                return RoutingOutcome(accepted=False, reason=str(exc), decision_age_ns=age_ns)
            if isinstance(expanded, MissionDirective):
                return self._accept_directive(expanded, envelope, age_ns, stale)
            outcome = self._accept_motion(expanded, envelope, ctx, age_ns, stale)
            outcome.expanded_kind = expanded.kind
            return outcome

        return self._accept_motion(payload, envelope, ctx, age_ns, stale)

    def _accept_directive(
        self,
        directive: MissionDirective,
        envelope: DecisionEnvelope,
        age_ns: int,
        stale: bool,
    ) -> RoutingOutcome:
        self.counters.directives += 1
        self.last_directive = directive
        if directive.label is ProgressLabel.STOP:
            self.stop_requested = True
            self.stop_reason = directive.rationale or "mission directive: stop"
        return RoutingOutcome(
            accepted=True,
            reason="directive recorded (no motor authority)",
            stale=stale,
            decision_age_ns=age_ns,
            directive=directive,
            expanded_kind=DecisionKind.MISSION_DIRECTIVE,
        )

    def _accept_motion(
        self,
        payload: WaypointGoal | KinematicAction | ActionChunk,
        envelope: DecisionEnvelope,
        ctx: DecisionContext,
        age_ns: int,
        stale: bool,
    ) -> RoutingOutcome:
        verification: VerificationResult | None = None
        effective = payload

        if isinstance(payload, WaypointGoal):
            if self.verifier is not None:
                verification = self.verifier.verify(envelope, ctx)
                if not verification.accepted:
                    self.counters.verifier_rejected += 1
                    return RoutingOutcome(
                        accepted=False,
                        reason=f"verifier rejected: {verification.reason}",
                        stale=stale,
                        decision_age_ns=age_ns,
                        verification=verification,
                    )
                if verification.replacement is not None:
                    self.counters.verifier_modified += 1
                    replacement_payload = verification.replacement.payload
                    if not isinstance(replacement_payload, WaypointGoal):
                        raise RouterViolation(
                            "a verifier may repair a waypoint into another waypoint, not into "
                            f"{replacement_payload.kind.value}"
                        )
                    effective = replacement_payload

            if self.planner is None:
                if not self.arch.unsafe_ablation:
                    raise RouterViolation(
                        "waypoint authority with no planner reached the router; the config "
                        "grammar should have rejected this architecture"
                    )
                trajectory = self._direct_line(effective, ctx)
            else:
                self.counters.plans_requested += 1
                trajectory = self.planner.plan(effective, ctx)
            if not trajectory.feasible:
                self.counters.plans_infeasible += 1
                return RoutingOutcome(
                    accepted=False,
                    reason=f"planner reported infeasible: {trajectory.reason}",
                    stale=stale,
                    decision_age_ns=age_ns,
                    verification=verification,
                    trajectory=trajectory,
                )
            self.source = _MotionSource(
                decision_id=envelope.decision_id,
                source_observation_seq=envelope.source_observation_seq,
                source_t_sim_ns=envelope.source_t_sim_ns,
                kind=DecisionKind.WAYPOINT,
                trajectory=trajectory,
                stop_when_done=effective.stop_at_target,
                was_stale=stale,
            )
            self.counters.executed += 1
            return RoutingOutcome(
                accepted=True,
                reason="waypoint planned",
                stale=stale,
                decision_age_ns=age_ns,
                verification=verification,
                trajectory=trajectory,
            )

        if isinstance(payload, KinematicAction):
            self._discard_pending_actions()
            self.source = _MotionSource(
                decision_id=envelope.decision_id,
                source_observation_seq=envelope.source_observation_seq,
                source_t_sim_ns=envelope.source_t_sim_ns,
                kind=DecisionKind.KINEMATIC_ACTION,
                actions=deque([payload]),
                action_expiry_ns=ctx.t_sim_ns + s_to_ns(payload.duration_s),
                was_stale=stale,
            )
            self.counters.executed += 1
            return RoutingOutcome(
                accepted=True, reason="action accepted", stale=stale, decision_age_ns=age_ns
            )

        if isinstance(payload, ActionChunk):
            self._discard_pending_actions()
            horizon = payload.actions
            if payload.replan_after is not None:
                horizon = horizon[: payload.replan_after]
            total_s = sum(a.duration_s for a in horizon)
            self.source = _MotionSource(
                decision_id=envelope.decision_id,
                source_observation_seq=envelope.source_observation_seq,
                source_t_sim_ns=envelope.source_t_sim_ns,
                kind=DecisionKind.ACTION_CHUNK,
                actions=deque(horizon),
                action_expiry_ns=ctx.t_sim_ns + s_to_ns(total_s),
                was_stale=stale,
            )
            self.counters.executed += 1
            return RoutingOutcome(
                accepted=True,
                reason=f"chunk of {len(horizon)} actions accepted",
                stale=stale,
                decision_age_ns=age_ns,
            )

        raise RouterViolation(f"no route defined for payload {type(payload).__name__}")

    def _discard_pending_actions(self) -> None:
        """A fresh inference supersedes whatever the last chunk had left."""
        if self.source is not None and self.source.actions:
            self.counters.chunk_actions_discarded += len(self.source.actions)

    def _direct_line(self, goal: WaypointGoal, ctx: DecisionContext) -> Trajectory:
        """Unplanned straight line, used only by declared unsafe ablations."""
        from uavlab.contracts.motion import TrajectoryPoint

        return Trajectory(
            start_t_sim_ns=ctx.t_sim_ns,
            points=(TrajectoryPoint(t_offset_ns=0, position=goal.target),),
            planner_name="none(unsafe_ablation)",
            feasible=True,
        )

    # -- issuing motion -----------------------------------------------------

    def command_for_tick(
        self, ctx: DecisionContext
    ) -> tuple[ControlCommand, SafetyDecision | None, int | None]:
        """Produce the command for this control tick, shielded.

        Returns ``(command, safety_decision, decision_age_ns)``. The age is
        measured *now*, at execution, which is the number that actually
        describes how obsolete the world was when the vehicle moved.
        """
        command = self._raw_command(ctx)
        age_ns = command.decision_age_ns(ctx.t_sim_ns)

        if age_ns is not None:
            self.counters.decision_age_ns_total += age_ns
            self.counters.decision_age_samples += 1
            if age_ns > self.max_age_ns:
                self.counters.stale_commands_executed += 1

        safety: SafetyDecision | None = None
        if self.shield is not None:
            command, safety = self.shield.check(command, ctx)
            match safety.verdict:
                case SafetyVerdict.ACCEPT:
                    self.counters.safety_accept += 1
                case SafetyVerdict.MODIFY:
                    self.counters.safety_modify += 1
                case SafetyVerdict.REJECT:
                    self.counters.safety_reject += 1
                case SafetyVerdict.STOP:
                    self.counters.safety_stop += 1
                    self.stop_requested = True
                    self.stop_reason = f"safety shield: {safety.reason}"

        self.counters.commands_issued += 1
        return command, safety, age_ns

    def _raw_command(self, ctx: DecisionContext) -> ControlCommand:
        src = self.source
        if src is None:
            return self.controller.hold(ctx)

        if src.kind in (DecisionKind.KINEMATIC_ACTION, DecisionKind.ACTION_CHUNK):
            if src.action_expiry_ns is not None and ctx.t_sim_ns >= src.action_expiry_ns:
                # The learned intent has run out; hold rather than extrapolate.
                if src.actions:
                    self.counters.chunk_actions_discarded += len(src.actions)
                    src.actions.clear()
                return self._stamp(self.controller.hold(ctx), src)
            action = src.actions[0] if src.actions else None
            if action is None:
                return self._stamp(self.controller.hold(ctx), src)
            command = self.controller.from_action(action, ctx, src.decision_id)
            self.counters.chunk_actions_executed += 1
            if len(src.actions) > 1:
                # Consume one step per control tick under a receding horizon.
                src.actions.popleft()
            return self._stamp(command, src)

        if src.trajectory is not None:
            command = self.controller.track(src.trajectory, ctx)
            if src.stop_when_done and self._trajectory_complete(src, ctx):
                self.stop_requested = True
                self.stop_reason = "waypoint reached with stop_at_target"
            return self._stamp(command, src)

        return self.controller.hold(ctx)

    def _trajectory_complete(self, src: _MotionSource, ctx: DecisionContext) -> bool:
        traj = src.trajectory
        if traj is None or not traj.points:
            return False
        final = traj.points[-1].position
        return ctx.observation.position.distance_to(final) <= 1.0

    @staticmethod
    def _stamp(command: ControlCommand, src: _MotionSource) -> ControlCommand:
        """Attach provenance so every command can be traced to its observation."""
        return command.model_copy(
            update={
                "source_decision_id": src.decision_id,
                "source_observation_seq": src.source_observation_seq,
                "source_t_sim_ns": src.source_t_sim_ns,
            }
        )

    # -- introspection ------------------------------------------------------

    @property
    def active_kind(self) -> DecisionKind | None:
        return self.source.kind if self.source else None

    def hold_command(self, ctx: DecisionContext) -> ControlCommand:
        return ControlCommand(t_sim_ns=ctx.t_sim_ns, velocity=Vec3(x=0.0, y=0.0, z=0.0))
