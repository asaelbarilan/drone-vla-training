"""D-104: one development episode per selected architecture/scenario, no retries."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
from uavlab.adapters.gym.capability_env import SCENARIOS
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.experiments.manifest import build_manifest, write_manifest

OUT = Path("reports/capability_screen_20260912")
PROFILES = {"c0": "c0", "c5": "c5_capability_gemma_dev"}

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("architectures", nargs="+", choices=PROFILES)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for family in args.architectures:
        for scenario in SCENARIOS:
            name = f"capability_{family}_{scenario}_20260912_s1061"
            dest = Path("runs") / name
            if dest.exists():
                raise RuntimeError(f"Refusing to replace or retry {dest}")
            arch = load_architecture(PROFILES[family])
            env = load_environment(f"capability_{scenario}")
            write_manifest(build_manifest(arch, env, seeds=[1061]), dest)
            print(f"START {name}", flush=True)
            runtime = Orchestrator(arch, env, EpisodeSpec(episode_id=name, seed=1061),
                                   out_dir=dest, debug_capture=True)
            result = await runtime.run()
            data = result.model_dump(mode="json")
            (dest / "result.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
            evidence = OUT / name
            evidence.mkdir(exist_ok=True)
            for filename in ("manifest.json", "result.json"):
                (evidence / filename).write_text((dest / filename).read_text(encoding="utf-8"), encoding="utf-8")
            print(json.dumps({"run": name, "success": data["success"],
                  "termination": data["termination_reason"], "sim_s": data["sim_duration_s"],
                  "wall_s": data["wall_duration_s"], "error": data.get("error")}), flush=True)
            if data.get("error"):
                raise RuntimeError("Infrastructure/protocol error preserved; batch paused for diagnosis")

if __name__ == "__main__":
    asyncio.run(main())
