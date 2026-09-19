"""Launch the task-owned scene after D150 archive verification; bounded lifetime/logs."""

import argparse
import json
import re
import socket
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--mode", choices=("offscreen", "xvfb", "opengl"), default="xvfb")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--clock", choices=("official", "ScalableClock"), default="official")
    args = parser.parse_args()
    if not re.fullmatch("[a-z0-9_]+", args.name) or not 30 <= args.seconds <= 300:
        parser.error("Use a simple run name and a 30..300 second lifetime")
    try:
        with socket.create_connection(("127.0.0.1", 41489), timeout=1):
            raise RuntimeError(
                "Port 41489 is occupied; do not overwrite a running scene's settings"
            )
    except (ConnectionRefusedError, TimeoutError):
        pass
    base = Path("D:/drone_vla_pilot/simulators/openfly")
    scene = base / "env_airsim_18/LinuxNoEditor"
    run = base / "runtime" / args.name
    run.mkdir(parents=True, exist_ok=False)
    settings_path = scene / "AirVLN/Binaries/Linux/settings.json"
    original = settings_path.with_name("settings.official.json")
    if not original.exists():
        original.write_bytes(settings_path.read_bytes())
    settings = json.loads(original.read_text())
    settings.update(ApiServerPort=41489, LocalHostIp="127.0.0.1", RpcEnabled=True)
    if args.clock != "official":
        settings["ClockType"] = args.clock
    for sensor in settings["Vehicles"]["drone_1"]["Sensors"].values():
        if sensor.get("SensorType") == 6:
            sensor.update(Enabled=False, DrawDebugPoints=False)
    text = json.dumps(settings, indent=2)
    # This release reads adjacent settings and ignored the standard CLI override.
    settings_path.write_text(text)
    (run / "settings.json").write_text(text)
    linux = "/mnt/d/drone_vla_pilot/simulators/openfly/env_airsim_18/LinuxNoEditor"
    cmd = ["wsl.exe", "-d", "Ubuntu-22.04", "--cd", linux, "--"]
    if args.mode != "offscreen":
        cmd += ["xvfb-run", "-a", "-s", "-screen 0 640x480x24 -nolisten tcp"]
    cmd += ["timeout", "--signal=TERM", "--kill-after=5s", f"{args.seconds}s"]
    if args.mode == "opengl":
        cmd += ["env", "LIBGL_ALWAYS_SOFTWARE=1"]
    cmd += [
        linux + "/AirVLN/Binaries/Linux/AirVLN-Linux-Shipping",
        "AirVLN",
        "-opengl4" if args.mode == "opengl" else "-vulkan",
        "-nosound",
        "-unattended",
        "-nosplash",
        "-ResX=640",
        "-ResY=360",
        "-stdout",
        "-FullStdOutLogOutput",
    ]
    cmd += ["-RenderOffscreen"] if args.mode == "offscreen" else ["-windowed"]
    with (run / "stdout.log").open("wb") as log:
        process = subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW
        )
    record = {
        "pid": process.pid,
        "command": cmd,
        "run": str(run),
        "mode": args.mode,
        "started_unix": time.time(),
        "deadline_seconds": args.seconds,
        "camera": "unchanged official 1920x1080/front_custom settings",
        "settings_changes": ["localhost RPC41489", "unused lidar disabled"],
        "clock": args.clock,
        "model_used": False,
    }
    (run / "process.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record))


if __name__ == "__main__":
    main()
