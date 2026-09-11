"""Transport invariants for local Ollama model profiles."""

from __future__ import annotations

import asyncio

import pytest

from uavlab.interfaces import InferenceRequest
from uavlab.plugins.inference.ollama import OllamaInference, OllamaRequestError


def request() -> InferenceRequest:
    return InferenceRequest(
        model_id="gemma3:4b",
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


def test_mismatched_model_is_rejected_before_network(monkeypatch) -> None:
    backend = OllamaInference(model_id="qwen3-vl:4b")

    def unexpected_call(*args, **kwargs):
        pytest.fail("mismatched model request reached the server")

    monkeypatch.setattr(backend, "_post", unexpected_call)
    with pytest.raises(ValueError, match="requests model"):
        asyncio.run(backend.invoke(request()))


@pytest.mark.parametrize(
    "name",
    ["c5_gemma4_e2b_baseline_dev", "c5_gemma4_e2b_target_stop_dev", "c5_onfly_active_dev"],
)
def test_gemma_profile_uses_real_gemma_backend_and_content(name, monkeypatch):
    from pathlib import Path

    from uavlab.core.compose import load_architecture

    arch = load_architecture(name, Path("configs"))
    backend = OllamaInference(**arch.inference.params)
    posted = []

    def capture(_path, body):
        posted.append(body)
        return {"message": {"content": "{}"}, "eval_count": 2}

    monkeypatch.setattr(backend, "_post", capture)
    for role, component in [("policy", arch.policy), ("monitor", arch.monitor)]:
        result = asyncio.run(
            backend.invoke(
                InferenceRequest(
                    model_id=component.params["model_id"],
                    role=role,
                    prompt_hash="identity-test",
                    input_tokens=1,
                    prompt="test",
                )
            )
        )
        assert result.payload == "{}"
    assert all(body["model"] == "gemma4:e2b" for body in posted)
    assert all(body["think"] is False for body in posted)


def test_historical_mislabelled_gemma_profile_fails_before_http(monkeypatch):
    from pathlib import Path

    from uavlab.core.compose import load_architecture

    arch = load_architecture("c5_onfly_gemma4b_direction_dev", Path("configs"))
    backend = OllamaInference(**arch.inference.params)

    def unexpected(*args, **kwargs):
        pytest.fail("mislabelled historical profile reached HTTP")

    monkeypatch.setattr(backend, "_post", unexpected)
    with pytest.raises(ValueError, match="requests model"):
        asyncio.run(
            backend.invoke(
                InferenceRequest(
                    model_id=arch.policy.params["model_id"],
                    role="policy",
                    prompt_hash="historical-identity",
                    input_tokens=1,
                    prompt="test",
                )
            )
        )
