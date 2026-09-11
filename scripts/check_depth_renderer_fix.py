"""D-98: validate corrected depth on the saved flight without inference."""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path

import numpy as np
from audit_waypoint_handoff import owner_mask, ray_box_depth
from PIL import Image
from probe_passage_4160 import DT_NS, command
from probe_super_passage_4160 import xyz

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.adapters.gym.render import render_depth_frame
from uavlab.analysis.flight_debugger import read_events, read_json
from uavlab.contracts import MissionConstraints, MissionSpec, SuccessCriteria
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.frame_store import global_store
from uavlab.plugins.reasoning.onfly import _depth_at, bearing_gated_range


async def main():
    run = Path("runs/c5_guarded_monitor_20260911_s1061")
    audit = Path("reports/waypoint_handoff_audit_20260912")
    out = Path("reports/depth_renderer_fix_20260912")
    out.mkdir(parents=True, exist_ok=True)
    manifest = read_json(run / "manifest.json")
    data = read_json(audit / "trace.json")
    sources = {row["source_seq"]: row for row in data["decisions"]}
    before = manifest["environment_config"]
    after = load_environment("grid_nav_onfly_depth_v2_dev").model_dump(mode="json")
    normalized = {**after, "id": before["id"], "params": dict(after["params"])}
    assert normalized["params"].pop("depth_renderer") == "box_ray_v2"
    assert normalized == before, "Unintended environment difference"
    assert (
        load_architecture("c5_gemma_guarded_monitor_dev").model_dump(mode="json")
        == manifest["architecture_config"]
    )
    params = {**before["params"], **before["adapter"]["params"], "allow_privileged": False}
    mission = MissionSpec(
        mission_id="depth-fix-pixel-check",
        instruction=before["instruction"],
        task_family=before["task_family"],
        constraints=MissionConstraints.model_validate(params["constraints"]),
        success=SuccessCriteria.model_validate(params.get("success", {})),
    )
    env = DeterministicEnv(**params)
    await env.reset(mission, 1061)
    rows = []
    poses = 0
    for event in read_events(run / "events.jsonl"):
        if event["event_type"] != "control":
            continue
        obs = await env.observe()
        payload = event["payload"]
        assert math.dist(xyz(obs.position), [payload[f"position_{a}"] for a in "xyz"]) < 1e-9
        poses += 1
        if obs.seq in sources:
            source = sources[obs.seq]
            old = global_store().get(obs.depth.uri)
            assert np.array_equal(
                old, np.load(audit / "frames" / f"{obs.seq:04d}_depth.npz")["depth"]
            )
            rgb = np.array(global_store().get(obs.rgb.uri))
            assert np.array_equal(rgb, np.array(Image.open(audit / source["rgb_file"])))
            corrected = render_depth_frame(
                np.array(xyz(obs.position)),
                obs.yaw_rad,
                env.obstacles,
                env.landmarks,
                env.target_label,
                env._camera,
                {h.label for h in obs.semantic_hits},
                renderer="box_ray_v2",
            )
            u, v = source["pixel"]
            depth = _depth_at(corrected, u, v)
            raw_depth = min(7.0, depth if depth is not None else 7.0)
            intr = obs.intrinsics
            gated = bearing_gated_range(
                raw_depth,
                u,
                fx=intr.fx,
                cx=intr.cx,
                half_fov_rad=math.atan(intr.width / (2 * intr.fx)),
                sigma_theta=0.65,
            )
            point = env._camera.unproject(u, v, gated, np.array(xyz(obs.position)), obs.yaw_rad)
            row = {
                "source_seq": obs.seq,
                "available_s": source["available_s"],
                "old_sample_m": source["raw_patch_median_m"],
                "corrected_sample_m": depth,
                "new_waypoint": point.tolist(),
                "old_waypoint": source["world_waypoint"],
                "waypoint_change_m": math.dist(point, source["world_waypoint"]),
                "checked_patch_surface_pixels": 0,
                "max_patch_error_m": 0.0,
            }
            owners, _ = owner_mask(env, obs)
            for y in range(round(v) - 2, round(v) + 3):
                for x in range(round(u) - 2, round(u) + 3):
                    if not (0 <= y < intr.height and 0 <= x < intr.width):
                        continue
                    index = int(owners[y, x]) - 1
                    if not 0 <= index < len(env.obstacles):
                        continue
                    obstacle = env.obstacles[index]
                    origin = np.array(xyz(obs.position))
                    ray = env._camera.unproject(x, y, 1.0, origin, obs.yaw_rad) - origin
                    expected = ray_box_depth(origin, ray, obstacle.center, obstacle.half)
                    actual = float(corrected[y, x])
                    if expected <= 0.2 or not math.isfinite(expected):
                        assert math.isinf(actual)
                    else:
                        error = abs(actual - expected)
                        assert error < 1e-5, (obs.seq, x, y, actual, expected)
                        row["max_patch_error_m"] = max(error, row["max_patch_error_m"])
                    row["checked_patch_surface_pixels"] += 1
            rows.append(row)
            if source["available_s"] == 41:
                np.savez_compressed(
                    out / "source_800_depth_comparison.npz", legacy=old, corrected=corrected
                )
        await env.step(
            command(obs.t_sim_ns, [payload[k] for k in ("vx", "vy", "vz")], payload["yaw_rate"]),
            DT_NS,
        )
    summary = {
        "poses_matched": poses,
        "source_rgb_and_legacy_depth_images_matched": len(rows),
        "surface_patch_pixels_checked": sum(r["checked_patch_surface_pixels"] for r in rows),
        "max_surface_depth_error_m": max(r["max_patch_error_m"] for r in rows),
        "only_environment_change": "depth_renderer=box_ray_v2",
        "architecture_unchanged": True,
        "model_calls": 0,
        "selected_decision": next(r for r in rows if r["available_s"] == 41),
    }
    (out / "SAVED_PIXEL_CHECK.json").write_text(
        json.dumps({"summary": summary, "sources": rows}, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)
    await env.close()


if __name__ == "__main__":
    asyncio.run(main())
