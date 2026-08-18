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
)
from uavlab.contracts.decision import MissionDirective
from uavlab.interfaces import DecisionContext

SkillResult = WaypointGoal | KinematicAction | MissionDirective
SkillFn = Callable[[SkillCall, DecisionContext], SkillResult]


class UnknownSkillError(KeyError):
    """Raised when a policy proposes a skill outside the bounded vocabulary."""


def _arg(call: SkillCall, key: str, default: float) -> float:
    value = call.args.get(key, default)
    return float(value) if isinstance(value, (int, float)) else default


def _skill_goto(call: SkillCall, ctx: DecisionContext) -> WaypointGoal:
    """Absolute goto in the canonical ENU frame."""
    return WaypointGoal(
        target=Vec3(x=_arg(call, "x", 0.0), y=_arg(call, "y", 0.0), z=_arg(call, "z", 3.0)),
        target_label=str(call.args.get("label", "")) or None,
        tolerance_m=_arg(call, "tolerance_m", 1.0),
        stop_at_target=bool(call.args.get("stop", False)),
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
        stop_at_target=bool(call.args.get("stop", True)),
    )


def _skill_hover(call: SkillCall, ctx: DecisionContext) -> WaypointGoal:
    return WaypointGoal(
        target=ctx.observation.position, tolerance_m=0.5, stop_at_target=True
    )


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
    return WaypointGoal(
        target=Vec3(x=p.x, y=p.y, z=p.z + _arg(call, "dz", 2.0)), tolerance_m=0.8
    )


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
        self.calls[call.skill_name] = self.calls.get(call.skill_name, 0) + 1
        return fn(call, ctx)

    @staticmethod
    def result_kind(result: SkillResult) -> DecisionKind:
        return result.kind
