"""Explicit, unit-tested coordinate transforms.

Silent frame conversion is one of the few bugs that can invert an entire
experimental conclusion while every test still passes, so there is exactly one
place where ENU and NED meet, and it is here.  Plugins never infer a frame.
"""

from __future__ import annotations

import math

from uavlab.contracts.common import Frame, Vec3

TWO_PI = 2.0 * math.pi


def enu_to_ned(v: Vec3) -> Vec3:
    """ENU (East, North, Up) -> NED (North, East, Down)."""
    if v.frame is not Frame.ENU:
        raise ValueError(f"expected an ENU vector, got {v.frame.value}")
    return Vec3(x=v.y, y=v.x, z=-v.z, frame=Frame.NED)


def ned_to_enu(v: Vec3) -> Vec3:
    """NED -> ENU. The transform is its own inverse under the axis swap."""
    if v.frame is not Frame.NED:
        raise ValueError(f"expected an NED vector, got {v.frame.value}")
    return Vec3(x=v.y, y=v.x, z=-v.z, frame=Frame.ENU)


def wrap_angle(rad: float) -> float:
    """Wrap to (-pi, pi]."""
    wrapped = math.fmod(rad + math.pi, TWO_PI)
    if wrapped <= 0.0:
        wrapped += TWO_PI
    return wrapped - math.pi


def yaw_enu_to_ned(yaw_enu_rad: float) -> float:
    """ENU yaw (CCW from East) -> NED heading (CW from North)."""
    return wrap_angle(math.pi / 2.0 - yaw_enu_rad)


def yaw_ned_to_enu(yaw_ned_rad: float) -> float:
    """NED heading (CW from North) -> ENU yaw (CCW from East)."""
    return wrap_angle(math.pi / 2.0 - yaw_ned_rad)


def body_to_enu(v: Vec3, yaw_enu_rad: float) -> Vec3:
    """Rotate a body-frame vector into ENU using yaw only (planar convention)."""
    if v.frame is not Frame.BODY:
        raise ValueError(f"expected a BODY vector, got {v.frame.value}")
    cos_y, sin_y = math.cos(yaw_enu_rad), math.sin(yaw_enu_rad)
    return Vec3(
        x=v.x * cos_y - v.y * sin_y,
        y=v.x * sin_y + v.y * cos_y,
        z=v.z,
        frame=Frame.ENU,
    )


def enu_to_body(v: Vec3, yaw_enu_rad: float) -> Vec3:
    """Inverse of :func:`body_to_enu`."""
    if v.frame is not Frame.ENU:
        raise ValueError(f"expected an ENU vector, got {v.frame.value}")
    cos_y, sin_y = math.cos(-yaw_enu_rad), math.sin(-yaw_enu_rad)
    return Vec3(
        x=v.x * cos_y - v.y * sin_y,
        y=v.x * sin_y + v.y * cos_y,
        z=v.z,
        frame=Frame.BODY,
    )


def convert(v: Vec3, target: Frame, yaw_enu_rad: float = 0.0) -> Vec3:
    """Convert between frames, raising rather than guessing on unsupported pairs."""
    if v.frame is target:
        return v
    match (v.frame, target):
        case (Frame.ENU, Frame.NED):
            return enu_to_ned(v)
        case (Frame.NED, Frame.ENU):
            return ned_to_enu(v)
        case (Frame.BODY, Frame.ENU):
            return body_to_enu(v, yaw_enu_rad)
        case (Frame.ENU, Frame.BODY):
            return enu_to_body(v, yaw_enu_rad)
        case (Frame.BODY, Frame.NED):
            return enu_to_ned(body_to_enu(v, yaw_enu_rad))
        case (Frame.NED, Frame.BODY):
            return enu_to_body(ned_to_enu(v), yaw_enu_rad)
    raise ValueError(f"no transform defined from {v.frame.value} to {target.value}")
