"""Gemini comparison backend; no retry or paid fallback."""

import time
from pathlib import Path

from uavlab.contracts import EventType
from uavlab.core.registry import register
from uavlab.interfaces import InferenceResult
from uavlab.plugins.inference.gemini_client import configuration, invoke_images


@register("inference", "gemini")
class GeminiInference:
    def __init__(self, **params):
        self.settings = configuration(Path(params.get("env_file", ".env")))
        self.model_id = str(params.get("model_id", self.settings.get("GEMINI_MODEL")))
        self.settings["GEMINI_MODEL"] = self.model_id
        self.stop_file = Path(params.get("quota_stop_file", ".local/gemini_quota_stop"))
        self.max_tokens = int(params.get("max_output_tokens", 256))
        self.fixed_latency_s = dict(params.get("fixed_latency_s", {}))
        self._services = None
        self._rows = []

    @property
    def name(self):
        return "gemini"

    def bind_runtime(self, services):
        self._services = services

    def reset(self, mission, seed):
        self._rows = []

    async def invoke(self, request):
        if request.model_id != self.model_id:
            raise ValueError("Gemini request/backend model mismatch")
        start = time.perf_counter_ns()
        response = invoke_images(
            self.settings,
            request.prompt,
            [{"mimeType": "image/png", "data": image} for image in request.images],
            self.stop_file,
            schema=request.response_schema,
            max_tokens=self.max_tokens,
        )
        elapsed = time.perf_counter_ns() - start
        candidates = response.get("candidates", [])
        if not candidates or candidates[0].get("finishReason") != "STOP":
            raise RuntimeError("Gemini response was blocked, incomplete or truncated; no fallback")
        text = "".join(
            p.get("text", "")
            for p in candidates[0].get("content", {}).get("parts", [])
            if not p.get("thought")
        )
        if not text:
            raise RuntimeError("Gemini returned no final text")
        usage = response.get("usageMetadata", {})
        tokens = int(usage.get("candidatesTokenCount", 0))
        charge = (
            int(float(self.fixed_latency_s[request.role]) * 1e9)
            if request.role in self.fixed_latency_s
            else elapsed
        )
        row = {
            "role": request.role,
            "model_id": self.model_id,
            "resolved_model": response.get("modelVersion"),
            "backend": self.name,
            "latency_s": elapsed / 1e9,
            "charged_s": charge / 1e9,
            "output_tokens": tokens,
            "prompt_tokens": usage.get("promptTokenCount", 0),
            "image_count": len(request.images),
            "response_chars": len(text),
        }
        self._rows.append(row)
        if self._services is not None:
            await self._services.clock.sleep_ns(charge)
            self._services.log.emit(
                f"inference/{request.role}",
                EventType.INFERENCE_CALL,
                self._services.clock.now_ns(),
                self._services.clock.wall_ns(),
                payload=row,
            )
        return InferenceResult(
            payload=text, output_tokens=tokens, latency_ns=elapsed, cache_hit=False
        )

    def stats(self):
        out = {"inference_calls_total": float(len(self._rows))}
        for role in {r["role"] for r in self._rows}:
            rows = [r for r in self._rows if r["role"] == role]
            out[f"inference_calls_{role}"] = float(len(rows))
            out[f"inference_mean_latency_s_{role}"] = sum(r["latency_s"] for r in rows) / len(rows)
            out[f"inference_charged_s_{role}"] = sum(r["charged_s"] for r in rows)
        return out
