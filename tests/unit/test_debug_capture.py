"""Exact capture preserves results and records failure evidence without calls."""

import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from uavlab.core.debug_capture import DebugCapture, RecordingInference
from uavlab.core.event_log import EventLog
from uavlab.interfaces import InferenceRequest, InferenceResult


class FakeClock:
    t = 100

    def now_ns(self):
        return self.t


class FakeBackend:
    name = "fake"

    def bind_runtime(self, services):
        self.services = services

    async def invoke(self, request):
        self.services.clock.t = 200
        return InferenceResult(
            payload='{"evidence":"red rectangle","visible":false}', output_tokens=7, latency_ns=50
        )


def test_capture_exact_request_images_and_unmodified_response(tmp_path):
    wrapped = RecordingInference(FakeBackend(), DebugCapture(tmp_path))
    wrapped.bind_runtime(SimpleNamespace(clock=FakeClock()))
    png = b"\x89PNG\r\n\x1a\nexact bytes"
    request = InferenceRequest(
        model_id="fake",
        role="monitor",
        prompt_hash="p",
        prompt="Look at this image",
        observation_seq=7,
        images=(base64.b64encode(png).decode(),),
        response_schema={"type": "object"},
    )
    result = asyncio.run(wrapped.invoke(request))
    record = json.loads(next((tmp_path / "debug/calls").glob("*.json")).read_text())
    assert record["prompt"] == request.prompt
    assert record["response_schema"] == request.response_schema
    assert record["response"] == result.payload
    assert (tmp_path / record["image_files"][0]).read_bytes() == png
    assert record["observation_seq"] == 7
    assert record["started_t_sim_ns"] == 100
    assert record["completed_t_sim_ns"] == 200
    assert result.latency_ns == 50
    assert wrapped.name == "fake"
    assert "images" not in record and "host" not in record


@pytest.mark.parametrize("error", [RuntimeError, asyncio.CancelledError])
def test_failed_or_cancelled_inference_preserves_input(tmp_path, error):
    class Failing(FakeBackend):
        async def invoke(self, request):
            raise error("do not copy transport error text")

    wrapped = RecordingInference(Failing(), DebugCapture(tmp_path))
    wrapped.bind_runtime(SimpleNamespace(clock=FakeClock()))
    with pytest.raises(error):
        asyncio.run(
            wrapped.invoke(
                InferenceRequest(model_id="fake", role="policy", prompt_hash="p", prompt="inspect")
            )
        )
    record = json.loads(next((tmp_path / "debug/calls").glob("*.json")).read_text())
    assert record["status"] in {"error", "cancelled"}
    assert record["prompt"] == "inspect"
    assert "response" not in record
    assert "do not copy" not in json.dumps(record)


def test_default_log_does_not_create_diagnostic_artifacts(tmp_path):
    log = EventLog("default", tmp_path)
    assert log.debug_capture is None
    assert not (tmp_path / "debug").exists()
    log.close()


def test_recorded_source_points_to_immutable_snapshot(tmp_path):
    from uavlab.contracts import EventType

    log = EventLog("captured", tmp_path, debug_capture=True)
    event = log.emit("test", EventType.WARNING, 0, 0, {"reason": "test"})
    source = event.payload["_debug_source"]
    assert source["path"] == str(Path(__file__).resolve())
    assert "test_recorded_source" in (tmp_path / source["snapshot"]).read_text(encoding="utf-8")
    log.close()


def test_opt_in_capture_preserves_simulated_episode_controls(tmp_path):
    from uavlab.core.compose import load_architecture, load_environment
    from uavlab.core.config import EpisodeSpec
    from uavlab.core.orchestrator import Orchestrator

    async def run(capture):
        env = load_environment("grid_nav").model_copy(update={"max_episode_s": 0.3})
        harness = Orchestrator(
            load_architecture("c0"),
            env,
            EpisodeSpec(episode_id="fixture", seed=1061),
            out_dir=tmp_path / str(capture),
            debug_capture=capture,
        )
        result = await harness.run()
        controls = [
            {k: v for k, v in e.payload.items() if not k.startswith("_debug")}
            for e in harness.log.events
            if e.event_type.value == "control"
        ]
        return result, controls

    plain, plain_controls = asyncio.run(run(False))
    recorded, recorded_controls = asyncio.run(run(True))
    assert recorded_controls == plain_controls
    assert recorded.sim_duration_s == plain.sim_duration_s
    assert recorded.metrics["distance_to_goal_m"] == plain.metrics["distance_to_goal_m"]


def test_existing_capture_is_not_silently_mixed_with_another_run(tmp_path):
    capture = DebugCapture(tmp_path)
    capture.write({"id": "call-000001", "prompt": "original"})
    with pytest.raises(ValueError, match="fresh output"):
        DebugCapture(tmp_path)
    assert (
        json.loads((tmp_path / "debug/calls/call-000001.json").read_text())["prompt"] == "original"
    )


def test_cli_rejects_existing_capture_before_touching_manifest(tmp_path):
    from uavlab.cli import main

    (tmp_path / "debug/calls").mkdir(parents=True)
    (tmp_path / "debug/calls/call-000001.json").write_text("{}")
    (tmp_path / "manifest.json").write_text("original manifest")
    assert (
        main(
            [
                "run",
                "--arch",
                "c0",
                "--env",
                "grid_nav",
                "--seed",
                "1061",
                "--out",
                str(tmp_path),
                "--debug-capture",
            ]
        )
        == 2
    )
    assert (tmp_path / "manifest.json").read_text() == "original manifest"
