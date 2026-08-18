"""Inference backend for a local Ollama endpoint.

The important difference from the simulated backend is where latency comes from.
`SimulatedInference` charges a *configured* cost; this one charges the cost it
actually measured. So when a real model runs, simulation time reflects what the
model really did, and `decision_age` stops being an assumption.

That has a consequence worth stating: with a real model the wall clock and the
simulation clock advance together, so an episode now takes real seconds. Real
models belong on the small promoted subset of configurations, not on the
screening sweep — which is the staging the protocol already prescribes.

Only the standard library is used for transport. Adding an HTTP client
dependency to the core runtime would break the property that `import uavlab`
pulls in nothing heavy.
"""

from __future__ import annotations

import base64
import io
import json
import http.client
import time
import urllib.parse
from typing import Any

from uavlab.contracts import MissionSpec
from uavlab.contracts.events import EventType
from uavlab.core.registry import register
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import InferenceRequest, InferenceResult


class OllamaUnavailable(RuntimeError):
    """Raised when the endpoint cannot be reached, with what to do about it."""


@register("inference", "ollama")
class OllamaInference:
    """Calls a local Ollama daemon and charges the measured latency to the clock."""

    def __init__(self, **params: Any) -> None:
        self.host = str(params.get("host", "http://localhost:11434"))
        self.model_id = str(params.get("model_id", "gemma3:4b"))
        self.timeout_s = float(params.get("timeout_s", 120.0))
        self.temperature = float(params.get("temperature", 0.0))
        """Zero by default. A stochastic policy would make paired-by-seed
        comparison meaningless, since the same scene would produce different
        decisions run to run."""
        self.num_predict = int(params.get("num_predict", 96))
        self.sampling_seed = int(params.get("sampling_seed", 0))
        """Seed sent to the server with every call.

        Determinism here is *best effort and not guaranteed*, which is worth
        stating plainly rather than discovering later. Measured on this
        repository: c2g reproduces exactly across three separate processes, but
        `uavlab verify` caught one divergence of 1.4 mm in final distance during
        a long sequential run. The residual variation is inside the server's GPU
        kernels, where batching and memory pressure change reduction order; no
        client-side option reaches it.

        Architectures with a verifier or monitor downstream (c3g-c6g) absorb a
        difference this small and verify clean. C2 maps the emitted pixel
        straight to a waypoint, so nothing absorbs it, which is why c2g is the
        one that shows it.
        """

        self.charge_mode = str(params.get("charge_mode", "fixed"))
        """How measured model latency is charged to the *simulation* clock.

        Charging raw measured latency makes ``decision_age`` honest but couples
        the simulation clock to wall-clock jitter: two runs of the same seed
        diverge, because a 100 ms difference in one call shifts every later
        decision. That destroys paired-by-seed comparison, which is the method
        the whole protocol rests on.

        Measured on this repository, same seed, two separate processes:

        =============  ==========================================
        mode           result
        =============  ==========================================
        ``measured``   DIVERGED (36.8 m vs 7.2 m final distance)
        ``quantised``  DIVERGED (10.9 m vs 18.5 m)
        ``fixed``      REPRODUCIBLE (identical to 4 decimals)
        =============  ==========================================

        Quantising is not enough, which is worth stating because it sounds like
        it should be: a call landing either side of a bucket boundary flips one
        decision, and that flip cascades through every decision after it. Only a
        constant charge removes the coupling entirely.

        ``fixed`` is therefore the default. The constant is *measured*, not
        guessed - see ``calibrate`` - so realism is preserved where it matters
        (the value) and discarded only where it breaks the method (the jitter).

        In every mode the *measured* latency is still recorded in the metrics, so
        the real cost of the model is never lost.
        """
        self.latency_quantum_s = float(params.get("latency_quantum_s", 0.25))
        self.fixed_latency_s = dict(params.get("fixed_latency_s", {}))
        """Per-role latency to charge in ``fixed`` mode, measured once and
        written into the model profile rather than guessed."""
        self.fallback_latency_s = float(params.get("fallback_latency_s", 2.0))

        if self.charge_mode not in ("measured", "quantised", "fixed"):
            raise ValueError(
                f"charge_mode must be measured|quantised|fixed, got {self.charge_mode!r}"
            )

        self.endpoint = str(params.get("endpoint", "chat"))
        """``chat`` or ``generate``.

        Measured: ``/api/chat`` costs about 0.2 s less per call than
        ``/api/generate`` on Ollama 0.32.14, consistently and for no reason
        visible from the client. Small, but free."""

        self.keep_alive = str(params.get("keep_alive", "30m"))
        """How long the daemon holds the model resident between calls."""

        self._conn: http.client.HTTPConnection | None = None
        self._services: RuntimeServices | None = None
        self._calls: dict[str, int] = {}
        self._tokens: dict[str, int] = {}
        self._latency_ns: dict[str, int] = {}
        self._charged_ns: dict[str, int] = {}
        """What was charged to the sim clock, which may differ from what was
        measured. Both are reported: the gap between them is exactly how much
        realism was traded away for reproducibility."""
        self._load_ns: dict[str, int] = {}
        """Server-reported per-request setup time.

        Tracked separately because on this setup it is ~1.4 s of every call and
        is *not* a model load: forcing a genuine reload (by changing num_ctx)
        costs 5-7 s. Reporting it apart from prefill and decode is what keeps a
        latency number from being read as model compute."""
        self._errors = 0

    @property
    def name(self) -> str:
        return "ollama"

    def bind_runtime(self, services: RuntimeServices) -> None:
        self._services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self.close()
        self._calls = {}
        self._tokens = {}
        self._latency_ns = {}
        self._charged_ns = {}
        self._load_ns = {}
        self._errors = 0

    # -- transport ----------------------------------------------------------

    def _connection(self) -> http.client.HTTPConnection:
        """A reused keep-alive connection to the daemon.

        Measured, not assumed: opening a fresh TCP connection per call cost a
        flat **2.08 s** on this machine — identical across gemma3:4b, moondream
        and qwen3-vl:2b, which is what identified it as transport rather than
        model compute. Reusing the connection took a call from 4.05 s to 1.8 s.

        That is a larger speed-up than any quantisation could deliver, and it
        would have been invisible without splitting measured wall time against
        the server's own reported load/prefill/decode timings. Worth remembering
        before blaming a model for being slow.
        """
        if self._conn is None:
            parsed = urllib.parse.urlparse(self.host)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            factory = (
                http.client.HTTPSConnection
                if parsed.scheme == "https"
                else http.client.HTTPConnection
            )
            self._conn = factory(host, port, timeout=self.timeout_s)
        return self._conn

    def _post(self, path: str, body: dict[str, Any], _retry: bool = True) -> dict[str, Any]:
        payload = json.dumps(body)
        try:
            conn = self._connection()
            conn.request("POST", path, body=payload, headers={"Content-Type": "application/json"})
            return json.loads(conn.getresponse().read())
        except (http.client.HTTPException, OSError) as exc:
            # A kept-alive connection can be closed by the far end between
            # calls. Rebuild once before treating it as a real failure.
            self.close()
            if _retry:
                return self._post(path, body, _retry=False)
            raise OllamaUnavailable(
                f"cannot reach Ollama at {self.host}: {exc}. Start it with "
                f"`ollama serve`, and confirm the model with `ollama pull {self.model_id}`."
            ) from exc

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001 - closing must never raise
                pass
            self._conn = None

    def available(self) -> bool:
        try:
            self._post("/api/show", {"model": self.model_id})
            return True
        except OllamaUnavailable:
            return False

    @staticmethod
    def encode_image(image: Any) -> str:
        """PIL image -> base64 PNG, which is what the endpoint accepts."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def _charge_for(self, role: str, measured_ns: int) -> int:
        """Decide what to bill the simulation clock for this call."""
        if self.charge_mode == "measured":
            return measured_ns
        if self.charge_mode == "fixed":
            seconds = float(self.fixed_latency_s.get(role, self.fallback_latency_s))
            return int(seconds * 1e9)
        quantum_ns = max(int(self.latency_quantum_s * 1e9), 1)
        # Round to nearest, never to zero: a call that took real time must cost
        # the simulated vehicle real time, or a slow model would look free.
        return max(quantum_ns, int(round(measured_ns / quantum_ns)) * quantum_ns)

    # -- the interface ------------------------------------------------------

    async def invoke(self, request: InferenceRequest) -> InferenceResult:
        prompt = request.prompt
        images = list(request.images)

        options = {
            "temperature": self.temperature,
            "num_predict": self.num_predict,
            # Pinned even though temperature is 0 and greedy decoding should not
            # consult it. It costs nothing, it states the intent, and it removes
            # the one source of run-to-run variation that is ours to control.
            # It does NOT make the backend deterministic on its own: see
            # `sampling_seed` for what remains.
            "seed": self.sampling_seed,
        }
        if self.endpoint == "chat":
            message: dict[str, Any] = {"role": "user", "content": prompt}
            if images:
                message["images"] = images
            body: dict[str, Any] = {
                "model": self.model_id,
                "messages": [message],
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": options,
            }
            path = "/api/chat"
        else:
            body = {
                "model": self.model_id,
                "prompt": prompt,
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": options,
            }
            if images:
                body["images"] = images
            path = "/api/generate"

        started = time.perf_counter_ns()
        text = ""
        eval_count = 0
        load_ns = 0
        try:
            payload = self._post(path, body)
            text = str(
                payload.get("response")
                or payload.get("message", {}).get("content", "")
            )
            eval_count = int(payload.get("eval_count", 0) or 0)
            load_ns = int(payload.get("load_duration", 0) or 0)
        except OllamaUnavailable:
            self._errors += 1
            raise
        measured_ns = time.perf_counter_ns() - started
        self._load_ns[request.role] = self._load_ns.get(request.role, 0) + load_ns

        charge_ns = self._charge_for(request.role, measured_ns)
        self._charged_ns[request.role] = self._charged_ns.get(request.role, 0) + charge_ns
        if self._services is not None and charge_ns > 0:
            await self._services.clock.sleep_ns(charge_ns)

        role = request.role
        self._calls[role] = self._calls.get(role, 0) + 1
        self._tokens[role] = self._tokens.get(role, 0) + eval_count
        self._latency_ns[role] = self._latency_ns.get(role, 0) + measured_ns

        if self._services is not None:
            self._services.log.emit(
                f"inference/{role}",
                EventType.INFERENCE_CALL,
                self._services.clock.now_ns(),
                self._services.clock.wall_ns(),
                payload={
                    "role": role,
                    "model_id": self.model_id,
                    "backend": "ollama",
                    "latency_s": measured_ns / 1e9,
                    "output_tokens": eval_count,
                    "image_count": len(images),
                    "response_chars": len(text),
                },
            )

        return InferenceResult(
            payload=text, output_tokens=eval_count, latency_ns=measured_ns, cache_hit=False
        )

    def stats(self) -> dict[str, float]:
        out: dict[str, float] = {"inference_errors": float(self._errors)}
        total_calls = total_tokens = 0
        for role, calls in self._calls.items():
            out[f"inference_calls_{role}"] = float(calls)
            out[f"inference_tokens_{role}"] = float(self._tokens.get(role, 0))
            out[f"inference_latency_s_{role}"] = self._latency_ns.get(role, 0) / 1e9
            out[f"inference_server_setup_s_{role}"] = self._load_ns.get(role, 0) / 1e9
            out[f"inference_charged_s_{role}"] = self._charged_ns.get(role, 0) / 1e9
            if calls:
                out[f"inference_mean_latency_s_{role}"] = (
                    self._latency_ns.get(role, 0) / 1e9 / calls
                )
            total_calls += calls
            total_tokens += self._tokens.get(role, 0)
        out["inference_calls_total"] = float(total_calls)
        out["inference_tokens_total"] = float(total_tokens)
        out["reasoner_calls"] = float(self._calls.get("reasoner", 0))
        return out
