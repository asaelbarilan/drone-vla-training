"""No-model counterexamples to the old velocity-to-AeroVLA label conversion.

These are analytical interface probes, NOT model predictions or flight results.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from uavlab.contracts import ControlCommand, Vec3
from uavlab.plugins.reasoning.aerovla import action_from_output
from uavlab.training.qwen_vla_dataset import action_json, expert_command_to_aerovla


def audit() -> dict:
    cases = []
    for name, velocity, rate in [
        ("nonterminal_hold", (0, 0, 0), 0),
        ("forward", (2.5, 0, 0), 0),
        ("lateral_left", (0, 2.5, 0), 0),
        ("yaw_only", (0, 0, 0), 0.4),
    ]:
        command = ControlCommand(
            t_sim_ns=0, velocity=Vec3(x=velocity[0], y=velocity[1], z=velocity[2]),
            yaw_rate_rps=rate,
        )
        target = expert_command_to_aerovla(command, yaw_rad=0, horizon_s=0.25)
        action, decoded = action_from_output(target, yaw_rad=0)
        assert action is not None
        result_velocity = [action.velocity.x, action.velocity.y, action.velocity.z]
        cases.append({
            "case": name, "teacher_velocity_enu_mps": list(velocity),
            "teacher_yaw_rate_rps": rate, "label_horizon_s": 0.25,
            "label": json.loads(action_json(target)), "decoded_offsets": decoded,
            "decoded_velocity_enu_mps": result_velocity,
            "decoded_yaw_rate_rps": action.yaw_rate_rps,
            "decoded_duration_s": action.duration_s,
            "velocity_error_mps": math.dist(velocity, result_velocity),
            "yaw_rate_error_rps": abs(rate - action.yaw_rate_rps),
        })
    return {
        "kind": "analytical_teacher_codec_counterexamples_not_model_predictions",
        "native_codec_modified": False, "cases": cases,
        "conclusion": "Do not equate parseable imitation labels with executable teacher actions.",
        "gate": "blocked pending teacher execution/terminal-observability audit",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(audit(), handle, indent=2)
    print(args.out)
