"""Probe with AirSim's official SDK and OpenFly's initialization order.

No model is loaded. An RPC acknowledgement never counts as executed motion.
The additional camera request after a pose mismatch is diagnostic only.
"""

import argparse
import hashlib
import json
import math
import socket
import sys
import time
from pathlib import Path

from uavlab.training.openfly_execution import airsim_pose_components


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    base = Path("D:/drone_vla_pilot/simulators/openfly").resolve()
    run = args.run_dir.resolve()
    if not run.is_relative_to(base / "runtime") or not (run / "process.json").is_file():
        raise ValueError("Use an existing task-owned launch directory")
    sys.path.insert(0, str(base / "python_client"))
    import airsim
    import numpy as np
    from PIL import Image

    source_path = Path("reports/vla_openfly_execution_20260919/source_control.json")
    source = json.loads(source_path.read_text())
    x, y, z, yaw = airsim_pose_components(source["raw_atomic"]["steps"][0]["observed_pose"])
    out = {
        "client": "official airsim 1.8.1",
        "model_used": False,
        "renderer_gate_passed": False,
        "events": [],
        "requested_airsim_pose": [x, y, z, yaw],
        "source_control_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
    }
    client = None
    started = time.monotonic()

    def call(name, fn):
        before = time.monotonic()
        event = {"call": name}
        try:
            value = fn()
            event["result"] = str(value)[:1500] if name != "simGetImages" else "received"
            return value
        except Exception as error:
            event["error"] = repr(error)
            raise
        finally:
            event["seconds"] = time.monotonic() - before
            out["events"].append(event)

    try:
        deadline = time.monotonic() + 35
        while True:
            try:
                with socket.create_connection(("127.0.0.1", 41489), timeout=1):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise TimeoutError("Owned renderer port did not become ready") from None
                time.sleep(1)
        client = airsim.MultirotorClient(ip="127.0.0.1", port=41489, timeout_value=15)
        if not call("ping", client.ping):
            raise RuntimeError("Renderer ping failed")
        call("enableApiControl", lambda: client.enableApiControl(True, "drone_1"))
        call("armDisarm", lambda: client.armDisarm(True, "drone_1"))
        call(
            "moveByVelocityBodyFrameAsync",
            lambda: client.moveByVelocityBodyFrameAsync(0, 0, 0, 0.02, vehicle_name="drone_1"),
        )
        target = airsim.Pose(airsim.Vector3r(x, y, z), airsim.to_quaternion(0, 0, yaw))
        call("simSetVehiclePose", lambda: client.simSetVehiclePose(target, True, "drone_1"))
        # No pause command: this matches the public OpenFly initialization/capture sequence.
        actual = call("simGetVehiclePose", lambda: client.simGetVehiclePose("drone_1"))
        p = actual.position
        q = actual.orientation
        out["observed_pose"] = actual.to_msgpack()
        out["position_error_m"] = math.dist([p.x_val, p.y_val, p.z_val], [x, y, z])
        target_q = target.orientation
        dot = sum(
            getattr(q, k) * getattr(target_q, k) for k in ("x_val", "y_val", "z_val", "w_val")
        )
        norm = math.sqrt(sum(getattr(q, k) ** 2 for k in ("x_val", "y_val", "z_val", "w_val")))
        out["orientation_error_degrees"] = math.degrees(2 * math.acos(min(1, abs(dot) / norm)))
        images = call(
            "simGetImages",
            lambda: client.simGetImages(
                [airsim.ImageRequest("front_custom", airsim.ImageType.Scene, False, False)],
                "drone_1",
            ),
        )
        if not images or images[0].width <= 0 or images[0].height <= 0:
            raise RuntimeError("Renderer returned no scene pixels")
        response = images[0]
        array = np.frombuffer(response.image_data_uint8, dtype=np.uint8).reshape(
            response.height, response.width, 3
        )
        out["image"] = {
            "width": response.width,
            "height": response.height,
            "std": float(array.std()),
            "timestamp": response.time_stamp,
            "camera_position": response.camera_position.to_msgpack(),
            "camera_orientation": response.camera_orientation.to_msgpack(),
        }
        path = run / "official_client.png"
        Image.fromarray(array).save(path)
        out["image"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        cp = response.camera_position
        # Official front_custom has a +1 metre NED Z offset, with zero roll/pitch.
        out["camera_position_error_m"] = math.dist([cp.x_val, cp.y_val, cp.z_val], [x, y, z + 1])
        out["renderer_gate_passed"] = bool(
            out["position_error_m"] < 0.05
            and out["orientation_error_degrees"] < 0.1
            and out["camera_position_error_m"] < 0.05
            and array.std() > 2
        )
    except Exception as error:
        out.update(error_type=type(error).__name__, error=str(error))
    finally:
        if client is not None:
            client.client.close()
        out["elapsed_s"] = time.monotonic() - started
        (run / "official_client_probe.json").write_text(
            json.dumps(out, indent=2, default=lambda v: v.to_msgpack()), encoding="utf-8"
        )
    print(json.dumps(out, default=lambda v: v.to_msgpack()), flush=True)
    if not out["renderer_gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
