import asyncio
import json
from dataclasses import replace
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from uavlab.interfaces import InferenceRequest
from uavlab.plugins.inference import free_vlm_router as router


@pytest.fixture
def backend(tmp_path, monkeypatch):
    settings = {}
    for provider in router.DEFAULT_MODELS:
        key = tmp_path / f"{provider}.txt"
        key.write_text("test-secret")
        settings[f"{provider.upper()}_API_KEY_FILE"] = str(key)
        settings[f"{provider.upper()}_FREE_TIER_CONFIRMED"] = "true"
    settings["OPENROUTER_MODEL"] = "test/vision:free"
    monkeypatch.setattr(router.gemini_client, "configuration", lambda _: settings)
    return router.FreeVLMRouter(quota_dir=str(tmp_path))


def request():
    return InferenceRequest(
        model_id="free-vlm-router",
        role="policy",
        prompt_hash="test",
        prompt="find target",
        images=("base64-image",),
        response_schema={"type": "object"},
    )


def test_503_moves_once_then_sticks_to_successful_provider(backend, monkeypatch):
    calls = []

    def invoke(provider, req):
        calls.append(provider)
        if provider == "gemini":
            raise router.RouteFailure(503)
        return '{"u":93}', 5, "resolved-vision"

    monkeypatch.setattr(backend, "_call", invoke)
    asyncio.run(backend.invoke(request()))
    asyncio.run(backend.invoke(request()))
    assert calls == ["gemini", "groq", "groq"]
    assert backend._rows[-1]["model_id"] == "qwen/qwen3.8-27b"
    assert backend._rows[-1]["resolved_model"] == "resolved-vision"


def test_429_persists_and_reset_cannot_reenable(backend, monkeypatch):
    def invoke(provider, req):
        if provider == "gemini":
            raise router.RouteFailure(429)
        return "{}", 1, "test"

    monkeypatch.setattr(backend, "_call", invoke)
    asyncio.run(backend.invoke(request()))
    assert backend.stop_file("gemini").exists()
    backend.reset(None, 1061)
    backend._disabled.clear()  # Simulate fresh in-memory state; disk marker still blocks.
    assert backend.readiness()["gemini"]["status"] == "circuit_open"


def test_exhaustion_makes_at_most_one_attempt_per_provider(backend, monkeypatch):
    transport = Mock(side_effect=router.RouteFailure(503))
    monkeypatch.setattr(backend, "_call", transport)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="No confirmed"):
            asyncio.run(backend.invoke(request()))
    assert transport.call_count == 4


def test_unconfirmed_missing_and_paid_routes_are_never_called(backend, monkeypatch):
    backend.settings["GEMINI_FREE_TIER_CONFIRMED"] = "false"
    backend.settings["GROQ_API_KEY_FILE"] = "missing-key-file"
    backend.settings["MISTRAL_FREE_TIER_CONFIRMED"] = "false"
    backend.settings["OPENROUTER_MODEL"] = "paid/vision"
    transport = Mock()
    monkeypatch.setattr(backend, "_call", transport)
    with pytest.raises(RuntimeError, match="No confirmed"):
        asyncio.run(backend.invoke(request()))
    transport.assert_not_called()


def test_mismatched_alias_never_calls_provider(backend, monkeypatch):
    transport = Mock()
    monkeypatch.setattr(backend, "_call", transport)
    with pytest.raises(ValueError, match="mismatch"):
        asyncio.run(backend.invoke(replace(request(), model_id="gemini-3.5-flash")))
    transport.assert_not_called()


def test_bad_request_does_not_hide_configuration_error(backend, monkeypatch):
    transport = Mock(side_effect=router.RouteFailure(400))
    monkeypatch.setattr(backend, "_call", transport)
    with pytest.raises(router.RouteFailure):
        asyncio.run(backend.invoke(request()))
    assert transport.call_count == 1


@pytest.mark.parametrize("provider", ["groq", "mistral", "openrouter"])
def test_chat_transport_preserves_images_and_auth_in_header(backend, monkeypatch, provider):
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(
        {
            "model": "resolved",
            "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
            "usage": {"completion_tokens": 1},
        }
    )
    transport = Mock(return_value=response)
    monkeypatch.setattr(router, "urlopen", transport)
    model = backend.readiness()[provider]["model"]
    result = router.chat_response(
        provider, model, backend.settings[f"{provider.upper()}_API_KEY_FILE"], request(), 256
    )
    assert result == ("{}", 1, "resolved")
    wire = transport.call_args.args[0]
    body = json.loads(wire.data)
    assert wire.full_url == router.ENDPOINTS[provider]
    assert "test-secret" not in wire.full_url
    assert wire.get_header("Authorization") == "Bearer test-secret"
    image = body["messages"][0]["content"][1]["image_url"]
    assert (
        image if provider == "mistral" else image["url"]
    ) == "data:image/png;base64,base64-image"
    if provider == "openrouter":
        assert body["provider"]["max_price"] == {"prompt": 0, "completion": 0}
        assert body["provider"]["allow_fallbacks"] is False


def test_wire_429_is_typed_and_does_not_leak_secret(backend, monkeypatch):
    monkeypatch.setattr(
        router, "urlopen", Mock(side_effect=HTTPError("url", 429, "sensitive body", None, None))
    )
    with pytest.raises(router.RouteFailure) as error:
        router.chat_response("groq", "test", backend.settings["GROQ_API_KEY_FILE"], request(), 256)
    assert error.value.status == 429
    assert "sensitive" not in str(error.value)


def test_router_profile_preserves_model_alias():
    from pathlib import Path

    from uavlab.core.compose import load_architecture

    arch = load_architecture("c5_free_vlm_router_dev", Path("configs"))
    assert arch.inference.name == "free_vlm_router"
    assert arch.policy.params["model_id"] == arch.monitor.params["model_id"] == "free-vlm-router"
