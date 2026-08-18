"""Progress monitors.

A monitor answers a different question from the policy.  The policy asks "where
do I go next?"; the monitor asks "is this mission still going anywhere?".  That
separation is the reason a monitor can improve stopping correctness and
lost-task detection without touching steering at all, and it is why the monitor
is scheduled independently rather than folded into the decision loop.

The monitor emits :class:`ProgressState` and nothing else.  It has no motor
authority whatsoever.
"""

from __future__ import annotations

from typing import Any

from uavlab.contracts import MissionSpec, ProgressLabel, ProgressState, Vec3, ns_to_s
from uavlab.core.registry import register
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import DecisionContext, InferenceRequest
from uavlab.plugins.reasoning.base import recall_target


@register("monitor", "progress")
class ProgressMonitor:
    """Distance-trend supervision over the mission's own memory.

    Deliberately built on the *semantic* memory snapshot rather than on
    ground truth: a monitor that could see the true goal would flatter every
    architecture it was attached to, and the C4->C5 memory contrast would
    become meaningless.
    """

    def __init__(self, **params: Any) -> None:
        self.model_id = str(params.get("model_id", "sim-monitor"))
        self.target_label = str(params.get("target_label", "target"))
        self.arrival_radius_m = float(params.get("arrival_radius_m", 2.0))
        self.progress_epsilon_m = float(params.get("progress_epsilon_m", 0.5))
        self.lost_after_s = float(params.get("lost_after_s", 8.0))
        self.stop_confirmations = int(params.get("stop_confirmations", 2))
        """Consecutive arrival assessments required before calling STOP.

        One noisy frame should not end a mission; this is the monitor's whole
        advantage over a policy that stops on instantaneous evidence.
        """
        self.blocked_clearance_m = float(params.get("blocked_clearance_m", 1.5))
        self.ambiguity_margin = float(params.get("ambiguity_margin", 0.12))
        self.use_memory = bool(params.get("use_memory", True))

        self.services: RuntimeServices | None = None
        self._best_distance = float("inf")
        self._last_progress_t_ns = 0
        self._last_evidence_t_ns = 0
        self._arrivals = 0
        self._assessments = 0
        self._stopped = False

    @property
    def name(self) -> str:
        return "progress"

    def bind_runtime(self, services: RuntimeServices) -> None:
        self.services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self.arrival_radius_m = mission.success.goal_radius_m
        self._best_distance = float("inf")
        self._last_progress_t_ns = 0
        self._last_evidence_t_ns = 0
        self._arrivals = 0
        self._assessments = 0
        self._stopped = False

    async def assess(self, ctx: DecisionContext) -> ProgressState:
        if self.services is not None and self.services.inference is not None:
            await self.services.inference.invoke(
                InferenceRequest(
                    model_id=self.model_id,
                    role="monitor",
                    prompt_hash=f"monitor:{ctx.observation.seq}",
                    input_tokens=96 + ctx.memory.tokens_used,
                    image_count=1,
                    observation_seq=ctx.observation.seq,
                )
            )

        self._assessments += 1
        now = ctx.t_sim_ns
        target = self._target(ctx)

        if target is None:
            stalled_s = ns_to_s(now - self._last_evidence_t_ns)
            if stalled_s >= self.lost_after_s:
                return self._state(
                    ProgressLabel.LOST,
                    ctx,
                    confidence=0.7,
                    evidence=f"no target evidence for {stalled_s:.1f}s",
                    stalled_for_s=stalled_s,
                )
            return self._state(
                ProgressLabel.CONTINUE,
                ctx,
                confidence=0.4,
                evidence="searching; no target evidence yet",
                stalled_for_s=stalled_s,
            )

        self._last_evidence_t_ns = now
        distance = ctx.observation.position.distance_to(target)

        if distance < self._best_distance - self.progress_epsilon_m:
            self._best_distance = distance
            self._last_progress_t_ns = now
        stalled_s = ns_to_s(now - self._last_progress_t_ns)

        if distance <= self.arrival_radius_m:
            self._arrivals += 1
            if self._arrivals >= self.stop_confirmations and not self._stopped:
                self._stopped = True
                return self._state(
                    ProgressLabel.STOP,
                    ctx,
                    confidence=0.9,
                    evidence=f"within {distance:.2f} m of target on "
                    f"{self._arrivals} consecutive assessments",
                    distance=distance,
                    stalled_for_s=stalled_s,
                )
        else:
            self._arrivals = 0

        if self._is_ambiguous(ctx):
            return self._state(
                ProgressLabel.AMBIGUOUS,
                ctx,
                confidence=0.5,
                evidence="multiple candidate targets with similar scores",
                distance=distance,
                stalled_for_s=stalled_s,
            )

        geometry = ctx.perception.geometry
        clearance = geometry.free_radius_m if geometry else float("inf")
        if clearance < self.blocked_clearance_m and stalled_s > 1.0:
            return self._state(
                ProgressLabel.BLOCKED,
                ctx,
                confidence=0.8,
                evidence=f"clearance {clearance:.2f} m and no progress for {stalled_s:.1f}s",
                distance=distance,
                stalled_for_s=stalled_s,
            )

        return self._state(
            ProgressLabel.CONTINUE,
            ctx,
            confidence=0.8,
            evidence=f"{distance:.1f} m to target, best {self._best_distance:.1f} m",
            distance=distance,
            stalled_for_s=stalled_s,
        )

    def _target(self, ctx: DecisionContext) -> Vec3 | None:
        for det in ctx.perception.detections:
            if det.label == self.target_label and det.position is not None:
                return det.position
        if not self.use_memory:
            return None
        remembered = recall_target(ctx, self.target_label)
        return remembered.position if remembered else None

    def _is_ambiguous(self, ctx: DecisionContext) -> bool:
        scores = sorted(
            (d.score for d in ctx.perception.detections if d.label == self.target_label),
            reverse=True,
        )
        return len(scores) >= 2 and (scores[0] - scores[1]) < self.ambiguity_margin

    def _state(
        self,
        label: ProgressLabel,
        ctx: DecisionContext,
        *,
        confidence: float,
        evidence: str,
        distance: float | None = None,
        stalled_for_s: float = 0.0,
    ) -> ProgressState:
        return ProgressState(
            label=label,
            observation_seq=ctx.observation.seq,
            t_sim_ns=ctx.t_sim_ns,
            confidence=confidence,
            evidence=evidence,
            distance_to_goal_m=distance,
            stalled_for_s=stalled_for_s,
            monitor_name=self.name,
        )


@register("monitor", "local_progress")
class LocalProgressDetector:
    """A cheap, non-semantic progress detector.

    Purely geometric: distance travelled over a window, plus forward clearance.
    It costs no inference at all, which is exactly the point — an
    event-triggered architecture needs *something* watching in order to know
    when to wake the expensive reasoner, and if that something were itself a
    model call, the architecture would no longer be "reasoning absent during
    nominal execution".

    It cannot judge semantics, so it never emits STOP.  Deciding that a mission
    is finished requires understanding the mission, and this component does not.
    """

    def __init__(self, **params: Any) -> None:
        self.window_s = float(params.get("window_s", 3.0))
        self.min_travel_m = float(params.get("min_travel_m", 1.0))
        self.blocked_clearance_m = float(params.get("blocked_clearance_m", 1.8))
        self._history: list[tuple[int, Vec3]] = []

    @property
    def name(self) -> str:
        return "local_progress"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._history = []

    async def assess(self, ctx: DecisionContext) -> ProgressState:
        now = ctx.t_sim_ns
        self._history.append((now, ctx.observation.position))
        cutoff = now - int(self.window_s * 1e9)
        self._history = [(t, p) for t, p in self._history if t >= cutoff]

        travelled = 0.0
        for (_, a), (_, b) in zip(self._history, self._history[1:], strict=False):
            travelled += a.distance_to(b)

        span_s = ns_to_s(now - self._history[0][0]) if self._history else 0.0
        stalled = span_s >= self.window_s and travelled < self.min_travel_m
        geometry = ctx.perception.geometry
        clearance = geometry.free_radius_m if geometry else float("inf")

        if stalled and clearance < self.blocked_clearance_m:
            label, evidence = ProgressLabel.BLOCKED, (
                f"moved {travelled:.2f} m in {span_s:.1f} s with {clearance:.2f} m clearance"
            )
        elif stalled:
            label, evidence = ProgressLabel.CONTINUE, (
                f"moved only {travelled:.2f} m in {span_s:.1f} s"
            )
        else:
            label, evidence = ProgressLabel.CONTINUE, f"moved {travelled:.2f} m in {span_s:.1f} s"

        return ProgressState(
            label=label,
            observation_seq=ctx.observation.seq,
            t_sim_ns=now,
            confidence=1.0,
            evidence=evidence,
            stalled_for_s=span_s if stalled else 0.0,
            monitor_name=self.name,
        )


@register("monitor", "implicit")
class ImplicitMonitor:
    """No independent supervision; always reports CONTINUE.

    Present so that "this architecture has no monitor" is a configured
    component with a stated cost of zero, rather than a hole in the config.
    """

    def __init__(self, **params: Any) -> None:
        pass

    @property
    def name(self) -> str:
        return "implicit"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        return None

    async def assess(self, ctx: DecisionContext) -> ProgressState:
        return ProgressState(
            label=ProgressLabel.CONTINUE,
            observation_seq=ctx.observation.seq,
            t_sim_ns=ctx.t_sim_ns,
            confidence=0.0,
            evidence="no independent monitor",
            monitor_name="implicit",
        )
