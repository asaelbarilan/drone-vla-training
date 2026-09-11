"""Semantic/geometric verifiers.

The verifier sits between the semantic model and the planner, and answers one
question: is this proposal a *sane target at all*?  It is not the safety shield
— it never sees a control command — and keeping the two separate is what lets
C2->C3 (add a verifier) and C7->C8 (add a shield) be read as different findings
rather than one blurred "added some checking" effect.

A verifier may repair as well as veto.  Repairing is reported separately,
because a verifier that silently rewrites most proposals is doing the policy's
job, not validating it.
"""

from __future__ import annotations

import math
from typing import Any

from uavlab.contracts import DecisionEnvelope, MissionSpec, Vec3, WaypointGoal
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext, VerificationResult


@register("verifier", "none")
class NoVerifier:
    """Explicit "no validation", so its absence is a declared choice."""

    def __init__(self, **params: Any) -> None:
        pass

    @property
    def name(self) -> str:
        return "none"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        return None

    def verify(self, envelope: DecisionEnvelope, ctx: DecisionContext) -> VerificationResult:
        return VerificationResult(accepted=True, reason="no verifier configured")


@register("verifier", "semantic_geometric")
class SemanticGeometricVerifier:
    """Checks a waypoint against the geofence, the depth fan and the instruction."""

    def __init__(self, **params: Any) -> None:
        self.max_waypoint_distance_m = float(params.get("max_waypoint_distance_m", 30.0))
        self.min_clearance_m = float(params.get("min_clearance_m", 1.2))
        self.sensing_horizon_m = float(params.get("sensing_horizon_m", 25.0))
        self.repair = bool(params.get("repair", True))
        self.require_semantic_support = bool(params.get("require_semantic_support", False))
        """Reject targets with no supporting detection *and* no memory evidence."""
        self._min_alt = 0.5
        self._max_alt = 30.0
        self._geofence = 100.0
        self.rejections = 0
        self.repairs = 0

    @property
    def name(self) -> str:
        return "semantic_geometric"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._min_alt = mission.constraints.min_altitude_m
        self._max_alt = mission.constraints.max_altitude_m
        self._geofence = mission.constraints.geofence_radius_m
        self.rejections = 0
        self.repairs = 0

    def verify(self, envelope: DecisionEnvelope, ctx: DecisionContext) -> VerificationResult:
        goal = envelope.payload
        if not isinstance(goal, WaypointGoal):
            return VerificationResult(accepted=True, reason="not a waypoint; nothing to verify")

        target = goal.target
        position = ctx.observation.position
        reasons: list[str] = []
        repaired = target

        distance = position.distance_to(target)
        if distance > self.max_waypoint_distance_m:
            reasons.append(
                f"target {distance:.1f} m away exceeds the {self.max_waypoint_distance_m:.0f} m "
                "single-hop limit"
            )
            scale = self.max_waypoint_distance_m / distance
            repaired = Vec3(
                x=position.x + (target.x - position.x) * scale,
                y=position.y + (target.y - position.y) * scale,
                z=position.z + (target.z - position.z) * scale,
            )

        if not (self._min_alt <= repaired.z <= self._max_alt):
            reasons.append(
                f"altitude {repaired.z:.1f} m outside "
                f"[{self._min_alt}, {self._max_alt}]"
            )
            repaired = Vec3(
                x=repaired.x, y=repaired.y, z=min(self._max_alt, max(self._min_alt, repaired.z))
            )

        radius = math.sqrt(repaired.x**2 + repaired.y**2)
        if radius > self._geofence:
            self.rejections += 1
            return VerificationResult(
                accepted=False,
                code="geofence",
                reason=f"target is {radius:.1f} m from home, outside the "
                f"{self._geofence:.0f} m geofence",
            )

        if self._points_into_obstacle(repaired, ctx):
            self.rejections += 1
            return VerificationResult(
                accepted=False,
                reason="target lies within the minimum clearance of an observed obstacle",
            )

        if self.require_semantic_support and not self._has_semantic_support(goal, ctx):
            self.rejections += 1
            return VerificationResult(
                accepted=False,
                reason=f"no detection or memory evidence supports target "
                f"{goal.target_label or '(unlabelled)'}",
            )

        if reasons and self.repair:
            self.repairs += 1
            replacement = envelope.model_copy(
                update={
                    "payload": goal.model_copy(update={"target": repaired}),
                    "provenance": {**envelope.provenance, "verifier": "repaired"},
                }
            )
            return VerificationResult(
                accepted=True, reason="; ".join(reasons), replacement=replacement
            )
        if reasons:
            self.rejections += 1
            return VerificationResult(accepted=False, reason="; ".join(reasons))
        return VerificationResult(accepted=True, reason="ok")

    def _points_into_obstacle(self, target: Vec3, ctx: DecisionContext) -> bool:
        obs = ctx.observation
        if not obs.range_rays:
            return False
        dx, dy = target.x - obs.position.x, target.y - obs.position.y
        planar = math.hypot(dx, dy)
        if planar < 1e-6:
            return False
        world_bearing = math.atan2(dy, dx)
        body_bearing = math.atan2(
            math.sin(world_bearing - obs.yaw_rad), math.cos(world_bearing - obs.yaw_rad)
        )
        idx = min(
            range(len(obs.ray_bearings_rad)),
            key=lambda i: abs(
                math.atan2(
                    math.sin(obs.ray_bearings_rad[i] - body_bearing),
                    math.cos(obs.ray_bearings_rad[i] - body_bearing),
                )
            ),
        )
        clearance = obs.range_rays[idx]
        if clearance >= self.sensing_horizon_m - 1e-6:
            # The normalized range fan reports its maximum range when no
            # surface was hit.  That sentinel is free/unknown space, not an
            # obstacle coincidentally located at the horizon.
            return False
        # This verifier decides whether the proposed *endpoint* is sane.  An
        # obstacle anywhere earlier on the ray is a route-planning problem and
        # SUPER is specifically responsible for finding a detour.  Reject only
        # when the endpoint itself lies within the clearance band around the
        # first observed surface; otherwise a long-running skill would be
        # rejected precisely when its planner approached an obstacle to route
        # around it.
        return abs(planar - clearance) < self.min_clearance_m * 2.0

    @staticmethod
    def _has_semantic_support(goal: WaypointGoal, ctx: DecisionContext) -> bool:
        if goal.target_label is None:
            return True
        if any(d.label == goal.target_label for d in ctx.perception.detections):
            return True
        return any(item.position is not None for item in ctx.memory.items)
