"""Read-only training-host inventory; no environment/credential/key enumeration.

Run on the actual GPU host with python3. No third-party packages required.
Use --torch-probe only when a small CUDA context allocation is acceptable.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def command(args: list[str]) -> dict:
    executable = shutil.which(args[0])
    if executable is None:
        return {"available": False}
    try:
        result = subprocess.run(
            [executable, *args[1:]], capture_output=True, text=True, timeout=20, check=False
        )
        return {"available": True, "exit_code": result.returncode,
                "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"available": True, "error": "timeout after 20 seconds"}


def inventory(storage: Path, torch_probe: bool = False) -> dict:
    disk = shutil.disk_usage(storage)
    packages = {}
    for name in ["torch", "torchvision", "transformers", "accelerate", "peft",
                 "bitsandbytes", "ms-swift", "flash-attn", "qwen-vl-utils"]:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    report = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "os": platform.system(), "os_release": platform.release(),
        "architecture": platform.machine(), "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0], "packages": packages,
        "storage": {"path": str(storage.resolve()), "total_bytes": disk.total,
                    "used_bytes": disk.used, "free_bytes": disk.free},
        "gpu": command(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,"
                        "utilization.gpu,driver_version", "--format=csv,noheader"]),
        "cuda_toolkit": command(["nvcc", "--version"]),
        "instance_type": None, "region": None, "hourly_rate_usd": None,
        "billing_note": "Confirm instance type, region, purchase option and price separately.",
    }
    if platform.system() == "Linux":
        report["memory"] = {
            line.split(":", 1)[0]: line.split(":", 1)[1].strip()
            for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:", "SwapFree:"))
        }
        report["block_storage"] = command(["lsblk", "-b", "-o", "NAME,SIZE,TYPE,MOUNTPOINT"])
    if torch_probe:
        import torch

        report["torch_runtime"] = {
            "cuda_available": torch.cuda.is_available(), "cuda_build": torch.version.cuda,
            "device_count": torch.cuda.device_count(),
            "bf16_supported": (
                torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False
            ),
        }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", type=Path, default=Path.cwd())
    parser.add_argument("--torch-probe", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    payload = json.dumps(inventory(args.storage, args.torch_probe), indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    print(payload)
