"""Compare grounding methods on the exact failed tool image; no inference."""

import asyncio
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from uavlab.adapters.gym.capability_env import CapabilityEnv
from uavlab.contracts import MissionSpec, MemorySnapshot, PerceptionState
from uavlab.core.config import EnvironmentConfig
from uavlab.core.frame_store import global_store
from uavlab.interfaces import DecisionContext
from uavlab.plugins.reasoning.aerialclaw_visual import ObjectLocation, locate_in_depth


async def main():
    root = Path("runs/c1_visual_tool_visible_20260913_s1061")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    config = EnvironmentConfig.model_validate(manifest["environment_config"])
    mission = MissionSpec(
        mission_id="saved-probe",
        instruction=config.instruction,
        task_family=config.task_family,
        success=config.params["success"],
        constraints=config.params["constraints"],
        allowed_skills=config.params["allowed_skills"],
    )
    env = CapabilityEnv(**config.params)
    obs = await env.reset(mission, 1061)
    saved = Image.open(root / "debug/images/call-000002-0.png").convert("RGB")
    rgb = global_store().get(obs.rgb.uri)
    assert np.array_equal(np.asarray(saved), np.asarray(rgb)), (
        "Saved frame differs; cannot reuse geometry"
    )
    assert not obs.semantic_hits and obs.privileged is None
    ctx = DecisionContext(
        mission=mission,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=0,
        episode_id="saved-probe",
    )
    response = json.loads((root / "debug/calls/call-000002.json").read_text(encoding="utf-8"))[
        "response"
    ]
    answer = ObjectLocation.model_validate_json(response)
    depth = global_store().get(obs.depth.uri)
    raw, _ = locate_in_depth(answer, ctx, depth, -0.10)
    refined, d = locate_in_depth(answer, ctx, depth, -0.10, 0.03)
    assert raw is None and refined is not None
    report = {
        "same_saved_rgb_pixels": True,
        "image_sha256": hashlib.sha256(saved.tobytes()).hexdigest(),
        "response": json.loads(response),
        "unrefined_position": None,
        "refined_position": refined.model_dump(),
        "measured_depth_m": d,
        "refinement_fraction": 0.03,
        "new_model_calls": 0,
    }
    Path("reports/aerialclaw_tools_20260913/SAVED_FRAME_GEOMETRY.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))
    await env.close()


if __name__ == "__main__":
    asyncio.run(main())
