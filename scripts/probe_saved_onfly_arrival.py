"""Replay exact saved monitor inputs/controls; no network or model inference."""

import asyncio
import base64
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.adapters.gym.capability_env import CapabilityEnv
from uavlab.contracts import ControlCommand, MemorySnapshot, MissionSpec, PerceptionState, Vec3
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult
from uavlab.plugins.reasoning.onfly import OnFlyMonitor


def services(model):
    return RuntimeServices(
        clock=SimClock(),
        log=EventLog("saved-arrival"),
        feature_cache=FeatureCache(),
        inference=model,
        episode_id="saved-arrival",
    )


ROOT = Path("runs/frozen_c5_visible_target_20260913_s1061")
OUT = Path("reports/targeted_contracts_20260913")


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
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    cfg = manifest["environment_config"]
    mission = MissionSpec(
        mission_id="saved-arrival",
        instruction=cfg["instruction"],
        task_family=cfg["task_family"],
        success=cfg["params"]["success"],
        constraints=cfg["params"]["constraints"],
        allowed_skills=cfg["params"]["allowed_skills"],
    )
    calls = {
        c["observation_seq"]: c
        for p in (ROOT / "debug/calls").glob("*.json")
        if (c := json.loads(p.read_text(encoding="utf-8")))["role"] == "monitor"
        and c["status"] == "complete"
    }
    controls = [
        json.loads(line)
        for line in (ROOT / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["event_type"] == "control"
    ]
    result = {}
    for variant in ("legacy", "persistent", "availability_window"):
        model = SavedModel()
        params = dict(manifest["architecture_config"]["monitor"]["params"])
        params["arrival_memory_s"] = {"legacy": 0, "persistent": 3.0, "availability_window": 4.0}[
            variant
        ]
        monitor = OnFlyMonitor(**params)
        bind(monitor, services(model))
        monitor.reset(mission, 1061)
        env = CapabilityEnv(**cfg["params"])
        await env.reset(mission, 1061)
        rows = []
        poses = 0
        for e in controls:
            obs = await env.observe()
            t = obs.t_sim_ns / 1e9
            if t > 16:
                break
            p = e["payload"]
            assert (
                np.linalg.norm(
                    np.array([obs.position.x, obs.position.y, obs.position.z])
                    - [p["position_x"], p["position_y"], p["position_z"]]
                )
                < 1e-7
            )
            poses += 1
            for row in rows:
                if (
                    row["label"] == "stop"
                    and "live_recheck_accepted" not in row
                    and obs.t_sim_ns >= row["available_t_ns"]
                ):
                    row["live_recheck_accepted"] = monitor.stop_still_supported(obs)
                    row["live_recheck_t_s"] = t
                    row["original_target_age_at_available_s"] = (
                        obs.t_sim_ns - monitor._tracked_target_t_ns
                    ) / 1e9
            if obs.seq in calls:
                c = calls[obs.seq]
                model.reply = c["response"]
                model.image = c["image_files"][0]
                ctx = DecisionContext(
                    mission=mission,
                    observation=obs,
                    perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
                    memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
                    t_sim_ns=obs.t_sim_ns,
                    t_wall_ns=0,
                    episode_id="saved-arrival",
                )
                progress = await monitor.assess(ctx)
                rows.append(
                    dict(
                        available_t_ns=c["completed_t_sim_ns"],
                        source_t=t,
                        source_seq=obs.seq,
                        call=c["id"],
                        response=json.loads(c["response"]),
                        label=progress.label.value,
                        evidence=progress.evidence,
                        image_sha256=hashlib.sha256((ROOT / model.image).read_bytes()).hexdigest(),
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
        await env.close()
        result[variant] = dict(poses=poses, monitor_inputs=len(rows), rows=rows)
    assert not any(r["label"] == "stop" for r in result["legacy"]["rows"])
    assert [r["source_t"] for r in result["persistent"]["rows"] if r["label"] == "stop"] == [11.95]
    candidates = [r for r in result["persistent"]["rows"] if r["label"] == "stop"]
    assert len(candidates) == 1 and candidates[0]["live_recheck_accepted"] is False
    assert candidates[0]["original_target_age_at_available_s"] == 3.25
    window = [r for r in result["availability_window"]["rows"] if r["label"] == "stop"]
    assert window[0]["source_t"] == 11.95 and window[0]["live_recheck_accepted"] is True
    (OUT / "SAVED_ONFLY_AVAILABILITY.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(
        json.dumps({v: [(r["source_t"], r["label"]) for r in x["rows"]] for v, x in result.items()})
    )


if __name__ == "__main__":
    asyncio.run(main())
