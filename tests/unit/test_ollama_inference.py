"""Transport invariants for local Ollama model profiles."""

from __future__ import annotations

import asyncio

import pytest

from uavlab.interfaces import InferenceRequest
from uavlab.plugins.inference.ollama import OllamaInference, OllamaRequestError


def request() -> InferenceRequest:
    return InferenceRequest(
        model_id="model",
        role="policy",
        prompt_hash="test",
        input_tokens=1,
        prompt="test",
    )


def payload() -> dict:
    return {
        "message": {"content": "", "thinking": '{"u":500}'},
        "eval_count": 1,
        "load_duration": 0,
    }


def test_thinking_channel_must_be_selected_explicitly(monkeypatch) -> None:
    backend = OllamaInference(response_channel="thinking", fixed_latency_s={"policy": 0})
    monkeypatch.setattr(backend, "_post", lambda *_args, **_kwargs: payload())
    result = asyncio.run(backend.invoke(request()))
    assert result.payload == '{"u":500}'


def test_default_channel_does_not_execute_hidden_thinking(monkeypatch) -> None:
    backend = OllamaInference(fixed_latency_s={"policy": 0})
    monkeypatch.setattr(backend, "_post", lambda *_args, **_kwargs: payload())
    result = asyncio.run(backend.invoke(request()))
    assert result.payload == ""


def test_invalid_response_channel_fails_configuration() -> None:
    with pytest.raises(ValueError, match="response_channel"):
        OllamaInference(response_channel="automatic")


def test_num_ctx_is_sent_when_configured(monkeypatch) -> None:
    backend = OllamaInference(num_ctx=8192, fixed_latency_s={"policy": 0})
    posted = {}

    def capture(_path, body):
        posted.update(body)
        return payload()

    monkeypatch.setattr(backend, "_post", capture)
    asyncio.run(backend.invoke(request()))
    assert posted["options"]["num_ctx"] == 8192


def test_server_rejection_fails_loudly(monkeypatch) -> None:
    backend = OllamaInference(fixed_latency_s={"policy": 0})
    monkeypatch.setattr(
        backend,
        "_post",
        lambda *_args, **_kwargs: {"error": "request exceeds context size"},
    )
    with pytest.raises(OllamaRequestError, match="exceeds context size"):
        asyncio.run(backend.invoke(request()))
    assert backend.stats()["inference_errors"] == 1.0
