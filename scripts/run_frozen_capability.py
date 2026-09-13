"""D-106: frozen 24-cell development comparison, one launch per cell."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from uavlab.adapters.gym.capability_env import SCENARIOS
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.experiments.manifest import build_manifest, write_manifest

OUT = Path("reports/frozen_capability_20260913")
FROZEN = OUT / "FREEZE.json"


def cells():
    result = []
    for family in ("c0", "c1", "c5"):
        for scenario in SCENARIOS:
            visual = family == "c1" and scenario in ("visible_target", "turn_search")
            profile = {
                "c0": "c0",
                "c1": "c1_capability_gemma_dev",
                "c5": "c5_capability_gemma_dev",
            }[family]
            if visual:
                profile = "c1_visual_search_gemma_dev"
            result.append(
                dict(
                    family=family,
                    scenario=scenario,
                    profile=profile,
                    environment=f"capability_{scenario}" + ("_tools" if visual else ""),
                    name=f"frozen_{family}_{scenario}_20260913_s1061",
                    integration_limited=family == "c1"
                    and scenario not in ("known_goal", "visible_target", "turn_search"),
                )
            )
    return sorted(result, key=lambda c: c["name"] != "frozen_c1_turn_search_20260913_s1061")


def snapshot():
    paths = sorted([*Path("src").rglob("*.py"), *Path("configs").rglob("*.yaml")])
    return {p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def resolved(cell):
    return dict(
        architecture=load_architecture(cell["profile"]).model_dump(mode="json"),
        environment=load_environment(cell["environment"]).model_dump(mode="json"),
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("freeze", "search", "remaining"))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    matrix = cells()
    if args.stage == "freeze":
        if FROZEN.exists():
            raise RuntimeError("Freeze already exists")
        for c in matrix:
            if (Path("runs") / c["name"]).exists():
                raise RuntimeError("Run name already exists")
        frozen = dict(
            source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            hashes=snapshot(),
            cells=[{**c, **resolved(c)} for c in matrix],
        )
        FROZEN.write_text(json.dumps(frozen, indent=2), encoding="utf-8")
        print("FROZEN 24 cells", flush=True)
        return
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    assert snapshot() == frozen["hashes"], "Source/config changed after freeze"
    selected = matrix[:1] if args.stage == "search" else matrix[1:]
    if args.stage == "remaining":
        assert (OUT / "SEARCH_INSPECTED.md").exists(), "Inspect first flight before remaining cells"
    for cell in selected:
        assert snapshot() == frozen["hashes"]
        saved = next(c for c in frozen["cells"] if c["name"] == cell["name"])
        cfg = resolved(cell)
        assert all(cfg[k] == saved[k] for k in cfg)
        dest = Path("runs") / cell["name"]
        if dest.exists():
            raise RuntimeError(f"Refusing retry or overwrite: {dest}")
        arch = load_architecture(cell["profile"])
        env = load_environment(cell["environment"])
        write_manifest(build_manifest(arch, env, seeds=[1061]), dest)
        print("START", cell["name"], flush=True)
        runtime = Orchestrator(
            arch,
            env,
            EpisodeSpec(episode_id=cell["name"], seed=1061),
            out_dir=dest,
            debug_capture=True,
        )
        result = await runtime.run()
        data = result.model_dump(mode="json")
        (dest / "result.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
        evidence = OUT / cell["name"]
        evidence.mkdir(exist_ok=True)
        for filename in ("manifest.json", "result.json"):
            (evidence / filename).write_bytes((dest / filename).read_bytes())
        print(
            json.dumps(
                dict(
                    run=cell["name"],
                    success=data["success"],
                    termination=data["termination_reason"],
                    sim_s=data["sim_duration_s"],
                    wall_s=data["wall_duration_s"],
                    error=data.get("error"),
                )
            ),
            flush=True,
        )
        if data.get("error"):
            raise RuntimeError("Runtime error preserved; stopping batch")


if __name__ == "__main__":
    asyncio.run(main())
