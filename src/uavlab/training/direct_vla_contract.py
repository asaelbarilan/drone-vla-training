"""Additive direct_velocity_yaw_level_v1 contract; native AeroVLA is unchanged.

Velocity axes are forward/left/up in a *level* frame defined by the source
observation yaw. This is not a roll/pitch aircraft-body frame. Decode ONCE at
that yaw into ENU, then hold the world-frame setpoint for the configured horizon.
The shared controller may project vector speed; the simulator adds acceleration
lag. These effects must be recorded separately from quantization.
Stop means mission termination, not physical landing. Zero motion is valid hold.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from uavlab.contracts import ControlCommand, Frame, KinematicAction, Vec3
from uavlab.core.frames import body_to_enu, enu_to_body

CONTRACT_ID = "direct_velocity_yaw_level_v1"
NUM_VELOCITY_BINS = 65
ZERO_BIN = (NUM_VELOCITY_BINS - 1) // 2
HORIZONTAL_RANGE_MPS = (-5.0, 5.0)
VERTICAL_RANGE_MPS = (-5.0, 5.0)
YAW_RATE_RANGE_RPS = (-1.5, 1.5)
CONTROL_TICK_S = 0.05


class DirectVLAOutputError(ValueError):
    """An invalid label/output must not silently become a motion command."""


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _range(value_range: tuple[float, float]) -> tuple[float, float]:
    low, high = (_finite(v, "range bound") for v in value_range)
    if low >= 0.0 or high <= 0.0 or low != -high:
        raise ValueError("direct-VLA ranges must be symmetric around zero")
    return low, high


def quantize_symmetric(value: float, value_range: tuple[float, float]) -> int:
    """Nearest bin, rejecting unsupported labels instead of hiding clipping."""
    low, high = _range(value_range)
    value = _finite(value, "action value")
    if not low <= value <= high:
        raise ValueError(f"action value {value} outside [{low}, {high}]; no silent clipping")
    return round((value - low) * (NUM_VELOCITY_BINS - 1) / (high - low))


def dequantize_symmetric(token: int, value_range: tuple[float, float]) -> float:
    if type(token) is not int:
        raise DirectVLAOutputError("action bins must be integers")
    if not 0 <= token < NUM_VELOCITY_BINS:
        raise DirectVLAOutputError(f"action bin {token} is outside [0, {NUM_VELOCITY_BINS - 1}]")
    low, high = _range(value_range)
    return low + token * (high - low) / (NUM_VELOCITY_BINS - 1)


@dataclass(frozen=True, slots=True)
class DirectVLATarget:
    """The historical field suffix 'body' here means yaw-level forward/left/up."""

    vx_body_bin: int
    vy_body_bin: int
    vz_body_bin: int
    yaw_rate_bin: int
    stop: bool = False

    def __post_init__(self) -> None:
        tokens = (self.vx_body_bin, self.vy_body_bin, self.vz_body_bin, self.yaw_rate_bin)
        for token in tokens:
            dequantize_symmetric(token, HORIZONTAL_RANGE_MPS)
        if type(self.stop) is not bool:
            raise DirectVLAOutputError("stop must be a JSON boolean")
        if self.stop and tokens != (ZERO_BIN,) * 4:
            raise DirectVLAOutputError("a stop target must carry zero motion bins")


def target_from_command(
    command: ControlCommand,
    yaw_enu_rad: float,
    *,
    terminal: bool = False,
) -> DirectVLATarget:
    """Quantize an ENU teacher setpoint; no inference of mission completion."""
    yaw_enu_rad = _finite(yaw_enu_rad, "source yaw")
    if type(terminal) is not bool:
        raise ValueError("terminal must be a boolean")
    if command.frame is not Frame.ENU or command.velocity.frame is not Frame.ENU:
        raise ValueError("teacher command and velocity must both be ENU")
    for v in command.velocity.as_tuple():
        _finite(v, "teacher velocity")
    yaw_rate = _finite(command.yaw_rate_rps, "teacher yaw rate")
    if command.velocity.norm() > HORIZONTAL_RANGE_MPS[1] + 1e-12:
        raise ValueError("teacher speed exceeds the 5 m/s contract")
    if terminal:
        if not command.is_hold:
            raise ValueError("terminal label requires an explicit zero-motion teacher command")
        return DirectVLATarget(ZERO_BIN, ZERO_BIN, ZERO_BIN, ZERO_BIN, True)
    body = enu_to_body(command.velocity, yaw_enu_rad)
    return DirectVLATarget(
        quantize_symmetric(body.x, HORIZONTAL_RANGE_MPS),
        quantize_symmetric(body.y, HORIZONTAL_RANGE_MPS),
        quantize_symmetric(body.z, VERTICAL_RANGE_MPS),
        quantize_symmetric(yaw_rate, YAW_RATE_RANGE_RPS),
        False,
    )


def action_from_target(
    target: DirectVLATarget,
    yaw_enu_rad: float,
    *,
    duration_s: float,
) -> KinematicAction | None:
    """Decode using SOURCE yaw, not yaw at delayed inference completion."""
    yaw_enu_rad = _finite(yaw_enu_rad, "source yaw")
    duration_s = _finite(duration_s, "duration_s")
    if duration_s < CONTROL_TICK_S:
        raise ValueError("duration_s must be positive and at least one 0.05 s control tick")
    ticks = duration_s / CONTROL_TICK_S
    if not math.isclose(ticks, round(ticks), abs_tol=1e-9, rel_tol=0):
        raise ValueError("duration_s must be an integer multiple of the 0.05 s control tick")
    if target.stop:
        return None
    body = Vec3(
        x=dequantize_symmetric(target.vx_body_bin, HORIZONTAL_RANGE_MPS),
        y=dequantize_symmetric(target.vy_body_bin, HORIZONTAL_RANGE_MPS),
        z=dequantize_symmetric(target.vz_body_bin, VERTICAL_RANGE_MPS),
        frame=Frame.BODY,
    )
    return KinematicAction(
        velocity=body_to_enu(body, yaw_enu_rad),
        yaw_rate_rps=dequantize_symmetric(target.yaw_rate_bin, YAW_RATE_RANGE_RPS),
        duration_s=duration_s,
    )


def target_json(target: DirectVLATarget) -> str:
    return json.dumps(
        {
            "vx_body_bin": target.vx_body_bin,
            "vy_body_bin": target.vy_body_bin,
            "vz_body_bin": target.vz_body_bin,
            "yaw_rate_bin": target.yaw_rate_bin,
            "stop": target.stop,
        },
        separators=(",", ":"),
    )


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DirectVLAOutputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_target(text: str) -> DirectVLATarget:
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except (TypeError, json.JSONDecodeError) as exc:
        raise DirectVLAOutputError("direct-VLA output must be one JSON object") from exc
    expected = {"vx_body_bin", "vy_body_bin", "vz_body_bin", "yaw_rate_bin", "stop"}
    if not isinstance(payload, dict) or set(payload) != expected:
        raise DirectVLAOutputError(f"direct-VLA output must contain exactly {sorted(expected)}")
    try:
        return DirectVLATarget(**payload)
    except TypeError as exc:
        raise DirectVLAOutputError("invalid direct-VLA fields") from exc
