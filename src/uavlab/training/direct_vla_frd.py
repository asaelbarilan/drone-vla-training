"""Versioned heading-level FRD actions; old FLU data/checkpoints remain unchanged.

+forward/+right/+down, +clockwise yaw viewed from above. Source yaw is ENU
radians. This frame is level, not tilted with the aircraft's roll and pitch.
The decoded ENU command stays fixed through its horizon. Not physical landing.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from uavlab.contracts import ControlCommand, KinematicAction
from uavlab.training import direct_vla_contract as flu

CONTRACT_ID = "direct_velocity_heading_frd_v2"
FIELDS = ("forward_bin", "right_bin", "down_bin", "yaw_cw_bin")


@dataclass(frozen=True, slots=True)
class FRDTarget:
    forward_bin: int
    right_bin: int
    down_bin: int
    yaw_cw_bin: int
    stop: bool = False

    def __post_init__(self):
        # Symmetric sign changes preserve both range and STOP validation.
        flu.DirectVLATarget(
            self.forward_bin, self.right_bin, self.down_bin, self.yaw_cw_bin, self.stop
        )


def from_flu(target: flu.DirectVLATarget) -> FRDTarget:
    if not isinstance(target, flu.DirectVLATarget):
        raise TypeError("explicit FLU target required")
    return FRDTarget(
        target.vx_body_bin,
        64 - target.vy_body_bin,
        64 - target.vz_body_bin,
        64 - target.yaw_rate_bin,
        target.stop,
    )


def to_flu(target: FRDTarget) -> flu.DirectVLATarget:
    if not isinstance(target, FRDTarget):
        raise TypeError("explicit FRD target required; do not mix contract versions")
    return flu.DirectVLATarget(
        target.forward_bin,
        64 - target.right_bin,
        64 - target.down_bin,
        64 - target.yaw_cw_bin,
        target.stop,
    )


def target_from_command(
    command: ControlCommand, yaw_enu_rad: float, *, terminal: bool = False
) -> FRDTarget:
    return from_flu(flu.target_from_command(command, yaw_enu_rad, terminal=terminal))


def action_from_target(
    target: FRDTarget, yaw_enu_rad: float, *, duration_s: float
) -> KinematicAction | None:
    return flu.action_from_target(to_flu(target), yaw_enu_rad, duration_s=duration_s)


def target_json(target: FRDTarget) -> str:
    to_flu(target)  # explicit contract/type check
    return json.dumps(asdict(target), separators=(",", ":"))


def parse_target(text: str) -> FRDTarget:
    try:
        payload = json.loads(text, object_pairs_hook=flu._unique_object)
    except (TypeError, json.JSONDecodeError) as exc:
        raise flu.DirectVLAOutputError("FRD output must be one JSON object") from exc
    if not isinstance(payload, dict) or set(payload) != {*FIELDS, "stop"}:
        raise flu.DirectVLAOutputError(
            "FRD output requires exactly forward_bin/right_bin/down_bin/yaw_cw_bin/stop"
        )
    return FRDTarget(**payload)


def student_prompt(instruction: str, state: dict) -> str:
    return (
        "Direct drone control. Image: front RGB above downward RGB. "
        "Use only the instruction, image and supplied odometry. "
        + instruction
        + "\nOdometry: "
        + json.dumps(state, separators=(",", ":"))
        + "\nReturn JSON keys forward_bin,right_bin,down_bin,yaw_cw_bin,stop. "
        "Velocity axes are forward/right/down in the level frame defined by this observation yaw. "
        "Bins 0..64 map to -5..5 m/s on each velocity axis and -1.5..1.5 rad/s yaw "
        "(positive clockwise viewed from above). Bin32 is exactly zero. "
        "The decoded ENU setpoint lasts 0.2 seconds. "
        "Nonterminal hold is all32 with stop=false. "
        "Mission termination is all32 with stop=true; it is not physical landing."
    )
