"""Three saved-image recognition checks; no navigation or simulator-truth input.

Call only after the bounded flight series. The capture stage uses an ordinary
reset observation solely to construct the exact monitor prompt/schema; its
synthetic depth is never used to claim arrival. Results score recognition only.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from PIL import Image

from uavlab.contracts import MemorySnapshot, PerceptionState
from uavlab.core.clock import SimClock
from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.frame_store import global_store
from uavlab.core.orchestrator import Orchestrator
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import DecisionContext, InferenceResult
from uavlab.plugins.inference.ollama import OllamaInference
from uavlab.plugins.reasoning.onfly import OnFlyMonitor


class Capture:
    async def invoke(self, request):
        self.request = request
        return InferenceResult(
            payload=json.dumps(
                dict(evidence="capture", visible=False, u=None, v=None, observed_color="unknown")
            ),
            output_tokens=0,
            latency_ns=0,
        )


async def main():
    config = Path("configs")
    arch = load_architecture("c5_gemma_guarded_monitor_dev", config)
    env_cfg = load_environment("grid_nav_onfly_native_dynamics", config)
    harness = Orchestrator(arch, env_cfg, EpisodeSpec(episode_id="saved_image_checks", seed=1061))
    params = {**env_cfg.params, **env_cfg.adapter.params, "allow_privileged": False}
    env = harness.registry.build("environment", env_cfg.adapter.name, params)
    await env.reset(harness.mission, 1061)
    backend = OllamaInference(**arch.inference.params)
    rows = []
    for name, filename, expected_color in [
        ("false_stop_gray", "GEMMA_YAW_FALSE_STOP_20260911.png", "gray"),
        ("visible_approach", "C5_VISIBLE_APPROACH_20260911.png", "red"),
        ("genuine_arrival", "C5_TRUE_ARRIVAL_20260911.png", "red"),
    ]:
        observation = await env.observe()
        path = Path("reports/paper_implementation") / filename
        global_store().put(observation.rgb.uri, Image.open(path).convert("RGB"))
        ctx = DecisionContext(
            mission=harness.mission,
            observation=observation,
            perception=PerceptionState(
                observation_seq=observation.seq, t_sim_ns=observation.t_sim_ns
            ),
            memory=MemorySnapshot(observation_seq=observation.seq, t_sim_ns=observation.t_sim_ns),
            t_sim_ns=observation.t_sim_ns,
            t_wall_ns=0,
            episode_id="saved_image_checks",
        )
        capture = Capture()
        monitor = OnFlyMonitor(**arch.monitor.params)
        monitor.reset(harness.mission, 1061)
        monitor.bind_runtime(
            RuntimeServices(
                clock=SimClock(),
                log=EventLog("saved_image_checks", None),
                feature_cache=FeatureCache(),
                inference=capture,
            )
        )
        await monitor.assess(ctx)
        response = await backend.invoke(capture.request)
        row = dict(
            frame=name,
            image=str(path),
            expected_color=expected_color,
            model=backend.model_id,
            prompt=capture.request.prompt,
            schema=capture.request.response_schema,
            response=response.payload,
            scope="image recognition only; not arrival or navigation",
        )
        rows.append(row)
        print(json.dumps(row), flush=True)
    Path("reports/paper_implementation/GUARDED_MONITOR_FRAME_CHECKS_20260911.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    backend.close()
    await env.close()


if __name__ == "__main__":
    asyncio.run(main())
