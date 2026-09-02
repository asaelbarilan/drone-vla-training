"""Learned Cognitive Value of Invocation gate from PMR.

The paper does not publish its fitted weights or normalizers.  This plugin
therefore requires an explicit locally trained checkpoint and fails closed
when it is absent; a hand-written score must never be presented as learned-CVI.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from uavlab.contracts import (
    AdmissionDecision,
    AdmissionRuntime,
    MissionSpec,
    ProgressLabel,
    WaypointGoal,
    ns_to_s,
)
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext

CHECKPOINT_FORMAT = "uavlab.pmr_cvi.v1"
FEATURE_NAMES: tuple[str, ...] = (
    "position_x_m",
    "position_y_m",
    "position_z_m",
    "speed_mps",
    "goal_distance_m",
    "waypoint_progress_m",
    "progress_rate_mps",
    "no_progress_s",
    "obstacle_risk",
    "target_confidence",
    "planner_failure",
    "uncertainty",
    "time_since_last_query_s",
    "remaining_budget_frac",
    "reasoning_debt",
    "battery_frac",
    "previous_command_success",
    "safety_interventions",
)


@register("admission", "pmr_cvi")
class PMRCVIAdmission:
    """Fixed 18D sigmoid-linear PMR admission gate with runtime guards."""

    def __init__(self, **params: Any) -> None:
        checkpoint_path = str(params.get("checkpoint_path", "")).strip()
        if not checkpoint_path:
            raise ValueError(
                "pmr_cvi requires checkpoint_path; the paper does not publish weights, "
                "so an untrained or hand-tuned score is not a valid substitute"
            )
        self.checkpoint_path = Path(checkpoint_path)
        checkpoint = self._load_checkpoint(self.checkpoint_path)

        self.mean = tuple(float(value) for value in checkpoint["mean"])
        self.scale = tuple(float(value) for value in checkpoint["scale"])
        self.weights = tuple(float(value) for value in checkpoint["weights"])
        self.bias = float(checkpoint["bias"])
        self.threshold = float(params.get("threshold", checkpoint.get("threshold", 0.997)))
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(f"pmr_cvi threshold must be in [0, 1], got {self.threshold}")

        self.hard_stuck_s = float(params.get("hard_stuck_s", 10.0))
        self.blocked_risk_threshold = float(params.get("blocked_risk_threshold", 0.7))
        self.clearance_scale_m = float(params.get("clearance_scale_m", 5.0))
        self.goal_distance_cap_m = float(params.get("goal_distance_cap_m", 100.0))
        self.query_time_cap_s = float(params.get("query_time_cap_s", 60.0))
        self.feature_clip = float(params.get("feature_clip", 8.0))
        self.min_battery_frac = float(params.get("min_battery_frac", 0.2))
        self.progress_epsilon_m = float(params.get("progress_epsilon_m", 0.05))

        self._previous_goal_distance_m: float | None = None
        self._previous_t_ns: int | None = None
        self._last_progress_t_ns: int | None = None
        self._assessments = 0
        self._admissions = 0

    @property
    def name(self) -> str:
        return "pmr_cvi"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._previous_goal_distance_m = None
        self._previous_t_ns = None
        self._last_progress_t_ns = None
        self._assessments = 0
        self._admissions = 0

    async def assess(
        self, ctx: DecisionContext, runtime: AdmissionRuntime
    ) -> AdmissionDecision:
        self._assessments += 1
        raw, goal_distance, no_progress_s, obstacle_risk = self._raw_features(ctx, runtime)
        normalized = tuple(
            max(
                -self.feature_clip,
                min(self.feature_clip, (value - mean) / scale),
            )
            for value, mean, scale in zip(raw, self.mean, self.scale, strict=True)
        )
        logit = self.bias + sum(
            weight * value for weight, value in zip(self.weights, normalized, strict=True)
        )
        score = self._sigmoid(logit)

        progress = ctx.last_progress
        blocked_motion = (
            runtime.planner_failed
            or obstacle_risk >= self.blocked_risk_threshold
            or (progress is not None and progress.label is ProgressLabel.BLOCKED)
        )
        hard_stuck = no_progress_s >= self.hard_stuck_s and blocked_motion

        budget_ready = runtime.max_calls is None or runtime.call_count < runtime.max_calls
        cooldown_ready = (
            runtime.last_call_t_sim_ns is None
            or ns_to_s(runtime.t_sim_ns - runtime.last_call_t_sim_ns) >= runtime.cooldown_s
        )
        outside_terminal = (
            goal_distance is None
            or goal_distance > ctx.mission.success.goal_radius_m
        )
        battery_safe = ctx.observation.battery_frac >= self.min_battery_frac
        guards = {
            "budget_ready": budget_ready,
            "cooldown_ready": cooldown_ready,
            "outside_terminal_radius": outside_terminal,
            "battery_safe": battery_safe,
        }
        admitted = all(guards.values()) and (score >= self.threshold or hard_stuck)
        if admitted:
            self._admissions += 1

        if not all(guards.values()):
            blocked = ",".join(name for name, ready in guards.items() if not ready)
            reason = f"runtime_guard:{blocked}"
        elif hard_stuck:
            reason = f"hard_stuck:no_progress={no_progress_s:.2f}s"
        elif score >= self.threshold:
            reason = f"learned_cvi={score:.6f}"
        else:
            reason = f"below_threshold:{score:.6f}<{self.threshold:.6f}"

        return AdmissionDecision(
            admit=admitted,
            score=score,
            threshold=self.threshold,
            hard_stuck=hard_stuck,
            guards=guards,
            feature_names=FEATURE_NAMES,
            features=normalized,
            reason=reason,
        )

    def _raw_features(
        self, ctx: DecisionContext, runtime: AdmissionRuntime
    ) -> tuple[tuple[float, ...], float | None, float, float]:
        now_ns = runtime.t_sim_ns
        goal_distance = self._goal_distance(ctx)
        bounded_goal_distance = (
            self.goal_distance_cap_m
            if goal_distance is None
            else min(self.goal_distance_cap_m, max(0.0, goal_distance))
        )

        waypoint_progress = 0.0
        progress_rate = 0.0
        if (
            goal_distance is not None
            and self._previous_goal_distance_m is not None
            and self._previous_t_ns is not None
            and now_ns > self._previous_t_ns
        ):
            waypoint_progress = self._previous_goal_distance_m - goal_distance
            dt_s = ns_to_s(now_ns - self._previous_t_ns)
            progress_rate = waypoint_progress / max(dt_s, 1e-9)

        if self._last_progress_t_ns is None:
            self._last_progress_t_ns = now_ns
        if waypoint_progress >= self.progress_epsilon_m:
            self._last_progress_t_ns = now_ns
        local_no_progress_s = ns_to_s(now_ns - self._last_progress_t_ns)
        reported_no_progress_s = (
            ctx.last_progress.stalled_for_s if ctx.last_progress is not None else 0.0
        )
        no_progress_s = max(local_no_progress_s, reported_no_progress_s)

        if goal_distance is not None:
            self._previous_goal_distance_m = goal_distance
        self._previous_t_ns = now_ns

        geometry = ctx.perception.geometry
        clearance = geometry.free_radius_m if geometry is not None else float("inf")
        obstacle_risk = (
            0.0
            if not math.isfinite(clearance)
            else 1.0 - min(1.0, max(0.0, clearance) / self.clearance_scale_m)
        )
        target_confidence = max(
            (detection.score for detection in ctx.perception.detections),
            default=0.0,
        )
        time_since_query_s = (
            self.query_time_cap_s
            if runtime.last_call_t_sim_ns is None
            else min(
                self.query_time_cap_s,
                max(0.0, ns_to_s(now_ns - runtime.last_call_t_sim_ns)),
            )
        )
        remaining_budget = (
            1.0
            if runtime.max_calls is None
            else max(0.0, (runtime.max_calls - runtime.call_count) / max(runtime.max_calls, 1))
        )
        reasoning_debt = min(
            2.0,
            no_progress_s / max(self.hard_stuck_s, 1e-6)
            + 0.25 * float(runtime.planner_failed)
            + 0.25 * ctx.perception.uncertainty,
        )
        previous_command_success = (
            1.0
            if ctx.last_routing_feedback is None or ctx.last_routing_feedback.accepted
            else 0.0
        )
        position = ctx.observation.position
        raw = (
            position.x,
            position.y,
            position.z,
            ctx.observation.velocity.norm(),
            bounded_goal_distance,
            waypoint_progress,
            progress_rate,
            no_progress_s,
            obstacle_risk,
            target_confidence,
            float(runtime.planner_failed),
            ctx.perception.uncertainty,
            time_since_query_s,
            remaining_budget,
            reasoning_debt,
            ctx.observation.battery_frac,
            previous_command_success,
            float(runtime.safety_interventions),
        )
        return raw, goal_distance, no_progress_s, obstacle_risk

    @staticmethod
    def _goal_distance(ctx: DecisionContext) -> float | None:
        if ctx.last_progress is not None and ctx.last_progress.distance_to_goal_m is not None:
            return ctx.last_progress.distance_to_goal_m
        if ctx.last_decision is not None and isinstance(ctx.last_decision.payload, WaypointGoal):
            return ctx.observation.position.distance_to(ctx.last_decision.payload.target)
        positioned = [
            detection
            for detection in ctx.perception.detections
            if detection.position is not None
        ]
        if positioned:
            best = max(positioned, key=lambda detection: detection.score)
            assert best.position is not None
            return ctx.observation.position.distance_to(best.position)
        return None

    @staticmethod
    def _sigmoid(value: float) -> float:
        if value >= 0:
            exp_neg = math.exp(-value)
            return 1.0 / (1.0 + exp_neg)
        exp_pos = math.exp(value)
        return exp_pos / (1.0 + exp_pos)

    @staticmethod
    def _load_checkpoint(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(
                f"PMR learned-CVI checkpoint not found: {path}. "
                "Train it from development PMR logs before enabling this profile."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != CHECKPOINT_FORMAT:
            raise ValueError(
                f"PMR checkpoint format must be {CHECKPOINT_FORMAT!r}, "
                f"got {data.get('format')!r}"
            )
        if data.get("trained") is not True:
            raise ValueError("PMR checkpoint must declare trained=true")
        names = tuple(data.get("feature_names", ()))
        if names != FEATURE_NAMES:
            raise ValueError("PMR checkpoint feature order does not match the fixed 18D contract")
        for key in ("mean", "scale", "weights"):
            values = data.get(key)
            if not isinstance(values, list) or len(values) != len(FEATURE_NAMES):
                raise ValueError(f"PMR checkpoint {key!r} must contain 18 values")
        if any(float(value) <= 0.0 for value in data["scale"]):
            raise ValueError("PMR checkpoint scales must all be positive")
        if "bias" not in data:
            raise ValueError("PMR checkpoint is missing bias")
        return data

    def stats(self) -> dict[str, float]:
        return {
            "admission_assessments": float(self._assessments),
            "admission_positive": float(self._admissions),
        }
