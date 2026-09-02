"""One scheduler, four interchangeable policies.

Scheduling is a first-class plugin because *when* expensive reasoning runs is
one of the study's axes.  If each policy implementation built its own private
timer, then C4, C6, C10, C12 and C13 would differ in implementation quality as
well as in architecture, and no amount of careful analysis afterwards could
separate the two.

The distinction that matters most here is inline versus concurrent.  Under a
periodic hierarchy a slow reasoner *blocks* the fast executor; under a
multi-rate policy it runs beside it and the executor keeps flying on a slightly
older intent.  That is precisely the C10 versus C12 contrast, so it is
represented structurally rather than by tuning a rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from uavlab.contracts.common import ProgressLabel, s_to_ns
from uavlab.contracts.perception import PerceptionState
from uavlab.contracts.progress import ProgressState
from uavlab.core.clock import SimClock
from uavlab.core.config import SchedulerKind, SchedulerSpec


@dataclass(slots=True)
class RoleSchedule:
    """How one concurrently schedulable role is driven."""

    role: str
    period_ns: int | None = None
    concurrent: bool = True
    """False means the role is invoked inline by the decision loop and blocks it."""
    every_n_decisions: int = 1
    """Inline roles run on every n-th decision tick."""
    triggered: bool = False
    next_deadline_ns: int | None = field(default=None, repr=False)
    """Next start-time deadline for concurrent periodic execution."""


@dataclass(slots=True)
class TriggerGate:
    """Admission control for event-triggered reasoning.

    Keeps the cost side honest: a trigger that fires constantly is not
    "selective invocation", and the budget makes that visible in the logs
    instead of only in the latency numbers.
    """

    name: str
    cooldown_ns: int
    max_calls: int | None = None
    calls: int = 0
    last_fired_ns: int | None = None
    suppressed: int = 0
    _armed_reason: str | None = field(default=None, repr=False)

    def condition_met(
        self,
        progress: ProgressState | None,
        perception: PerceptionState | None,
        stall_threshold_s: float,
        uncertainty_threshold: float,
    ) -> str | None:
        """Evaluate the named trigger, returning a cause string or ``None``."""
        match self.name:
            case "never":
                return None
            case "always":
                return "always"
            case "no_progress":
                if progress is not None and progress.stalled_for_s >= stall_threshold_s:
                    return f"stalled_for_s={progress.stalled_for_s:.2f}"
                return None
            case "blocked":
                if progress is not None and progress.label is ProgressLabel.BLOCKED:
                    return "monitor reported blocked"
                return None
            case "high_uncertainty":
                if perception is not None and perception.uncertainty >= uncertainty_threshold:
                    return f"uncertainty={perception.uncertainty:.2f}"
                return None
            case "ambiguous":
                if progress is not None and progress.label is ProgressLabel.AMBIGUOUS:
                    return "monitor reported ambiguous"
                return None
            case "no_progress_or_ambiguity":
                causes: list[str] = []
                if progress is not None:
                    if progress.stalled_for_s >= stall_threshold_s:
                        causes.append(f"stalled_for_s={progress.stalled_for_s:.2f}")
                    if progress.label in (
                        ProgressLabel.BLOCKED,
                        ProgressLabel.LOST,
                        ProgressLabel.AMBIGUOUS,
                    ):
                        causes.append(f"label={progress.label.value}")
                if perception is not None and perception.uncertainty >= uncertainty_threshold:
                    causes.append(f"uncertainty={perception.uncertainty:.2f}")
                return "; ".join(causes) or None
        raise ValueError(f"unknown trigger {self.name!r}")

    def admit(self, t_sim_ns: int, cause: str | None) -> str | None:
        """Apply cooldown and budget. Returns the admitted cause, or ``None``."""
        if cause is None:
            return None
        if self.max_calls is not None and self.calls >= self.max_calls:
            self.suppressed += 1
            return None
        if self.last_fired_ns is not None and t_sim_ns - self.last_fired_ns < self.cooldown_ns:
            self.suppressed += 1
            return None
        self.calls += 1
        self.last_fired_ns = t_sim_ns
        return cause

    def stats(self) -> dict[str, float]:
        return {
            "trigger_calls": float(self.calls),
            "trigger_suppressed": float(self.suppressed),
        }


class Scheduler:
    """Turns a :class:`SchedulerSpec` into concrete role schedules."""

    def __init__(self, spec: SchedulerSpec, clock: SimClock) -> None:
        self.spec = spec
        self.clock = clock
        self.gate: TriggerGate | None = None
        if spec.trigger:
            self.gate = TriggerGate(
                name=spec.trigger,
                cooldown_ns=s_to_ns(spec.cooldown_s),
                max_calls=spec.max_calls,
            )

    # -- schedule construction ---------------------------------------------

    def build(self, *, has_monitor: bool, has_recovery: bool) -> list[RoleSchedule]:
        spec = self.spec
        schedules = [
            RoleSchedule("control", period_ns=s_to_ns(1.0 / spec.control_hz)),
            RoleSchedule("decision", period_ns=s_to_ns(1.0 / spec.decision_hz)),
        ]

        monitor_period = s_to_ns(1.0 / spec.monitor_hz) if spec.monitor_hz else None
        reasoner_period = s_to_ns(1.0 / spec.reasoner_hz) if spec.reasoner_hz else None

        match spec.kind:
            case SchedulerKind.PERIODIC:
                # Everything shares the decision loop's thread of control: a slow
                # reasoner blocks the fast executor, which is the point.
                if has_monitor and monitor_period is not None:
                    schedules.append(
                        RoleSchedule(
                            "monitor",
                            period_ns=monitor_period,
                            concurrent=False,
                            every_n_decisions=self._ratio(spec.decision_hz, spec.monitor_hz),
                        )
                    )
                if has_recovery and reasoner_period is not None:
                    schedules.append(
                        RoleSchedule(
                            "reasoner",
                            period_ns=reasoner_period,
                            concurrent=False,
                            every_n_decisions=self._ratio(spec.decision_hz, spec.reasoner_hz),
                        )
                    )
            case SchedulerKind.ASYNC_MULTI_RATE:
                if has_monitor and monitor_period is not None:
                    schedules.append(RoleSchedule("monitor", period_ns=monitor_period))
                if has_recovery and reasoner_period is not None:
                    schedules.append(RoleSchedule("reasoner", period_ns=reasoner_period))
            case SchedulerKind.EVENT_TRIGGERED:
                if has_recovery:
                    schedules.append(
                        RoleSchedule(
                            "trigger",
                            period_ns=s_to_ns(1.0 / spec.trigger_check_hz),
                            triggered=True,
                        )
                    )
                if has_monitor and monitor_period is not None:
                    schedules.append(RoleSchedule("monitor", period_ns=monitor_period))
            case SchedulerKind.HYBRID:
                if has_monitor and monitor_period is not None:
                    schedules.append(RoleSchedule("monitor", period_ns=monitor_period))
                if has_recovery and reasoner_period is not None:
                    schedules.append(RoleSchedule("reasoner", period_ns=reasoner_period))
                if has_recovery and spec.trigger:
                    schedules.append(
                        RoleSchedule(
                            "trigger",
                            period_ns=s_to_ns(1.0 / spec.trigger_check_hz),
                            triggered=True,
                        )
                    )
        # Loops do their work before calling ``tick``.  Establish the first
        # deadline here (rather than on the first tick after inference) so the
        # configured period is start-to-start, not compute-time-plus-period.
        epoch_ns = self.clock.now_ns()
        for schedule in schedules:
            if schedule.period_ns is not None:
                schedule.next_deadline_ns = epoch_ns + schedule.period_ns
        return schedules

    @staticmethod
    def _ratio(fast_hz: float, slow_hz: float | None) -> int:
        if not slow_hz or slow_hz <= 0:
            return 1
        return max(1, round(fast_hz / slow_hz))

    # -- driving ------------------------------------------------------------

    async def tick(self, schedule: RoleSchedule) -> None:
        """Wait until this role's next start-time deadline.

        A slow model call must not be followed by a *second* full-period wait.
        If work finishes before its deadline, sleep only the remaining time.
        If it overruns, let the next invocation start immediately and rebase
        the following deadline from that start.  Rebasing avoids catch-up
        bursts after a large overrun while preserving maximum attainable rate.
        """
        if schedule.period_ns is None:
            raise ValueError(f"role {schedule.role!r} has no period to wait on")
        now_ns = self.clock.now_ns()
        deadline_ns = schedule.next_deadline_ns
        if deadline_ns is None:
            # Defensive fallback for a manually constructed RoleSchedule. The
            # normal path initializes deadlines in ``build`` before work starts.
            deadline_ns = now_ns + schedule.period_ns

        if now_ns < deadline_ns:
            await self.clock.sleep_ns(deadline_ns - now_ns, role=schedule.role)
            schedule.next_deadline_ns = deadline_ns + schedule.period_ns
        else:
            schedule.next_deadline_ns = now_ns + schedule.period_ns

    def stats(self) -> dict[str, float]:
        return self.gate.stats() if self.gate else {}
