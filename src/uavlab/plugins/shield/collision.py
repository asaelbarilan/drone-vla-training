"""Safety shields.

The shield is independent of the semantic model by construction: it sees only a
control command and the current geometry.  That independence is the entire point
of the C7/C8 contrast — same VLA, shield off then on — because it separates "is
this stack physically safe?" from "is this model competent?".

Every intervention is recorded with a magnitude.  A shield that constantly
rewrites commands has not made the architecture safe; it has quietly become the
controller, and the intervention rate is what exposes that.
"""

from __future__ import annotations

import math
from typing import Any

from uavlab.contracts import (
    ControlCommand,
    MissionSpec,
    SafetyDecision,
    SafetyVerdict,
    Vec3,
)
from uavlab.core.registry import register
from uavlab.core.sensing import min_clearance
from uavlab.interfaces import DecisionContext


@register("shield", "none")
class NoShield:
    """Pass-through. Declares that this architecture has no independent safety."""

    def __init__(self, **params: Any) -> None:
        pass

    @property
    def name(self) -> str:
        return "none"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        return None

    def check(
        self, command: ControlCommand, ctx: DecisionContext
    ) -> tuple[ControlCommand, SafetyDecision]:
        return command, SafetyDecision(
            verdict=SafetyVerdict.ACCEPT, reason="no shield configured", t_sim_ns=ctx.t_sim_ns
        )


@register("shield", "simple_collision")
class SimpleCollisionShield:
    """Braking-distance shield with geofence and altitude envelopes."""

    def __init__(self, **params: Any) -> None:
        self.reaction_time_s = float(params.get("reaction_time_s", 0.35))
        self.hard_stop_m = float(params.get("hard_stop_m", 1.0))
        self.brake_margin_m = float(params.get("brake_margin_m", 1.5))
        self.max_deflection_rad = float(params.get("max_deflection_rad", math.radians(60.0)))
        self.allow_deflection = bool(params.get("allow_deflection", True))
        self._max_speed = 5.0
        self._min_alt = 0.5
        self._max_alt = 30.0
        self._geofence = 100.0
        self._min_clearance = 0.6

    @property
    def name(self) -> str:
        return "simple_collision"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        c = mission.constraints
        self._max_speed = c.max_speed_mps
        self._min_alt = c.min_altitude_m
        self._max_alt = c.max_altitude_m
        self._geofence = c.geofence_radius_m
        self._min_clearance = c.min_obstacle_clearance_m

    def check(
        self, command: ControlCommand, ctx: DecisionContext
    ) -> tuple[ControlCommand, SafetyDecision]:
        obs = ctx.observation
        velocity = command.velocity
        speed = velocity.norm()
        reasons: list[str] = []
        adjusted = velocity

        if speed > self._max_speed:
            scale = self._max_speed / speed
            adjusted = Vec3(x=adjusted.x * scale, y=adjusted.y * scale, z=adjusted.z * scale)
            reasons.append(f"speed {speed:.2f} clamped to {self._max_speed:.2f} m/s")
            speed = self._max_speed

        adjusted, alt_reason = self._enforce_altitude(adjusted, obs.position)
        if alt_reason:
            reasons.append(alt_reason)

        adjusted, fence_reason = self._enforce_geofence(adjusted, obs.position)
        if fence_reason:
            reasons.append(fence_reason)

        clearance = self._clearance_along(adjusted, ctx)
        stopping = speed * self.reaction_time_s + self.brake_margin_m

        if clearance <= self.hard_stop_m:
            stopped = ControlCommand(
                t_sim_ns=command.t_sim_ns,
                velocity=Vec3(x=0.0, y=0.0, z=0.0),
                yaw_rate_rps=0.0,
                frame=command.frame,
                expires_t_sim_ns=command.expires_t_sim_ns,
                source_decision_id=command.source_decision_id,
                source_observation_seq=command.source_observation_seq,
                source_t_sim_ns=command.source_t_sim_ns,
                safety_modified=True,
                metadata={"shield": "hard_stop"},
            )
            return stopped, SafetyDecision(
                verdict=SafetyVerdict.REJECT,
                reason=f"clearance {clearance:.2f} m below hard stop {self.hard_stop_m:.2f} m",
                risk=1.0,
                source_decision_id=command.source_decision_id,
                modified=True,
                intervention_magnitude=speed,
                t_sim_ns=ctx.t_sim_ns,
                details={"clearance_m": clearance},
            )

        if clearance < stopping and speed > 1e-6:
            deflected = self._deflect(adjusted, ctx) if self.allow_deflection else None
            if deflected is not None:
                adjusted = deflected
                reasons.append(f"deflected around obstacle at {clearance:.2f} m")
            else:
                allowed = max(0.0, (clearance - self.brake_margin_m) / max(self.reaction_time_s, 1e-3))
                scale = min(1.0, allowed / speed)
                adjusted = Vec3(x=adjusted.x * scale, y=adjusted.y * scale, z=adjusted.z * scale)
                reasons.append(
                    f"speed reduced for {clearance:.2f} m clearance (needed {stopping:.2f} m)"
                )

        if not reasons:
            return command, SafetyDecision(
                verdict=SafetyVerdict.ACCEPT,
                reason="within envelope",
                risk=self._risk(clearance),
                source_decision_id=command.source_decision_id,
                t_sim_ns=ctx.t_sim_ns,
                details={"clearance_m": clearance},
            )

        magnitude = math.sqrt(
            (adjusted.x - velocity.x) ** 2
            + (adjusted.y - velocity.y) ** 2
            + (adjusted.z - velocity.z) ** 2
        )
        modified = ControlCommand(
            t_sim_ns=command.t_sim_ns,
            velocity=adjusted,
            yaw_rate_rps=command.yaw_rate_rps,
            frame=command.frame,
            expires_t_sim_ns=command.expires_t_sim_ns,
            source_decision_id=command.source_decision_id,
            source_observation_seq=command.source_observation_seq,
            source_t_sim_ns=command.source_t_sim_ns,
            safety_modified=True,
            metadata={"shield": "modified"},
        )
        return modified, SafetyDecision(
            verdict=SafetyVerdict.MODIFY,
            reason="; ".join(reasons),
            risk=self._risk(clearance),
            source_decision_id=command.source_decision_id,
            modified=True,
            intervention_magnitude=magnitude,
            t_sim_ns=ctx.t_sim_ns,
            details={"clearance_m": clearance},
        )

    def _risk(self, clearance: float) -> float:
        if clearance >= 10.0:
            return 0.0
        return float(min(1.0, max(0.0, 1.0 - clearance / 10.0)))

    def _enforce_altitude(self, velocity: Vec3, position: Vec3) -> tuple[Vec3, str]:
        if position.z <= self._min_alt and velocity.z < 0:
            return Vec3(x=velocity.x, y=velocity.y, z=0.0), (
                f"blocked descent at minimum altitude {self._min_alt:.1f} m"
            )
        if position.z >= self._max_alt and velocity.z > 0:
            return Vec3(x=velocity.x, y=velocity.y, z=0.0), (
                f"blocked climb at maximum altitude {self._max_alt:.1f} m"
            )
        return velocity, ""

    def _enforce_geofence(self, velocity: Vec3, position: Vec3) -> tuple[Vec3, str]:
        radius = math.hypot(position.x, position.y)
        if radius < self._geofence * 0.98:
            return velocity, ""
        outward = (position.x * velocity.x + position.y * velocity.y) / max(radius, 1e-6)
        if outward <= 0:
            return velocity, ""
        unit_x, unit_y = position.x / max(radius, 1e-6), position.y / max(radius, 1e-6)
        return (
            Vec3(
                x=velocity.x - outward * unit_x,
                y=velocity.y - outward * unit_y,
                z=velocity.z,
            ),
            f"removed outward component at the {self._geofence:.0f} m geofence",
        )

    def _clearance_along(self, velocity: Vec3, ctx: DecisionContext) -> float:
        obs = ctx.observation
        if not obs.range_rays:
            return obs.free_range_m
        if abs(velocity.x) < 1e-6 and abs(velocity.y) < 1e-6:
            return float(max(obs.range_rays))
        return self._ray_at(math.atan2(velocity.y, velocity.x), ctx)

    @staticmethod
    def _ray_at(world_bearing: float, ctx: DecisionContext) -> float:
        # Windowed, not single-ray: an obstacle sitting between two rays of a
        # discrete depth fan is otherwise invisible to the shield.
        return min_clearance(ctx.observation, world_bearing)

    def _deflect(self, velocity: Vec3, ctx: DecisionContext) -> Vec3 | None:
        """Rotate the command to the nearest bearing with enough room."""
        speed = velocity.norm()
        if speed < 1e-6:
            return None
        base = math.atan2(velocity.y, velocity.x)
        needed = speed * self.reaction_time_s + self.brake_margin_m
        offset = math.radians(10.0)
        while offset <= self.max_deflection_rad:
            for sign in (1.0, -1.0):
                candidate = base + sign * offset
                if self._ray_at(candidate, ctx) >= needed:
                    horizontal = math.hypot(velocity.x, velocity.y)
                    return Vec3(
                        x=horizontal * math.cos(candidate),
                        y=horizontal * math.sin(candidate),
                        z=velocity.z,
                    )
            offset += math.radians(10.0)
        return None
