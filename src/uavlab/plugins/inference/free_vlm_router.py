"""Opt-in free-only cloud vision failover, with explicit provider provenance."""

import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from uavlab.contracts import EventType
from uavlab.core.registry import register
from uavlab.interfaces import InferenceResult
from uavlab.plugins.inference import gemini_client

ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}
DEFAULT_MODELS = {
    "gemini": "gemini-3.5-flash",
    "groq": "qwen/qwen3.8-27b",
    "mistral": "mistral-small-2506",
    "openrouter": "",
}


class RouteFailure(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Provider transport failed: {status}")


def chat_response(provider, model, key_file, request, max_tokens):
    key = gemini_client.key_from_file({"GEMINI_API_KEY_FILE": key_file})
    content = [{"type": "text", "text": request.prompt}]
    for image in request.images:
        url = f"data:image/png;base64,{image}"
        content.append(
            {"type": "image_url", "image_url": url if provider == "mistral" else {"url": url}}
        )
    body = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if request.response_schema is not None:
        # JSON mode is common across these providers. Preserve the exact task schema
        # in the prompt; downstream policy/monitor validation remains authoritative.
        content[0]["text"] += "\nReturn only JSON matching this schema: " + json.dumps(
            request.response_schema
        )
        body["response_format"] = {"type": "json_object"}
    if provider == "openrouter":
        if not model.endswith(":free"):
            raise ValueError("OpenRouter requires a pinned :free model")
        body["provider"] = {"allow_fallbacks": False, "max_price": {"prompt": 0, "completion": 0}}
    wire = Request(
        ENDPOINTS[provider],
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with urlopen(wire, timeout=60) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RouteFailure(exc.code) from None
    except (URLError, TimeoutError):
        raise RouteFailure("network") from None
    choices = result.get("choices", [])
    if not choices or choices[0].get("finish_reason") != "stop":
        raise ValueError("Provider returned incomplete or blocked output")
    text = choices[0].get("message", {}).get("content")
    if not isinstance(text, str) or not text:
        raise ValueError("Provider returned no text")
    usage = result.get("usage", {})
    return text, usage.get("completion_tokens", 0), result.get("model", model)


@register("inference", "free_vlm_router")
class FreeVLMRouter:
    model_id = "free-vlm-router"
    name = "free_vlm_router"

    def __init__(self, **params):
        self.settings = gemini_client.configuration(Path(params.get("env_file", ".env")))
        for provider in DEFAULT_MODELS:
            for suffix in ("API_KEY_FILE", "MODEL", "FREE_TIER_CONFIRMED"):
                key = f"{provider.upper()}_{suffix}"
                if key in os.environ:
                    self.settings[key] = os.environ[key]
        self.order = params.get("provider_order", list(DEFAULT_MODELS))
        if (
            not self.order
            or len(set(self.order)) != len(self.order)
            or any(p not in DEFAULT_MODELS for p in self.order)
        ):
            raise ValueError("Use unique supported provider names")
        self.stop_dir = Path(params.get("quota_dir", ".local"))
        self.max_tokens = int(params.get("max_output_tokens", 256))
        self.fixed_latency_s = dict(params.get("fixed_latency_s", {}))
        self._services = None
        self._disabled = set()
        self._rows = []
        self._current = None

    def bind_runtime(self, services):
        self._services = services

    def reset(self, mission, seed):
        self._rows = []
        # Do not reset provider circuit breakers or current route across episodes.

    def stop_file(self, provider):
        return self.stop_dir / f"{provider}_quota_stop"

    def readiness(self):
        result = {}
        for provider in self.order:
            prefix = provider.upper()
            key = self.settings.get(f"{prefix}_API_KEY_FILE", "")
            model = self.settings.get(f"{prefix}_MODEL", DEFAULT_MODELS[provider])
            reason = "ready"
            if provider in self._disabled or self.stop_file(provider).exists():
                reason = "circuit_open"
            elif self.settings.get(f"{prefix}_FREE_TIER_CONFIRMED", "false").lower() != "true":
                reason = "free_access_unconfirmed"
            elif not key or not Path(key).is_file():
                reason = "key_file_missing"
            elif not model or (provider == "openrouter" and not model.endswith(":free")):
                reason = "free_model_not_selected"
            result[provider] = {"status": reason, "model": model}
        return result

    def _call(self, provider, request):
        model = self.settings.get(f"{provider.upper()}_MODEL", DEFAULT_MODELS[provider])
        if provider != "gemini":
            return chat_response(
                provider,
                model,
                self.settings[f"{provider.upper()}_API_KEY_FILE"],
                request,
                self.max_tokens,
            )
        try:
            result = gemini_client.invoke_images(
                self.settings,
                request.prompt,
                [{"mimeType": "image/png", "data": image} for image in request.images],
                self.stop_file(provider),
                schema=request.response_schema,
                max_tokens=self.max_tokens,
            )
        except gemini_client.ProviderHTTPError as exc:
            raise RouteFailure(exc.status) from None
        except (RuntimeError, TimeoutError):
            raise RouteFailure("network") from None
        candidates = result.get("candidates", [])
        if not candidates or candidates[0].get("finishReason") != "STOP":
            raise ValueError("Gemini returned incomplete or blocked output")
        text = "".join(
            p.get("text", "")
            for p in candidates[0].get("content", {}).get("parts", [])
            if not p.get("thought")
        )
        if not text:
            raise ValueError("Gemini returned no text")
        return (
            text,
            result.get("usageMetadata", {}).get("candidatesTokenCount", 0),
            result.get("modelVersion", model),
        )

    def _log(self, row, event):
        self._rows.append(row)
        if self._services:
            self._services.log.emit(
                "inference/router",
                event,
                self._services.clock.now_ns(),
                self._services.clock.wall_ns(),
                payload=row,
            )

    async def invoke(self, request):
        if request.model_id != self.model_id:
            raise ValueError("Router request/backend model mismatch")
        order = list(self.order)
        if self._current in order:
            order.remove(self._current)
            order.insert(0, self._current)
        overall = time.perf_counter_ns()
        for provider in order:
            state = self.readiness()[provider]
            if state["status"] != "ready":
                continue
            started = time.perf_counter_ns()
            try:
                text, tokens, resolved = self._call(provider, request)
            except RouteFailure as exc:
                self._disabled.add(provider)
                if exc.status == 429:
                    marker = self.stop_file(provider)
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text(
                        "Quota exhausted; explicit authorization required to reset.\n"
                    )
                self._log(
                    {
                        "provider": provider,
                        "model_id": state["model"],
                        "role": request.role,
                        "status": exc.status,
                        "latency_s": (time.perf_counter_ns() - started) / 1e9,
                        "outcome": "failed",
                    },
                    EventType.WARNING,
                )
                if (
                    exc.status == "network"
                    or exc.status == 429
                    or (isinstance(exc.status, int) and 500 <= exc.status <= 599)
                ):
                    continue
                raise
            if request.response_schema is not None:
                json.loads(text)  # Never treat non-JSON as a successful navigation response.
            elapsed = time.perf_counter_ns() - overall
            charged = int(self.fixed_latency_s.get(request.role, elapsed / 1e9) * 1e9)
            if self._services:
                await self._services.clock.sleep_ns(charged)
            self._current = provider
            self._log(
                {
                    "provider": provider,
                    "backend": self.name,
                    "model_id": state["model"],
                    "resolved_model": resolved,
                    "role": request.role,
                    "latency_s": elapsed / 1e9,
                    "charged_s": charged / 1e9,
                    "output_tokens": tokens,
                    "image_count": len(request.images),
                    "outcome": "success",
                },
                EventType.INFERENCE_CALL,
            )
            return InferenceResult(
                payload=text, output_tokens=tokens, latency_ns=elapsed, cache_hit=False
            )
        raise RuntimeError("No confirmed free vision provider remains available")

    def stats(self):
        return {
            "inference_calls_total": float(sum(r["outcome"] == "success" for r in self._rows)),
            "inference_provider_failures": float(sum(r["outcome"] == "failed" for r in self._rows)),
        }
