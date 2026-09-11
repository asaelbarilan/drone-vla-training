"""Opt-in diagnostic sidecars. No secrets, model calls or policy-side truth access.

Requests are captured at the plugin/backend boundary; transport headers and
provider credentials are deliberately outside this interface. Disk work does not
advance simulation time but adds wall overhead, so capture is off by default.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from uavlab.core.services import bind


class DebugCapture:
    def __init__(self, root: Path):
        self.root = root
        self.calls = root / "debug" / "calls"
        if self.calls.exists() and any(self.calls.iterdir()):
            raise ValueError("Debug capture already exists; use a fresh output directory")
        self.calls.mkdir(parents=True, exist_ok=True)
        self.counter = 0
        self.sources: dict[str, str] = {}

    def source(self, frame) -> dict | None:
        if frame is None:
            return None
        path = Path(frame.f_code.co_filename).resolve()
        repo = Path(__file__).resolve().parents[3]
        if path.suffix != ".py" or not path.is_relative_to(repo):
            return None
        key = str(path)
        if key not in self.sources:
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            dest = self.root / "debug" / "sources" / (digest + ".py")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            self.sources[key] = dest.relative_to(self.root).as_posix()
        return {
            "path": key,
            "line": frame.f_lineno,
            "function": frame.f_code.co_name,
            "snapshot": self.sources[key],
        }

    def write(self, record: dict) -> None:
        path = self.calls / f"{record['id']}.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        temp.replace(path)

    def begin(self, request, clock, source) -> dict:
        self.counter += 1
        call_id = f"call-{self.counter:06d}"
        # Only typed inference fields, never backend params or authentication.
        record = asdict(request)
        images = record.pop("images")
        record.update(
            id=call_id,
            status="pending",
            source=source,
            started_t_sim_ns=clock.now_ns(),
            image_files=[],
        )
        for i, image in enumerate(images):
            raw = base64.b64decode(image, validate=True)
            path = self.root / "debug" / "images" / f"{call_id}-{i}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            record["image_files"].append(path.relative_to(self.root).as_posix())
        self.write(record)
        return record


class RecordingInference:
    """Transparent inference decorator; preserves results and clock charges."""

    def __init__(self, backend, capture: DebugCapture):
        self.backend = backend
        self.capture = capture
        self.services = None

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def bind_runtime(self, services):
        self.services = services
        bind(self.backend, services)

    async def invoke(self, request):
        clock = self.services.clock
        record = self.capture.begin(request, clock, self.capture.source(sys._getframe(1)))
        try:
            result = await self.backend.invoke(request)
        except BaseException as exc:
            record.update(
                status="cancelled" if isinstance(exc, asyncio.CancelledError) else "error",
                error_type=type(exc).__name__,
                completed_t_sim_ns=clock.now_ns(),
            )
            self.capture.write(record)
            raise
        record.update(
            status="complete",
            completed_t_sim_ns=clock.now_ns(),
            response=result.payload,
            latency_ns=result.latency_ns,
            output_tokens=result.output_tokens,
            cache_hit=result.cache_hit,
        )
        self.capture.write(record)
        return result
