"""Replay exact saved monitor inputs/controls; no network or model inference."""

import asyncio
import base64
import json
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.adapters.gym.capability_env import CapabilityEnv
from uavlab.contracts import ControlCommand, MissionSpec, Vec3
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import InferenceResult


def services(model):
    return RuntimeServices(
        clock=SimClock(),
        log=EventLog("saved-arrival"),
        feature_cache=FeatureCache(),
        inference=model,
        episode_id="saved-arrival",
    )


ROOT = Path("runs/c5_hover_contract_20260913_s1061")
OUT = Path("reports/hover_cycle_20260913")


class SavedModel:
    name = "saved_response_only"
    reply = ""
    image = b""

    async def invoke(self, request):
        from io import BytesIO

        actual = np.asarray(Image.open(BytesIO(base64.b64decode(request.images[0]))).convert("RGB"))
        expected = np.asarray(Image.open(ROOT / self.image).convert("RGB"))
        assert np.array_equal(actual, expected), "Saved input pixels differ"
        return InferenceResult(payload=self.reply)


async def main():
    from uavlab.core.frame_store import global_store
    from uavlab.plugins.reasoning.onfly import _depth_at

    manifest = json.loads((ROOT / "manifest.json").read_text())
    cfg = manifest["environment_config"]
    mission = MissionSpec(
        mission_id="probe",
        instruction=cfg["instruction"],
        task_family=cfg["task_family"],
        success=cfg["params"]["success"],
        constraints=cfg["params"]["constraints"],
    )
    env = CapabilityEnv(**cfg["params"])
    await env.reset(mission, 1061)
    calls = {
        c["observation_seq"]: c
        for f in (ROOT / "debug/calls").glob("*.json")
        if (c := json.loads(f.read_text()))["role"] == "monitor" and c["status"] == "complete"
    }
    rows = []
    for line in (ROOT / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["event_type"] != "control":
            continue
        obs = await env.observe()
        p = e["payload"]
        assert (
            np.linalg.norm(
                np.array([obs.position.x, obs.position.y, obs.position.z])
                - [p["position_x"], p["position_y"], p["position_z"]]
            )
            < 1e-7
        )
        if obs.seq in calls:
            c = calls[obs.seq]
            r = json.loads(c["response"])
            assert np.array_equal(
                np.asarray(global_store().get(obs.rgb.uri)),
                np.asarray(Image.open(ROOT / c["image_files"][0]).convert("RGB")),
            )
            depth = np.asarray(global_store().get(obs.depth.uri))
            u, v = r.get("u"), r.get("v")
            d = (
                _depth_at(depth, u * 223 / 999, v * 223 / 999, patch=0)
                if u is not None and v is not None
                else None
            )
            rows.append(
                dict(
                    t=obs.t_sim_ns / 1e9,
                    reply=r,
                    selected_depth=d,
                    depth_min=float(np.nanmin(depth)),
                    depth_max=float(np.nanmax(depth)),
                    position=obs.position.model_dump(),
                    yaw=obs.yaw_rad,
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
    (OUT / "GROUNDING_AUDIT.json").write_text(json.dumps(rows, indent=2) + "\n")
    for r in rows:
        if 10 <= r["t"] <= 26:
            print(json.dumps(r))


if __name__ == "__main__":
    asyncio.run(main())
