"""Independent FRD/control and yaw-dynamics checks of saved visual execution traces."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image

from uavlab.training.visual_yaw_fixture import visible_bearing


def audit(path):
    report = json.loads(path.read_text())
    root = Path(report["output_root"])
    checks = []
    for r in report["segments"]:
        assert (
            hashlib.sha256((root / r["id"] / "before.png").read_bytes()).hexdigest()
            == r["source_image_sha256"]
        )
        assert r["source_image_sha256"] == r["data_row"]["image_sha256"]["mosaic"]
        if r["outcome"] == "invalid_output_no_execution":
            assert not r["controls"] and not r["prediction"]["valid"]
            continue
        assert len(r["controls"]) == 4
        parsed = r["prediction"]["parsed"]
        yaw = r["state_before"]["yaw_enu_rad"]
        f = (parsed["forward_bin"] - 32) * 10 / 64
        right = (parsed["right_bin"] - 32) * 10 / 64
        down = (parsed["down_bin"] - 32) * 10 / 64
        expected = [
            math.cos(yaw) * f + math.sin(yaw) * right,
            math.sin(yaw) * f - math.cos(yaw) * right,
            -down,
        ]
        norm = math.sqrt(sum(x * x for x in expected))
        expected = [x * min(1, 5 / norm) for x in expected] if norm else expected
        expected_yaw = -(parsed["yaw_cw_bin"] - 32) * 3 / 64
        for i, entry in enumerate(r["controls"]):
            command = entry["command"]
            v = command["velocity"]
            assert all(abs(v[k] - x) < 1e-9 for k, x in zip(("x", "y", "z"), expected, strict=True))
            assert command["yaw_rate_rps"] == expected_yaw
            assert command["t_sim_ns"] == i * 50_000_000
            actual_yaw = entry["state"]["yaw_enu_rad"]
            wanted = yaw + i * 0.05 * expected_yaw
            assert (
                abs(math.atan2(math.sin(actual_yaw - wanted), math.cos(actual_yaw - wanted)))
                < 1e-10
            )
        actual_yaw = r["state_after"]["yaw_enu_rad"]
        wanted = yaw + 0.2 * expected_yaw
        assert abs(math.atan2(math.sin(actual_yaw - wanted), math.cos(actual_yaw - wanted))) < 1e-10
        image = root / r["id"] / "after.png"
        assert hashlib.sha256(image.read_bytes()).hexdigest() == r["after_image_sha256"]
        calib = r["data_row"]["intrinsics"]
        try:
            bearing, _ = visible_bearing(
                Image.open(image), r["data_row"]["instruction_colour"], calib["cx"], calib["fx"]
            )
        except ValueError:
            bearing = None
        assert bearing == r["bearing_after"]
        checks.append(
            dict(
                id=r["id"],
                frd_controls_match=True,
                yaw_dynamics_match=True,
                after_image_and_bearing_match=True,
            )
        )
    return dict(passed=True, checks=checks, source_rows=len(report["segments"]))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    r = audit(a.report)
    a.out.write_text(json.dumps(r, indent=2))
    print("PASS", len(r["checks"]), "executed segments")
