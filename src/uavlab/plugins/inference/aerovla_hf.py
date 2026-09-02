"""Lazy official AeroVLA OpenVLA-7B + LoRA inference backend.

The heavy runtime is optional. Merely importing the testbed never imports torch
or transformers; selecting this backend checks every resource and fails with a
specific installation/resource message instead of substituting a mock policy.
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import Any

from uavlab.contracts import MissionSpec
from uavlab.core.registry import register
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import InferenceRequest, InferenceResult


class AeroVLAResourceError(RuntimeError):
    """Official weights or their inference runtime are unavailable."""


@register("inference", "aerovla_hf")
class AeroVLAHFInference:
    """Official release wrapper behind the shared inference interface."""

    def __init__(self, **params: Any) -> None:
        self.base_model_path = Path(params.get("base_model_path", "models/aerovla/openvla-7b"))
        self.adapter_path = Path(params.get("adapter_path", "models/aerovla/aero_vla"))
        self.load_in_4bit = bool(params.get("load_in_4bit", False))
        self.fixed_latency_s = float(params.get("fixed_latency_s", 0.38))
        self.max_new_tokens = int(params.get("max_new_tokens", 20))
        self._services: RuntimeServices | None = None
        self._model = None
        self._tokenizer = None
        self._image_processor = None
        self._device = None
        self._calls = 0
        self._latency_ns = 0

    @property
    def name(self) -> str:
        return "aerovla_hf"

    def bind_runtime(self, services: RuntimeServices) -> None:
        self._services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._calls = 0
        self._latency_ns = 0

    def _check_resources(self) -> None:
        if not self.base_model_path.is_dir():
            raise AeroVLAResourceError(
                f"official OpenVLA base is missing at {self.base_model_path}. Download "
                "openvla/openvla-7b (15.1 GB); no scripted fallback is permitted."
            )
        if not (self.adapter_path / "adapter_config.json").is_file() or not (
            self.adapter_path / "adapter_model.safetensors"
        ).is_file():
            raise AeroVLAResourceError(
                f"official AeroVLA LoRA is missing at {self.adapter_path}. Download "
                "XuPeng23/AerialVLA/aero_vla; no scripted fallback is permitted."
            )

    def available(self) -> bool:
        try:
            self._check_resources()
        except AeroVLAResourceError:
            return False
        return True

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        self._check_resources()
        try:
            import torch
            from peft import PeftModel
            from transformers import (
                AutoImageProcessor,
                AutoModelForVision2Seq,
                AutoTokenizer,
                BitsAndBytesConfig,
            )
        except ImportError as exc:
            raise AeroVLAResourceError(
                "official AeroVLA inference requires torch, transformers, peft and, for "
                "4-bit mode, bitsandbytes. Install the optional native runtime; the "
                "testbed will not replace it with mock_vla."
            ) from exc

        base = str(self.base_model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
        self._image_processor = AutoImageProcessor.from_pretrained(base, trust_remote_code=True)
        kwargs: dict[str, Any] = {
            "trust_remote_code": True,
            "low_cpu_mem_usage": True,
            "device_map": "auto",
        }
        if self.load_in_4bit:
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )
        else:
            kwargs["torch_dtype"] = torch.bfloat16
        model = AutoModelForVision2Seq.from_pretrained(base, **kwargs)
        model.resize_token_embeddings(len(self._tokenizer))
        model = PeftModel.from_pretrained(model, str(self.adapter_path))
        model.eval()
        self._model = model
        self._device = next(model.parameters()).device

    async def invoke(self, request: InferenceRequest) -> InferenceResult:
        if len(request.images) != 1:
            raise AeroVLAResourceError(
                "official AeroVLA expects one precomposed dual-view image, "
                f"got {len(request.images)}"
            )
        self._ensure_loaded()
        from PIL import Image

        image = Image.open(io.BytesIO(base64.b64decode(request.images[0]))).convert("RGB")
        pixel_values = self._image_processor(images=image, return_tensors="pt")[
            "pixel_values"
        ].to(self._device)
        if hasattr(self._model, "dtype"):
            pixel_values = pixel_values.to(self._model.dtype)
        inputs = self._tokenizer(request.prompt, return_tensors="pt")
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        inputs["pixel_values"] = pixel_values

        started = time.perf_counter_ns()
        generated = self._model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
            eos_token_id=[self._tokenizer.eos_token_id],
        )
        measured_ns = time.perf_counter_ns() - started
        text = self._tokenizer.decode(generated[0], skip_special_tokens=False)
        self._calls += 1
        self._latency_ns += measured_ns
        if self._services is not None:
            await self._services.clock.sleep_ns(int(self.fixed_latency_s * 1e9))
        return InferenceResult(
            payload=text,
            output_tokens=int(generated.shape[-1]),
            latency_ns=measured_ns,
            cache_hit=False,
        )

    def stats(self) -> dict[str, float]:
        return {
            "inference_calls_policy": float(self._calls),
            "inference_calls_total": float(self._calls),
            "inference_latency_s_policy": self._latency_ns / 1e9,
            "inference_mean_latency_s_policy": (
                self._latency_ns / 1e9 / self._calls if self._calls else 0.0
            ),
            "inference_charged_s_policy": self._calls * self.fixed_latency_s,
            "inference_errors": 0.0,
            "reasoner_calls": 0.0,
        }
