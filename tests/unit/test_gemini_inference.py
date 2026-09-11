import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from uavlab.interfaces import InferenceRequest
from uavlab.plugins.inference import gemini


def setup_backend(monkeypatch):
    monkeypatch.setattr(gemini, "configuration", lambda _: {})
    return gemini.GeminiInference(model_id="gemini-3.5-flash", fixed_latency_s={"policy": 1.0})


def request(model="gemini-3.5-flash"):
    return InferenceRequest(
        model_id=model,
        role="policy",
        prompt_hash="test",
        input_tokens=1,
        prompt="find target",
        images=("png-base64",),
        response_schema={"type": "object"},
    )


def test_backend_preserves_payload_and_charges_fixed_time(monkeypatch):
    backend = setup_backend(monkeypatch)
    transport = Mock(
        return_value={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"text": "private reasoning", "thought": True},
                            {"text": '{"u":93}'},
                        ]
                    },
                }
            ],
            "usageMetadata": {"candidatesTokenCount": 5},
            "modelVersion": "gemini-3.5-flash",
        }
    )
    monkeypatch.setattr(gemini, "invoke_images", transport)
    clock = SimpleNamespace(sleep_ns=AsyncMock(), now_ns=lambda: 1, wall_ns=lambda: 2)
    log = Mock()
    backend.bind_runtime(SimpleNamespace(clock=clock, log=log))
    result = asyncio.run(backend.invoke(request()))
    assert result.payload == '{"u":93}'
    assert result.output_tokens == 5
    assert transport.call_args.args[1:3] == (
        "find target",
        [{"mimeType": "image/png", "data": "png-base64"}],
    )
    assert transport.call_args.kwargs["schema"] == {"type": "object"}
    clock.sleep_ns.assert_awaited_once_with(1_000_000_000)
    assert log.emit.call_args.kwargs["payload"]["backend"] == "gemini"


def test_model_mismatch_never_calls_transport(monkeypatch):
    backend = setup_backend(monkeypatch)
    transport = Mock()
    monkeypatch.setattr(gemini, "invoke_images", transport)
    with pytest.raises(ValueError, match="mismatch"):
        asyncio.run(backend.invoke(request("other")))
    transport.assert_not_called()


def test_truncation_is_not_a_navigation_response(monkeypatch):
    backend = setup_backend(monkeypatch)
    monkeypatch.setattr(
        gemini, "invoke_images", Mock(return_value={"candidates": [{"finishReason": "MAX_TOKENS"}]})
    )
    with pytest.raises(RuntimeError, match="truncated"):
        asyncio.run(backend.invoke(request()))


def test_quota_error_propagates_without_retry(monkeypatch):
    backend = setup_backend(monkeypatch)
    transport = Mock(side_effect=RuntimeError("HTTP 429"))
    monkeypatch.setattr(gemini, "invoke_images", transport)
    with pytest.raises(RuntimeError, match="429"):
        asyncio.run(backend.invoke(request()))
    assert transport.call_count == 1
