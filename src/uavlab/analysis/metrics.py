"""Per-episode metrics.

The rule this module exists to enforce: **no single architecture score**.  The
outputs form a capability vector and a compute vector, and the trade-off between
them stays visible.  Collapsing them into one number would hide exactly the
thing the study is looking for — that the best architecture is a function of
task regime, latency budget and compute budget, not a universal winner.

The metric worth singling out is decision staleness.  Inference latency alone
does not tell you how obsolete the world was when a decision finally executed,
and in an asynchronous architecture those are very different quantities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from uavlab.contracts.env_status import EnvironmentStatus
from uavlab.contracts.events import EventType
from uavlab.core.event_log import EventLog

if TYPE_CHECKING:  # pragma: no cover
    from uavlab.core.config import ArchitectureConfig
    from uavlab.core.decision_router import DecisionRouter
    from uavlab.core.feature_cache import FeatureCache
    from uavlab.core.scheduler import Scheduler


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile. No NumPy dependency in the metrics path."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = q / 100.0 * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def median(values: list[float]) -> float:
    return percentile(values, 50.0)


def compute_metrics(
    *,
    log: EventLog,
    router: DecisionRouter,
    scheduler: Scheduler,
    status: EnvironmentStatus,
    inference: Any,
    feature_cache: FeatureCache,
    sim_duration_ns: int,
    arch: ArchitectureConfig,
    reached_goal_t_ns: int | None,
    components: list[Any] | None = None,
) -> dict[str, float]:
    """Assemble the full metric vector for one episode."""
    sim_s = max(sim_duration_ns / 1e9, 1e-9)
    counters = router.counters

    # -- capability -------------------------------------------------------
    metrics: dict[str, float] = {
        "flight_time_s": sim_s,
        "path_length_m": status.path_length_m,
        "distance_to_goal_m": status.distance_to_goal_m,
        "collisions": float(status.collision_count),
        "collision_rate": 1.0 if status.collided else 0.0,
        "min_obstacle_distance_m": (
            status.min_obstacle_distance_m if status.min_obstacle_distance_m != float("inf") else -1.0
        ),
        "out_of_bounds": 1.0 if status.out_of_bounds else 0.0,
        "constraint_violations": float(status.constraint_violations),
        "subgoals_completed": float(status.subgoals_completed),
        "subgoal_completion": (
            status.subgoals_completed / status.subgoals_total if status.subgoals_total else 1.0
        ),
        "reached_goal": 1.0 if reached_goal_t_ns is not None else 0.0,
        "time_to_goal_s": (reached_goal_t_ns / 1e9) if reached_goal_t_ns is not None else -1.0,
    }
    metrics["path_efficiency"] = _spl(status)

    # -- semantic latency and staleness -----------------------------------
    inference_latencies = log.values(EventType.INFERENCE_CALL, "latency_s")
    decision_ages = [
        v for v in log.values(EventType.CONTROL, "decision_age_s") if v is not None
    ]
    production_latencies = log.values(EventType.DECISION_PROPOSED, "production_latency_s")

    metrics.update(
        {
            "semantic_latency_median_s": median(inference_latencies),
            "semantic_latency_p95_s": percentile(inference_latencies, 95.0),
            "decision_production_latency_median_s": median(production_latencies),
            "decision_age_median_s": median(decision_ages),
            "decision_age_p95_s": percentile(decision_ages, 95.0),
            "decision_age_max_s": max(decision_ages) if decision_ages else 0.0,
            "stale_action_rate": _ratio(
                counters.stale_commands_executed, counters.commands_issued
            ),
            "stale_rejection_rate": _ratio(counters.rejected_stale, counters.proposed),
        }
    )

    # -- control and plan health ------------------------------------------
    control_events = log.count(EventType.CONTROL)
    metrics.update(
        {
            "control_updates": float(control_events),
            "actual_control_hz": control_events / sim_s,
            "configured_control_hz": arch.scheduler.control_hz,
            "control_rate_fidelity": _ratio(
                control_events / sim_s, arch.scheduler.control_hz
            ),
            "decisions_proposed": float(counters.proposed),
            "decisions_executed": float(counters.executed),
            "executable_plan_rate": _ratio(
                counters.plans_requested - counters.plans_infeasible, counters.plans_requested
            ),
            "verifier_rejection_rate": _ratio(counters.verifier_rejected, counters.proposed),
            "verifier_repair_rate": _ratio(counters.verifier_modified, counters.proposed),
            "rejected_or_modified_proposal_rate": _ratio(
                counters.verifier_rejected + counters.verifier_modified + counters.rejected_stale,
                counters.proposed,
            ),
        }
    )

    # -- safety accounting -------------------------------------------------
    shield_actions = counters.safety_modify + counters.safety_reject + counters.safety_stop
    metrics.update(
        {
            "safety_interventions": float(shield_actions),
            "safety_intervention_rate": _ratio(shield_actions, counters.commands_issued),
            "safety_rejections": float(counters.safety_reject),
            "safety_stops": float(counters.safety_stop),
            "safety_modification_rate": _ratio(counters.safety_modify, counters.commands_issued),
        }
    )

    # -- supervision and recovery -----------------------------------------
    monitor_events = log.of_type(EventType.MONITOR)
    labels = [str(e.payload.get("label", "")) for e in monitor_events]
    metrics.update(
        {
            "monitor_assessments": float(len(monitor_events)),
            "monitor_stop_calls": float(labels.count("stop")),
            "monitor_lost_calls": float(labels.count("lost")),
            "monitor_blocked_calls": float(labels.count("blocked")),
            "recovery_triggers": float(log.count(EventType.RECOVERY_TRIGGER)),
            "recovery_decisions": float(log.count(EventType.RECOVERY_DECISION)),
        }
    )
    metrics.update(scheduler.stats())

    if status.task_complete is not None:
        metrics.update({f"task_{key}": value for key, value in status.extras.items()})

    # -- terminal-stop correctness ----------------------------------------
    # "Arrived" and "finished the mission" are different events, and only
    # architectures with supervision reliably turn the first into the second.
    goal_radius = status.extras.get("goal_radius_m", 2.0)
    within_goal = status.distance_to_goal_m <= goal_radius
    within_goal = within_goal if status.task_complete is None else status.task_complete
    stopped = router.stop_requested
    metrics["agent_stopped"] = 1.0 if stopped else 0.0
    metrics["correct_terminal_stop"] = 1.0 if (stopped and within_goal) else 0.0
    metrics["premature_stop"] = 1.0 if (stopped and not within_goal) else 0.0
    metrics["arrived_without_stopping"] = 1.0 if (within_goal and not stopped) else 0.0

    # Recovery is scored only where it was attempted; the aggregator filters on
    # ``recovery_attempted`` so episodes that never needed recovery cannot
    # inflate or deflate the rate.
    attempted = metrics["recovery_triggers"] > 0 or metrics["recovery_decisions"] > 0
    metrics["recovery_attempted"] = 1.0 if attempted else 0.0
    metrics["recovery_success"] = 1.0 if (attempted and within_goal) else 0.0

    # False-target commitment: measured by the environment from the true
    # geometry, because whether the vehicle committed to a decoy is a fact about
    # where it flew, not about what it reported believing.
    lure_dwell_s = status.extras.get("lure_dwell_s", 0.0)
    metrics["lure_dwell_s"] = lure_dwell_s
    metrics["false_target_commitment"] = 1.0 if lure_dwell_s >= 2.0 else 0.0

    # -- compute -----------------------------------------------------------
    if inference is not None and hasattr(inference, "stats"):
        metrics.update(inference.stats())
    # Any component may report its own counters. A real VLM's found/not-found
    # and parse-failure rates are the difference between "the architecture is
    # wrong" and "the model could not see the target", and without them the two
    # are indistinguishable in the results.
    for component in components or ():
        if component is not None and hasattr(component, "stats"):
            try:
                metrics.update(component.stats())
            except Exception:  # noqa: BLE001 - reporting must never fail a run
                pass
    metrics.update(feature_cache.stats.as_dict())
    metrics.update(counters.as_dict())
    metrics["peak_rss_mb"] = _peak_rss_mb()

    # Cost per outcome, kept as two numbers rather than a ratio-of-ratios so
    # that a Pareto plot can use either axis directly.
    metrics["reasoner_calls_per_minute"] = metrics.get("reasoner_calls", 0.0) / (sim_s / 60.0)
    metrics["tokens_per_minute"] = metrics.get("inference_tokens_total", 0.0) / (sim_s / 60.0)
    return metrics


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _spl(status: EnvironmentStatus) -> float:
    """Success-weighted path length, reported unweighted per episode.

    Weighting by success happens in the aggregation step, so a failed episode's
    path efficiency stays inspectable rather than being silently zeroed.
    """
    if status.path_length_m <= 0.0 or status.shortest_path_m <= 0.0:
        return 0.0
    return min(1.0, status.shortest_path_m / max(status.path_length_m, status.shortest_path_m))


def _peak_rss_mb() -> float:
    """Peak resident memory, best effort and never fatal."""
    try:  # pragma: no cover - platform dependent
        import resource

        usage = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Linux reports kilobytes; macOS reports bytes.
        return usage / (1024.0 * 1024.0) if usage > 1e9 else usage / 1024.0
    except ImportError:
        pass
    try:  # pragma: no cover - Windows
        import ctypes
        import ctypes.wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.wintypes.DWORD),
                ("PageFaultCount", ctypes.wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            return counters.PeakWorkingSetSize / (1024.0 * 1024.0)
    except Exception:  # noqa: BLE001 - memory reporting must never fail a run
        pass
    return 0.0


CAPABILITY_METRICS: tuple[str, ...] = (
    "success",
    "collision_rate",
    "correct_terminal_stop",
    "recovery_success",
    "subgoal_completion",
    "path_efficiency",
    "executable_plan_rate",
    "false_target_commitment",
)

COST_METRICS: tuple[str, ...] = (
    "semantic_latency_median_s",
    "semantic_latency_p95_s",
    "actual_control_hz",
    "decision_age_median_s",
    "peak_rss_mb",
    "reasoner_calls",
    "inference_tokens_total",
    "stale_action_rate",
)
"""The two halves of the Pareto surface, named so plots cannot drift from them."""
