"""The unified event log.

Every component emits :class:`EpisodeEvent` and nothing else, so cross-
architecture analysis is a query over one table rather than a per-architecture
parsing exercise.  Two sinks are written: JSONL for human reading and diffing,
Parquet for analysis.  Parquet is optional — the run must not fail because an
analysis dependency is missing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from uavlab.contracts.events import EpisodeEvent, EventType


class EventLog:
    """Buffers events, assigns sequence numbers, and persists them."""

    def __init__(
        self,
        episode_id: str,
        out_dir: Path | None = None,
        keep_in_memory: bool = True,
        *,
        debug_capture: bool = False,
    ):
        self.episode_id = episode_id
        self.out_dir = Path(out_dir) if out_dir else None
        self.keep_in_memory = keep_in_memory
        self.events: list[EpisodeEvent] = []
        self.debug_capture = None
        if debug_capture:
            if self.out_dir is None:
                raise ValueError("debug capture requires an output directory")
            from uavlab.core.debug_capture import DebugCapture

            self.debug_capture = DebugCapture(self.out_dir)
        self._seq = 0
        self._jsonl = None
        if self.out_dir is not None:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            self._jsonl = (self.out_dir / "events.jsonl").open("w", encoding="utf-8")

    @property
    def name(self) -> str:
        return "event_log"

    def emit(
        self,
        component: str,
        event_type: EventType,
        t_sim_ns: int,
        t_wall_ns: int,
        payload: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> EpisodeEvent:
        if self.debug_capture is not None:
            caller = sys._getframe(1)
            if caller.f_code.co_name == "_emit":
                caller = caller.f_back
            payload = {**(payload or {}), "_debug_source": self.debug_capture.source(caller)}
        event = EpisodeEvent(
            episode_id=self.episode_id,
            seq=self._seq,
            component=component,
            event_type=event_type,
            t_sim_ns=t_sim_ns,
            t_wall_ns=t_wall_ns,
            trace_id=trace_id,
            payload=payload or {},
        )
        self._seq += 1
        if self.keep_in_memory:
            self.events.append(event)
        if self._jsonl is not None:
            self._jsonl.write(json.dumps(event.model_dump(mode="json"), default=str) + "\n")
        return event

    # -- queries used by the metrics layer ---------------------------------

    def of_type(self, *types: EventType) -> list[EpisodeEvent]:
        wanted = set(types)
        return [e for e in self.events if e.event_type in wanted]

    def count(self, event_type: EventType) -> int:
        return sum(1 for e in self.events if e.event_type is event_type)

    def values(self, event_type: EventType, key: str) -> list[float]:
        """Collect one numeric payload field across events of a type."""
        out: list[float] = []
        for e in self.events:
            if e.event_type is event_type:
                v = e.payload.get(key)
                if isinstance(v, int | float) and not isinstance(v, bool):
                    out.append(float(v))
        return out

    # -- persistence --------------------------------------------------------

    def to_rows(self) -> list[dict[str, Any]]:
        return [e.flat_row() for e in self.events]

    def write_parquet(self, path: Path | None = None) -> Path | None:
        """Write the columnar table. Returns ``None`` when pyarrow is absent."""
        target = path or (self.out_dir / "events.parquet" if self.out_dir else None)
        if target is None or not self.events:
            return None
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            return None
        rows = self.to_rows()
        columns: dict[str, list[Any]] = {}
        for row in rows:
            for key in row:
                columns.setdefault(key, [])
        for row in rows:
            for key, bucket in columns.items():
                bucket.append(row.get(key))
        table = pa.table({k: pa.array(v) for k, v in columns.items()})
        pq.write_table(table, target)
        return target

    def close(self) -> None:
        if self._jsonl is not None:
            self._jsonl.close()
            self._jsonl = None

    def __len__(self) -> int:
        return len(self.events)

    def __enter__(self) -> EventLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.write_parquet()
        self.close()
