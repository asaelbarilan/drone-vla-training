"""Bounded localhost AirSim probe; never count cached poses as executed motion.

RPC signatures follow microsoft/AirSim v1.8.1 PythonClient/airsim/client.py.
Uses the already installed msgpackrpc transport without changing model packages.
"""

import argparse
import hashlib
import json
import math
import socket
import time
from pathlib import Path

import msgpackrpc
import numpy as np
from PIL import Image

from uavlab.training.openfly_execution import airsim_pose_components


def normalize_keys(value):
    if isinstance(value, dict):
        return {
            k.decode() if isinstance(k, bytes) else k: normalize_keys(v) for k, v in value.items()
        }
    if isinstance(value, list):
        return [normalize_keys(v) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    assert run.is_relative_to(Path("D:/drone_vla_pilot/simulators/openfly/runtime").resolve())
    assert (run / "process.json").exists()
    report = {
        "renderer_gate_passed": False,
        "model_used": False,
        "events": [],
        "probe_scope": "legacy direct-RPC position/pixel probe; no camera calibration",
    }
    source = json.loads(
        Path("reports/vla_openfly_execution_20260919/source_control.json").read_text()
    )
    pose = source["raw_atomic"]["steps"][0]["observed_pose"]
    report["requested_source_pose"] = pose
    x, y, z, yaw = airsim_pose_components(pose)
    target = {
        "position": {"x_val": x, "y_val": y, "z_val": z},
        "orientation": {
            "w_val": math.cos(yaw / 2),
            "x_val": 0.0,
            "y_val": 0.0,
            "z_val": math.sin(yaw / 2),
        },
    }
    rpc = None
    start = time.monotonic()

    def call(name, *arguments):
        before = time.monotonic()
        value = normalize_keys(rpc.call(name, *arguments))
        report["events"].append({"method": name, "elapsed_s": time.monotonic() - before})
        return value

    try:
        deadline = time.monotonic() + 35
        while True:
            try:
                with socket.create_connection(("127.0.0.1", 41489), timeout=2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Owned renderer RPC port did not become ready") from None
                time.sleep(1)
        rpc = msgpackrpc.Client(
            msgpackrpc.Address("127.0.0.1", 41489),
            timeout=20,
            pack_encoding="utf-8",
            unpack_encoding=None,
        )
        assert call("ping")
        call("enableApiControl", True, "drone_1")
        call("simPause", False)
        call("simSetVehiclePose", target, True, "drone_1")
        deadline = time.monotonic() + 15
        while True:
            actual = call("simGetVehiclePose", "drone_1")
            report["observed_rpc_pose"] = actual
            p = actual["position"]
            error = math.dist([p[k] for k in ("x_val", "y_val", "z_val")], [x, y, z])
            report["position_error_m"] = error
            if error < 0.05:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Renderer returned stale/unexecuted pose; no flight result")
            time.sleep(0.25)
        call("simPause", True)
        response = call(
            "simGetImages",
            [
                {
                    "camera_name": "front_custom",
                    "image_type": 0,
                    "pixels_as_float": False,
                    "compress": False,
                }
            ],
            "drone_1",
            False,
        )[0]
        pixels = response.pop("image_data_uint8")
        response.pop("image_data_float", None)
        report["image_metadata"] = response
        assert response["width"] > 0 and response["height"] > 0
        array = np.frombuffer(pixels, dtype=np.uint8).reshape(
            response["height"], response["width"], 3
        )
        assert array.std() > 2, "Blank/constant image is not a valid scene observation"
        path = run / "first_render.png"
        Image.fromarray(array).save(path)
        report.update(
            renderer_gate_passed=True, image_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
        )
    except Exception as error:
        report.update(error_type=type(error).__name__, error=str(error))
    finally:
        if rpc:
            rpc.close()
        report["elapsed_s"] = time.monotonic() - start
        (run / "probe.json").write_text(
            json.dumps(
                report,
                indent=2,
                default=lambda v: v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v),
            )
        )
    print(json.dumps(report), flush=True)
    if not report["renderer_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
