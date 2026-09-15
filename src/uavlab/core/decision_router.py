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
import math
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
from uavlab.core.skills import InvalidSkillArguments, SkillRuntime, UnknownSkillError
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
class _TargetCommitment:
    """Already verified semantic goal; execution lease does not refresh its image."""

    goal: WaypointGoal
    source: _MotionSource
    deadline_ns: int | None = None


@dataclass(slots=True)
class _FixedReorientation:
    """Bounded monitor-triggered executive action, not semantic motor output."""

    target_yaw_rad: float
    hold_until_ns: int
    expires_ns: int
    max_yaw_rate_rps: float
    settled: bool = False
    source_id: str = "onfly-lost-reorientation"
    resume_on_heading: bool = False


@dataclass(slots=True)
class RouterCounters:
    proposed: int = 0
    executed: int = 0
    rejected_stale: int = 0
    verifier_rejected: int = 0
    fence_recoveries: int = 0
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
    target_commitment_commands: int = 0
    stale_commands_rejected: int = 0
    decision_age_ns_total: int = 0
    decision_age_samples: int = 0
    unknown_skill: int = 0
    invalid_skill_args: int = 0

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
        verifier_params = arch.verifier.params if arch.verifier else {}
        self.fence_recovery = bool(verifier_params.get("fence_recovery", False))
        self.fence_rejection_limit = int(verifier_params.get("fence_rejection_limit", 3))
        self.fence_yaw_rate_rps = float(verifier_params.get("fence_yaw_rate_rps", 0.4))
        if self.fence_recovery and (
            self.fence_rejection_limit < 1
            or not math.isfinite(self.fence_yaw_rate_rps)
            or self.fence_yaw_rate_rps <= 0
        ):
            raise ValueError("fence recovery needs a positive rejection limit and yaw rate")
        monitor_params = arch.monitor.params if arch.monitor else {}
        self.fresh_after_lost_reorientation = bool(
            monitor_params.get("fresh_after_lost_reorientation", False)
        )
        self.target_commitment_s = float(arch.policy.params.get("target_commitment_s", 0.0))
        if not math.isfinite(self.target_commitment_s) or not 0 <= self.target_commitment_s <= 20:
            raise ValueError("target_commitment_s must be finite and in [0,20]")
        if self.target_commitment_s and (
            arch.policy.name != "onfly_decision" or arch.planner is None
            or arch.planner.name != "super_local" or arch.verifier is None
            or not arch.policy.params.get("grounded_waypoints", False)
        ):
            raise ValueError("target commitment requires grounded OnFly, verifier and SUPER")
        self._target_commitment: _TargetCommitment | None = None
        self._fence_rejections = 0
        self._fresh_after_reorientation_ns = -1
        self.max_age_ns = s_to_ns(arch.staleness.max_decision_age_s)
        self.reject_stale = arch.staleness.reject_stale

        self.source: _MotionSource | None = None
        self._reorientation: _FixedReorientation | None = None
        self.counters = RouterCounters()
        self.stop_requested: bool = False
        self.stop_reason: str = ""
        self.last_directive: MissionDirective | None = None

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self.source = None
        self._target_commitment = None
        self._reorientation = None
        self._fence_rejections = 0
        self._fresh_after_reorientation_ns = -1
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
        if self.fence_reorientation_active:
            return RoutingOutcome(accepted=False, reason="bounded fence reorientation active")
        if envelope.source_t_sim_ns <= self._fresh_after_reorientation_ns:
            return RoutingOutcome(
                accepted=False, reason="fresh observation required after recovery turn"
            )
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
            except InvalidSkillArguments as exc:
                self.counters.invalid_skill_args += 1
                return RoutingOutcome(
                    accepted=False,
                    reason=f"invalid skill arguments: {exc}",
                    decision_age_ns=age_ns,
                )
            if isinstance(expanded, MissionDirective):
                return self._accept_directive(expanded, envelope, age_ns, stale)
            # The semantic verifier validates the expanded typed result rather
            # than the wrapper SkillCall. Otherwise an out-of-bounds `goto`
            # would bypass the very AerialClaw-style runtime checks C1 declares.
            expanded_envelope = envelope.model_copy(
                update={"kind": expanded.kind, "payload": expanded}
            )
            outcome = self._accept_motion(expanded, expanded_envelope, ctx, age_ns, stale)
            outcome.expanded_kind = expanded.kind
            return outcome

        if (
            isinstance(payload, WaypointGoal)
            and envelope.provenance.get("waypoint_kind") == "exploration"
            and self.target_commitment_active(ctx, activate=True)
        ):
            return self._continue_target_commitment(ctx, age_ns)
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
                    self._consider_fence_recovery(verification, ctx)
                    return RoutingOutcome(
                        accepted=False,
                        reason=f"verifier rejected: {verification.reason}",
                        stale=stale,
                        decision_age_ns=age_ns,
                        verification=verification,
                    )
                self._fence_rejections = 0
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
            if effective.view_yaw_rad is not None:
                trajectory = trajectory.model_copy(update={"metadata": {
                    **trajectory.metadata,
                    "view_yaw_rad": str(effective.view_yaw_rad),
                    "view_position": ",".join(str(v) for v in (
                        effective.target.x, effective.target.y, effective.target.z)),
                    "view_tolerance_m": str(effective.tolerance_m),
                }})
            self.source = _MotionSource(
                decision_id=envelope.decision_id,
                source_observation_seq=envelope.source_observation_seq,
                source_t_sim_ns=envelope.source_t_sim_ns,
                kind=DecisionKind.WAYPOINT,
                trajectory=trajectory,
                stop_when_done=effective.stop_at_target,
                was_stale=stale,
            )
            self._target_commitment = None
            if (self.target_commitment_s and effective.target_label == "target"
                    and envelope.provenance.get("waypoint_kind") == "target"):
                self._target_commitment = _TargetCommitment(effective, self.source)
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

    @property
    def reorientation_active(self) -> bool:
        return self._reorientation is not None

    @property
    def fence_reorientation_active(self) -> bool:
        return self._reorientation is not None and self._reorientation.resume_on_heading

    def _consider_fence_recovery(self, result: VerificationResult, ctx: DecisionContext) -> None:
        if not self.fence_recovery:
            return
        self._fence_rejections = self._fence_rejections + 1 if result.code == "geofence" else 0
        if self._fence_rejections < self.fence_rejection_limit or self.reorientation_active:
            return
        position = ctx.observation.position
        # Same ENU fence origin as the verifier; no target location is involved.
        if math.hypot(position.x, position.y) < 1e-6:
            return
        target_yaw = math.atan2(-position.y, -position.x)
        error = math.atan2(
            math.sin(target_yaw - ctx.observation.yaw_rad),
            math.cos(target_yaw - ctx.observation.yaw_rad),
        )
        self.begin_fixed_reorientation(
            target_yaw_rad=target_yaw,
            t_sim_ns=ctx.t_sim_ns,
            hold_s=0.25,
            max_duration_s=abs(error) / self.fence_yaw_rate_rps + 2.0,
            yaw_rate_rps=self.fence_yaw_rate_rps,
            resume_on_heading=True,
        )
        self._fence_rejections = 0
        self.counters.fence_recoveries += 1

    def begin_fixed_reorientation(
        self,
        *,
        target_yaw_rad: float,
        t_sim_ns: int,
        hold_s: float,
        max_duration_s: float,
        yaw_rate_rps: float,
        resume_on_heading: bool = False,
    ) -> None:
        """Cancel translation, pause, then rotate toward a known heading.

        This is a fixed executive response to a monitor verdict. The monitor
        does not author a velocity, waypoint, or trajectory, so waypoint-level
        semantic authority remains unchanged and the output still passes
        through the shared controller/shield path.
        """
        self.source = None
        self._reorientation = _FixedReorientation(
            target_yaw_rad=math.atan2(math.sin(target_yaw_rad), math.cos(target_yaw_rad)),
            hold_until_ns=t_sim_ns + s_to_ns(max(0.0, hold_s)),
            expires_ns=t_sim_ns + s_to_ns(max(max_duration_s, hold_s, 0.05)),
            max_yaw_rate_rps=max(0.05, abs(yaw_rate_rps)),
            resume_on_heading=resume_on_heading,
            source_id="fence-reorientation" if resume_on_heading else "onfly-lost-reorientation",
        )

    def cancel_fixed_reorientation(self) -> None:
        self._reorientation = None

    def _fixed_reorientation_command(self, ctx: DecisionContext) -> ControlCommand | None:
        recovery = self._reorientation
        if recovery is None:
            return None
        # Recovery is deliberately bounded. Checking the deadline before the
        # settled branch prevents a perfect yaw alignment from becoming an
        # infinite hover when positional occlusion makes visual reacquisition
        # impossible from the recovered viewpoint.
        if ctx.t_sim_ns >= recovery.expires_ns:
            if recovery.resume_on_heading or self.fresh_after_lost_reorientation:
                self.source = None
                self._fresh_after_reorientation_ns = ctx.t_sim_ns
            self._reorientation = None
            return self.controller.hold(ctx).model_copy(
                update={"metadata": {"recovery": "reorientation_expired"}}
            )
        if ctx.t_sim_ns < recovery.hold_until_ns:
            return self.controller.hold(ctx).model_copy(
                update={"metadata": {"recovery": "lost_hold"}}
            )
        error = math.atan2(
            math.sin(recovery.target_yaw_rad - ctx.observation.yaw_rad),
            math.cos(recovery.target_yaw_rad - ctx.observation.yaw_rad),
        )
        if recovery.settled or abs(error) <= math.radians(5.0):
            if recovery.resume_on_heading:
                self._reorientation = None
                self.source = None
                self._fresh_after_reorientation_ns = ctx.t_sim_ns
                return self.controller.hold(ctx).model_copy(
                    update={"metadata": {"recovery": "fence_turn_complete"}}
                )
            # Keep the recovered viewpoint fixed until the next semantic
            # monitor result explicitly confirms reacquisition.  Resuming a
            # stale waypoint for the gap between monitor ticks immediately
            # undoes the recovery turn.
            recovery.settled = True
            return self.controller.hold(ctx).model_copy(
                update={"metadata": {"recovery": "awaiting_reacquisition"}}
            )
        yaw_rate = max(
            -recovery.max_yaw_rate_rps,
            min(recovery.max_yaw_rate_rps, error * 1.5),
        )
        action = KinematicAction(
            velocity=Vec3(x=0.0, y=0.0, z=0.0),
            yaw_rate_rps=yaw_rate,
            duration_s=0.1,
        )
        return self.controller.from_action(action, ctx, recovery.source_id).model_copy(
            update={
                "metadata": {
                    "recovery": "fence_reorientation"
                    if recovery.resume_on_heading
                    else "lost_reorientation"
                }
            }
        )

    def command_for_tick(
        self, ctx: DecisionContext
    ) -> tuple[ControlCommand, SafetyDecision | None, int | None]:
        """Produce the command for this control tick, shielded.

        Returns ``(command, safety_decision, decision_age_ns)``. The age is
        measured *now*, at execution, which is the number that actually
        describes how obsolete the world was when the vehicle moved.
        """
        target_lease_active = self.target_commitment_active(ctx)
        fixed_reorientation = self._fixed_reorientation_command(ctx)

        # Check the authoritative source *before* asking the controller to
        # derive another command from it.  Admission-time rejection is not
        # enough: a once-fresh trajectory can remain authoritative for many
        # control ticks and become stale during execution.
        source = self.source
        source_age_ns = ctx.t_sim_ns - source.source_t_sim_ns if source is not None else None
        reject_source = (
            source_age_ns is not None
            and source_age_ns > self.max_age_ns
            and self.reject_stale
            and not target_lease_active
        )

        if fixed_reorientation is not None:
            command = fixed_reorientation
            age_ns = None
        elif reject_source:
            self.source = None
            self.counters.stale_commands_rejected += 1
            command = self.controller.hold(ctx)
            age_ns = source_age_ns
        else:
            command = self._raw_command(ctx)
            age_ns = command.decision_age_ns(ctx.t_sim_ns)

        if age_ns is not None:
            self.counters.decision_age_ns_total += age_ns
            self.counters.decision_age_samples += 1
            if target_lease_active:
                self.counters.target_commitment_commands += 1
            elif age_ns > self.max_age_ns and not reject_source:
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
        # Receding-horizon safety planners such as SUPER deliberately end a
        # commitment at a known-free stopping point before the semantic goal.
        # Reaching that backup endpoint is not mission completion. Legacy
        # planners omit the field and retain the old final-point semantics.
        if traj.metadata.get("reaches_goal", "true") != "true":
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

    # -- named bounded accepted-target execution variant --------------------

    def _end_target_commitment(self) -> None:
        lease = self._target_commitment
        if (lease is not None and lease.deadline_ns is not None and self.source is not None
                and self.source.decision_id == lease.source.decision_id):
            self.source = None
        self._target_commitment = None

    def target_commitment_active(self, ctx: DecisionContext, *, activate: bool = False) -> bool:
        """Arbitrate LOST yaw and exploration without inventing fresh target evidence."""
        lease = self._target_commitment
        if lease is None:
            return False
        if (self.stop_requested or self.source is None
                or self.source.decision_id != lease.source.decision_id
                or ctx.observation.position.distance_to(lease.goal.target)
                <= lease.goal.tolerance_m):
            self._end_target_commitment()
            return False
        if lease.deadline_ns is not None:
            if ctx.t_sim_ns >= lease.deadline_ns:
                self._end_target_commitment()
                return False
            return True
        if ctx.t_sim_ns - lease.source.source_t_sim_ns > self.max_age_ns:
            self._end_target_commitment()
            return False
        if activate and not self.reorientation_active:
            lease.deadline_ns = ctx.t_sim_ns + s_to_ns(self.target_commitment_s)
            return True
        return False

    def _continue_target_commitment(self, ctx: DecisionContext, age_ns: int) -> RoutingOutcome:
        lease = self._target_commitment
        assert lease is not None and lease.deadline_ns is not None and self.planner is not None
        self.counters.plans_requested += 1
        trajectory = self.planner.plan(lease.goal, ctx)
        trajectory = trajectory.model_copy(update={"metadata": {
            **trajectory.metadata,
            "target_commitment_source_id": lease.source.decision_id,
            "target_commitment_source_seq": str(lease.source.source_observation_seq),
            "target_commitment_source_t_ns": str(lease.source.source_t_sim_ns),
            "target_commitment_deadline_ns": str(lease.deadline_ns),
            "target_commitment_geometry_seq": str(ctx.observation.seq),
        }})
        if not trajectory.feasible:
            self.counters.plans_infeasible += 1
            self._end_target_commitment()
            return RoutingOutcome(accepted=False, decision_age_ns=age_ns, trajectory=trajectory,
                reason="target commitment ended: common planner found no feasible commitment")
        # Incoming exploration is NOT executed. Keep the original decision/image identity.
        self.source = dataclasses.replace(lease.source, trajectory=trajectory)
        return RoutingOutcome(accepted=False, decision_age_ns=age_ns, trajectory=trajectory,
            reason="target commitment retained: exploratory replacement deferred")

    # -- introspection ------------------------------------------------------

    @property
    def active_kind(self) -> DecisionKind | None:
        return self.source.kind if self.source else None

    def hold_command(self, ctx: DecisionContext) -> ControlCommand:
        return ControlCommand(t_sim_ns=ctx.t_sim_ns, velocity=Vec3(x=0.0, y=0.0, z=0.0))
