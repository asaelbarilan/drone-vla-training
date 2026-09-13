"""Bounded skill runtime.

A skill call is *capability-bounded authority*: the semantic model may only
choose from a vocabulary that was validated in advance, and each skill expands
into an ordinary subgoal that then travels the same verifier/planner/safety path
as any other waypoint.  Nothing about the skill family gets a private route to
the controller.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from uavlab.contracts import (
    DecisionKind,
    KinematicAction,
    ProgressLabel,
    SkillCall,
    Vec3,
    WaypointGoal,
    s_to_ns,
)
from uavlab.contracts.decision import MissionDirective
from uavlab.core.mission_evidence import (
    OrderedVisitEvidence,
    public_coordinate_goal,
    public_ordered_visit,
)
from uavlab.interfaces import DecisionContext, SemanticCompletionEvidence

SkillResult = WaypointGoal | KinematicAction | MissionDirective
SkillFn = Callable[[SkillCall, DecisionContext], SkillResult]


class UnknownSkillError(KeyError):
    """Raised when a policy proposes a skill outside the bounded vocabulary."""


class InvalidSkillArguments(ValueError):
    """Raised before dispatch when a documented hard-skill contract is violated."""


_SKILL_ARGUMENTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    # name: (required, optional). Keeping this beside the implementation makes
    # the runtime catalog and enforcement one source of truth.
    "goto": (frozenset({"x", "y", "z"}), frozenset({"label", "tolerance_m"})),
    "move": (frozenset(), frozenset({"dx", "dy", "dz", "tolerance_m"})),
    "approach": (frozenset({"label"}), frozenset({"standoff_m", "tolerance_m"})),
    "hover": (frozenset(), frozenset()),
    "scan": (frozenset(), frozenset({"yaw_rate_rps", "duration_s"})),
    "back_off": (frozenset(), frozenset({"distance_m"})),
    "ascend": (frozenset(), frozenset({"dz"})),
    "stop": (frozenset(), frozenset({"reason"})),
}


def _number(call: SkillCall, key: str) -> float | None:
    value = call.args.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidSkillArguments(f"{call.skill_name}.{key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise InvalidSkillArguments(f"{call.skill_name}.{key} must be finite")
    return number


def validate_skill_call(call: SkillCall, ctx: DecisionContext | None = None) -> None:
    """Validate name-specific arguments before any skill can affect motion."""

    contract = _SKILL_ARGUMENTS.get(call.skill_name)
    if contract is None:
        raise UnknownSkillError(f"skill {call.skill_name!r} has no implementation")
    required, optional = contract
    keys = frozenset(call.args)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        raise InvalidSkillArguments(f"{call.skill_name} missing required arguments {missing}")
    if unknown:
        raise InvalidSkillArguments(f"{call.skill_name} has undocumented arguments {unknown}")

    numeric = {
        "goto": ("x", "y", "z", "tolerance_m"),
        "move": ("dx", "dy", "dz", "tolerance_m"),
        "approach": ("standoff_m", "tolerance_m"),
        "scan": ("yaw_rate_rps", "duration_s"),
        "back_off": ("distance_m",),
        "ascend": ("dz",),
    }.get(call.skill_name, ())
    values = {key: _number(call, key) for key in numeric}

    for key in ("tolerance_m", "standoff_m", "duration_s", "distance_m"):
        value = values.get(key)
        if value is not None and value <= 0.0:
            raise InvalidSkillArguments(f"{call.skill_name}.{key} must be > 0")
    if call.skill_name == "ascend" and values.get("dz") is not None and values["dz"] <= 0.0:
        raise InvalidSkillArguments("ascend.dz must be > 0")
    yaw_rate = values.get("yaw_rate_rps")
    if yaw_rate is not None and not 0.05 <= abs(yaw_rate) <= 2.0:
        raise InvalidSkillArguments("scan.yaw_rate_rps magnitude must be in [0.05, 2.0]")
    duration = values.get("duration_s")
    if duration is not None and duration > 10.0:
        raise InvalidSkillArguments("scan.duration_s must be <= 10")
    if call.skill_name == "move":
        delta = [values.get(k) or 0.0 for k in ("dx", "dy", "dz")]
        if not any(abs(value) > 1e-6 for value in delta):
            raise InvalidSkillArguments("move requires a non-zero dx, dy or dz")
    label = call.args.get("label")
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise InvalidSkillArguments(f"{call.skill_name}.label must be a non-empty string")
    reason = call.args.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise InvalidSkillArguments("stop.reason must be a string")
    # Mission termination is a capability with a semantic precondition, not an
    # unchecked text verdict. This uses only the current perception contract;
    # it never asks the environment whether the candidate is the true target.
    if call.skill_name == "stop" and ctx is not None:
        ordered = public_ordered_visit(ctx.mission)
        if ordered is not None:
            evidence = ctx.scratch.get("ordered_visit_evidence")
            if (
                not isinstance(evidence, OrderedVisitEvidence)
                or evidence.contract != ordered
                or not evidence.stop_supported(ctx.observation)
            ):
                raise InvalidSkillArguments(
                    "stop requires observed first-object dwell then final-object arrival"
                )
            return
        radius = ctx.mission.success.goal_radius_m
        coordinate = public_coordinate_goal(ctx.mission)
        if coordinate is not None:
            if (
                ctx.observation.position.distance_to(coordinate) > radius
                or ctx.observation.velocity.norm() > 0.75
            ):
                raise InvalidSkillArguments(
                    "stop requires arrival at the public mission coordinate within "
                    f"{radius:.1f} m and speed <= 0.75 m/s"
                )
            return
        live_supported = any(
            detection.label == "target"
            and detection.position is not None
            and ctx.observation.position.distance_to(detection.position) <= radius
            for detection in ctx.perception.detections
        )
        recent_memory_supported = any(
            item.label == "target"
            and item.position is not None
            and ctx.t_sim_ns - item.t_sim_ns <= s_to_ns(10.0)
            and ctx.observation.position.distance_to(item.position) <= radius
            for item in ctx.memory.items
        )
        completed = ctx.scratch.get("semantic_completion_evidence")
        completed_skill_supported = (
            isinstance(completed, SemanticCompletionEvidence)
            and completed.label == "target"
            and ctx.t_sim_ns - completed.completed_t_sim_ns <= s_to_ns(10.0)
            and ctx.observation.position.distance_to(completed.position) <= radius
        )
        if not (live_supported or recent_memory_supported or completed_skill_supported):
            raise InvalidSkillArguments(
                "stop requires live, <=10 s remembered, or completed evidence-supported "
                "target-skill evidence within "
                f"the {radius:.1f} m success radius"
            )


def _arg(call: SkillCall, key: str, default: float) -> float:
    value = call.args.get(key, default)
    return float(value) if isinstance(value, (int, float)) else default


def _skill_goto(call: SkillCall, ctx: DecisionContext) -> WaypointGoal:
    """Absolute goto in the canonical ENU frame."""
    return WaypointGoal(
        target=Vec3(x=_arg(call, "x", 0.0), y=_arg(call, "y", 0.0), z=_arg(call, "z", 3.0)),
        target_label=str(call.args.get("label", "")) or None,
        tolerance_m=_arg(call, "tolerance_m", 1.0),
        stop_at_target=False,
    )


def _skill_move(call: SkillCall, ctx: DecisionContext) -> WaypointGoal:
    """Relative displacement from the current position."""
    p = ctx.observation.position
    return WaypointGoal(
        target=Vec3(
            x=p.x + _arg(call, "dx", 0.0),
            y=p.y + _arg(call, "dy", 0.0),
            z=p.z + _arg(call, "dz", 0.0),
        ),
        tolerance_m=_arg(call, "tolerance_m", 1.0),
    )


def _skill_approach(call: SkillCall, ctx: DecisionContext) -> WaypointGoal:
    """Approach a detected label, stopping at a standoff distance.

    Falls back to holding position when the label is not currently detected —
    a skill agent is not allowed to invent a target it cannot see.
    """
    label = str(call.args.get("label", ""))
    standoff = _arg(call, "standoff_m", 2.0)
    target: Vec3 | None = None
    for det in ctx.perception.detections:
        if det.position is not None and (not label or det.label == label):
            target = det.position
            break
    if target is None:
        return WaypointGoal(
            target=ctx.observation.position,
            target_label=label or None,
            tolerance_m=1.0,
            stop_at_target=False,
        )
    p = ctx.observation.position
    dx, dy, dz = target.x - p.x, target.y - p.y, target.z - p.z
    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dist <= standoff or dist < 1e-6:
        approach = target
    else:
        scale = (dist - standoff) / dist
        approach = Vec3(x=p.x + dx * scale, y=p.y + dy * scale, z=p.z + dz * scale)
    return WaypointGoal(
        target=approach,
        target_label=label or None,
        tolerance_m=_arg(call, "tolerance_m", 1.0),
        stop_at_target=False,
    )


def _skill_hover(call: SkillCall, ctx: DecisionContext) -> WaypointGoal:
    return WaypointGoal(target=ctx.observation.position, tolerance_m=0.5, stop_at_target=False)


def _skill_scan(call: SkillCall, ctx: DecisionContext) -> KinematicAction:
    """Rotate in place to acquire visual evidence."""
    return KinematicAction(
        velocity=Vec3(x=0.0, y=0.0, z=0.0),
        yaw_rate_rps=_arg(call, "yaw_rate_rps", 0.6),
        duration_s=_arg(call, "duration_s", 1.0),
    )


def _skill_back_off(call: SkillCall, ctx: DecisionContext) -> WaypointGoal:
    """Retreat along the current heading; the canonical recovery skill."""
    p = ctx.observation.position
    dist = _arg(call, "distance_m", 3.0)
    yaw = ctx.observation.yaw_rad
    return WaypointGoal(
        target=Vec3(x=p.x - dist * math.cos(yaw), y=p.y - dist * math.sin(yaw), z=p.z),
        tolerance_m=1.0,
    )


def _skill_ascend(call: SkillCall, ctx: DecisionContext) -> WaypointGoal:
    p = ctx.observation.position
    return WaypointGoal(target=Vec3(x=p.x, y=p.y, z=p.z + _arg(call, "dz", 2.0)), tolerance_m=0.8)


def _skill_stop(call: SkillCall, ctx: DecisionContext) -> MissionDirective:
    """Terminal intent. Routed as a directive, never as motion."""
    return MissionDirective(
        label=ProgressLabel.STOP, rationale=str(call.args.get("reason", "skill requested stop"))
    )


SKILL_LIBRARY: dict[str, SkillFn] = {
    "goto": _skill_goto,
    "move": _skill_move,
    "approach": _skill_approach,
    "hover": _skill_hover,
    "scan": _skill_scan,
    "back_off": _skill_back_off,
    "ascend": _skill_ascend,
    "stop": _skill_stop,
}


class SkillRuntime:
    """Expands a bounded skill call into an ordinary subgoal."""

    def __init__(self, allowed: tuple[str, ...] = ()) -> None:
        self.allowed = tuple(allowed) or tuple(SKILL_LIBRARY)
        self.calls: dict[str, int] = {}

    @property
    def name(self) -> str:
        return "skill_runtime"

    def reset(self) -> None:
        self.calls = {}

    def expand(self, call: SkillCall, ctx: DecisionContext) -> SkillResult:
        if call.skill_name not in self.allowed:
            raise UnknownSkillError(
                f"skill {call.skill_name!r} is outside the bounded vocabulary "
                f"{sorted(self.allowed)}"
            )
        fn = SKILL_LIBRARY.get(call.skill_name)
        if fn is None:
            raise UnknownSkillError(f"skill {call.skill_name!r} has no implementation")
        validate_skill_call(call, ctx)
        self.calls[call.skill_name] = self.calls.get(call.skill_name, 0) + 1
        return fn(call, ctx)

    @staticmethod
    def result_kind(result: SkillResult) -> DecisionKind:
        return result.kind
