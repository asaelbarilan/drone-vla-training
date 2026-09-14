"""Saved flight/source/constraint audit; truth confined to diagnostics; zero inference."""

import asyncio
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import ControlCommand, MissionSpec, Vec3
from uavlab.core.frame_store import global_store

OUT = Path("reports/clutter_stable_20260914")


async def audit(name):
    root = Path("runs") / name
    m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    cfg = m["environment_config"]
    mission = MissionSpec(
        mission_id="saved-audit",
        instruction=cfg["instruction"],
        task_family=cfg["task_family"],
        success=cfg["params"]["success"],
        constraints=cfg["params"]["constraints"],
    )
    env = DeterministicEnv(**cfg["params"])
    await env.reset(mission, 1061)
    calls = {}
    for p in (root / "debug/calls").glob("*.json"):
        c = json.loads(p.read_text(encoding="utf-8"))
        if c["role"] == "policy" and c["status"] == "complete":
            calls[c["observation_seq"]] = c
    lines = (root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    es = [json.loads(line) for line in lines]
    controls = [e for e in es if e["event_type"] == "control"]
    excess = []
    images = 0
    selected = []
    ds = {
        e["payload"]["source_observation_seq"]: e
        for e in es
        if e["event_type"] == "decision_proposed"
    }
    for e in controls:
        obs = await env.observe()
        p = e["payload"]
        assert (
            np.linalg.norm(
                np.array([obs.position.x, obs.position.y, obs.position.z])
                - [p["position_x"], p["position_y"], p["position_z"]]
            )
            < 1e-7
        )
        speed = float(np.linalg.norm([p["vx"], p["vy"], p["vz"]]))
        if speed > 0.6:
            excess.append(speed - 0.6)
        if obs.seq in calls:
            c = calls[obs.seq]
            rgb = np.asarray(global_store().get(obs.rgb.uri))
            assert np.array_equal(
                rgb, np.asarray(Image.open(root / c["image_files"][0]).convert("RGB"))
            )
            images += 1
            if obs.seq in ds and obs.t_sim_ns < 30e9:
                d = ds[obs.seq]
                v = d["payload"]["provenance"]
                u, w = float(v["pixel_u"]), float(v["pixel_v"])
                selected.append(
                    dict(
                        call=c["id"],
                        decision_id=d["trace_id"],
                        source_t=obs.t_sim_ns / 1e9,
                        available_t=d["t_sim_ns"] / 1e9,
                        reply=json.loads(c["response"]),
                        effective_kind=v["waypoint_kind"],
                        pixel_rgb=rgb[round(w), round(u)].tolist(),
                        pixel=[u, w],
                        waypoint=d["payload"]["decision_payload"]["target"],
                    )
                )
        await env.step(
            ControlCommand(
                t_sim_ns=e["t_sim_ns"],
                velocity=Vec3(x=p["vx"], y=p["vy"], z=p["vz"]),
                yaw_rate_rps=p["yaw_rate"],
            ),
            50_000_000,
        )
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    assert len(excess) == result["metrics"]["constraint_violations"]
    assert not excess or max(excess) < 1e-12
    return dict(
        name=name,
        poses_matched=len(controls),
        source_images_matched=images,
        raw_speed_violations=len(excess),
        max_speed_excess_mps=max(excess, default=0),
        effective_kinds=dict(
            Counter(d["payload"]["provenance"]["waypoint_kind"] for d in ds.values())
        ),
        selected_decisions=selected,
    )


async def main():
    rows = [
        await audit(n)
        for n in ("c5_clutter_stable_20260914_s1061", "c5_clutter_attributes_20260914_s1061")
    ]
    for filename in ("FREEZE.json", "REPAIR_FREEZE.json"):
        f = json.loads((OUT / filename).read_text(encoding="utf-8"))
        for p, h in f["source_config_sha256"].items():
            assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == h, p
    for p in OUT.glob("*/debug/sources/*"):
        assert hashlib.sha256(p.read_bytes()).hexdigest() == p.stem, p
    (OUT / "AUDIT.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(
        json.dumps(
            [{k: v for k, v in r.items() if k != "selected_decisions"} for r in rows], indent=2
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
