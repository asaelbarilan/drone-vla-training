"""One local Gemma call on a recorded initial RGB, no flight or automatic retry."""

import asyncio
import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.contracts import (
    MemorySnapshot,
    MissionConstraints,
    MissionSpec,
    PerceptionState,
    SuccessCriteria,
)
from uavlab.core.clock import SimClock
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.debug_capture import RecordingInference
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.frame_store import global_store
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext


async def main():
    out = Path("reports/adaptive_plan_flights_20260912/preflight")
    arch = load_architecture("vlm_adaptive_plan_gemma_dev")
    cfg = load_environment("grid_nav_onfly_depth_v2_dev")
    mission = MissionSpec(
        mission_id="adaptive-preflight",
        instruction=cfg.instruction,
        task_family=cfg.task_family,
        success=SuccessCriteria.model_validate(cfg.params.get("success", {})),
        constraints=MissionConstraints.model_validate(cfg.params.get("constraints", {})),
    )
    env = REGISTRY.build("environment", cfg.adapter.name, {**cfg.params, **cfg.adapter.params})
    obs = await env.reset(mission, 1061)
    saved = Path("runs/c5_depth_ray_v2_20260912_s1061/debug/images/call-000001-0.png")
    image = Image.open(saved).convert("RGB")
    assert np.array_equal(np.asarray(image), np.asarray(global_store().get(obs.rgb.uri)))
    global_store().put(obs.rgb.uri, image)
    tags = json.load(urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10))
    tag = next(x for x in tags["models"] if x["name"] == "gemma4:e2b")
    assert tag["digest"] == arch.inference.params["expected_digest"]
    log = EventLog("adaptive-preflight", out, debug_capture=True)
    clock = SimClock()
    backend = REGISTRY.build("inference", arch.inference.name, arch.inference.params)
    # No transport retry on this single-call diagnostic.
    post = backend._post
    backend._post = lambda path, body: post(path, body, _retry=False)
    recorded = RecordingInference(backend, log.debug_capture)
    services = RuntimeServices(
        clock=clock,
        log=log,
        feature_cache=FeatureCache(),
        inference=recorded,
        episode_id="adaptive-preflight",
    )
    bind(recorded, services)
    policy = REGISTRY.build("policy", arch.policy.name, arch.policy.params)
    bind(policy, services)
    policy.reset(mission, 1061)
    ctx = DecisionContext(
        mission=mission,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="adaptive-preflight",
    )
    summary = {
        "source_rgb": str(saved),
        "source_rgb_sha256": hashlib.sha256(saved.read_bytes()).hexdigest(),
        "source_pixels_match_reconstructed_initial_pose": True,
        "model_digest": tag["digest"],
        "model_calls_budget": 1,
        "flight": False,
    }
    try:
        task = asyncio.create_task(policy.decide(ctx))
        while not task.done():
            await asyncio.sleep(0)
            clock.advance()
        result = await task
        summary.update(valid=True, decision=result.model_dump(mode="json"), plan=policy.snapshot())
    except Exception as exc:
        summary.update(valid=False, error=str(exc))
    finally:
        summary["inference_stats"] = backend.stats()
        (out / "RESULT.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        log.close()
        backend.close()
        await env.close()
    print(json.dumps(summary, indent=2))
    if not summary["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
