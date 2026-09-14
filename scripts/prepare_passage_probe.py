"""Freeze three exact RGB-D sources and expectations before six paired calls."""

import asyncio
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import ControlCommand, MissionSpec, Vec3
from uavlab.core.frame_store import global_store

OUT = Path("reports/passage_choice_20260914")
CASES = [
    dict(
        id="visible_target",
        run="c5_depth_ray_v2_20260912_s1061",
        call="call-000040",
        expectation=(
            "Red tower visible near (80,85). A target point must land on red "
            "body. Visibility alone does not prove the narrow gap traversable."
        ),
    ),
    dict(
        id="hidden_openings",
        run="c5_clutter_stable_20260914_s1061",
        call="call-000004",
        expectation=(
            "No red tower visible. Exploration should select free space "
            "between/right of structures, not a gray face. Physical "
            "feasibility checked separately."
        ),
    ),
    dict(
        id="close_wall",
        run="c5_clutter_stable_20260914_s1061",
        call="call-000040",
        expectation=(
            "No red tower; close gray walls cover almost all view. Do not "
            "claim a confident forward passage from the thin left sliver. "
            "Abstention is acceptable; no assertion no route exists outside "
            "view."
        ),
    ),
]


async def main():
    OUT.mkdir(exist_ok=True)
    for run in sorted({c["run"] for c in CASES}):
        root = Path("runs") / run
        m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        cfg = m["environment_config"]
        mission = MissionSpec(
            mission_id="saved-passage",
            instruction=cfg["instruction"],
            task_family=cfg["task_family"],
            success=cfg["params"]["success"],
            constraints=cfg["params"]["constraints"],
        )
        env = DeterministicEnv(**cfg["params"])
        await env.reset(mission, 1061)
        wanted = {}
        for case in CASES:
            if case["run"] == run:
                call = json.loads(
                    (root / "debug/calls" / (case["call"] + ".json")).read_text(encoding="utf-8")
                )
                wanted[call["observation_seq"]] = (case, call)
        poses = 0
        for line in (root / "events.jsonl").read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if e["event_type"] != "control":
                continue
            obs = await env.observe()
            p = e["payload"]
            poses += 1
            assert (
                np.linalg.norm(
                    np.array([obs.position.x, obs.position.y, obs.position.z])
                    - [p["position_x"], p["position_y"], p["position_z"]]
                )
                < 1e-7
            )
            if obs.seq in wanted:
                case, call = wanted.pop(obs.seq)
                raw = (root / call["image_files"][0]).read_bytes()
                img = np.asarray(global_store().get(obs.rgb.uri))
                assert np.array_equal(
                    img, np.asarray(Image.open(root / call["image_files"][0]).convert("RGB"))
                )
                (OUT / (case["id"] + ".png")).write_bytes(raw)
                np.savez_compressed(
                    OUT / (case["id"] + ".npz"), depth=np.asarray(global_store().get(obs.depth.uri))
                )
                case.update(
                    source_seq=obs.seq,
                    source_t=obs.t_sim_ns / 1e9,
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                    observation=obs.model_dump(mode="json"),
                    obstacles=[
                        dict(center=o.center.tolist(), half=o.half.tolist()) for o in env.obstacles
                    ],
                    pose_prefix_checked=poses,
                    depth_renderer=cfg["params"].get("depth_renderer"),
                )
            if not wanted:
                break
            await env.step(
                ControlCommand(
                    t_sim_ns=e["t_sim_ns"],
                    velocity=Vec3(x=p["vx"], y=p["vy"], z=p["vz"]),
                    yaw_rate_rps=p["yaw_rate"],
                ),
                50_000_000,
            )
        assert not wanted
        await env.close()
    source = Path("runs/c5_clutter_stable_20260914_s1061/debug/calls/call-000004.json")
    original = json.loads(source.read_text(encoding="utf-8"))
    baseline = dict(prompt=original["prompt"], schema=original["response_schema"])
    candidate = json.loads(json.dumps(baseline))
    candidate["schema"]["properties"]["kind"]["enum"].append("hold")
    candidate["prompt"] += (
        " Passage check overrides the requirement to always return a movement point:"
        " when the requested target is absent, inspect the space between obstacle "
        "silhouettes before choosing exploration. Choose a broad visible opening "
        "near flight height, not the center of an obstacle or empty sky above it. In"
        " evidence describe the selected opening and its bordering obstacles. If no "
        "clearly usable opening is visible, return kind=hold, u=500, v=500; these "
        "are ignored placeholders, not a movement target. A thin uncertain sliver is"
        " not enough evidence to commit. Do not invent a route outside this image."
    )
    manifest = json.loads(
        Path("runs/c5_clutter_stable_20260914_s1061/manifest.json").read_text(encoding="utf-8")
    )
    freeze = dict(
        cases=CASES,
        variants=dict(baseline=baseline, passage_check=candidate),
        inference=manifest["architecture_config"]["inference"]["params"],
        policy=manifest["architecture_config"]["policy"]["params"],
        calls_budget=6,
        scope=(
            "Saved-source paired diagnostic; hold is probe-only and not "
            "installed in flight runtime. No truth or annotations sent to "
            "model."
        ),
    )
    (OUT / "FREEZE.json").write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    print([(c["id"], c["source_seq"], c["source_t"]) for c in CASES])


if __name__ == "__main__":
    asyncio.run(main())
