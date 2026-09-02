"""Unified event log.

Every module emits EpisodeEvent and nothing else.  One log schema for all
architectures is what makes cross-architecture analysis a query rather than a
per-paper parsing exercise.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from uavlab.contracts.common import StrictModel


class EventType(str, Enum):
    EPISODE_START = "episode_start"
    EPISODE_END = "episode_end"
    OBSERVATION = "observation"
    PERCEPTION = "perception"
    MEMORY_UPDATE = "memory_update"
    DECISION_PROPOSED = "decision_proposed"
    DECISION_REJECTED_STALE = "decision_rejected_stale"
    DECISION_EXECUTED = "decision_executed"
    VERIFIER = "verifier"
    PLAN = "plan"
    SAFETY = "safety"
    CONTROL = "control"
    MONITOR = "monitor"
    ADMISSION = "admission"
    RECOVERY_TRIGGER = "recovery_trigger"
    RECOVERY_DECISION = "recovery_decision"
    INFERENCE_CALL = "inference_call"
    FAILURE_INJECTED = "failure_injected"
    WARNING = "warning"


class EpisodeEvent(StrictModel):
    """One immutable log record.

    Both clocks are mandatory.  Under a fake clock they diverge, and every
    timing conclusion in the study depends on not confusing them.
    """

    episode_id: str
    seq: int
    component: str
    event_type: EventType
    t_sim_ns: int
    t_wall_ns: int
    trace_id: str | None = None
    """Links an observation to the decision and control command it produced."""
    payload: dict[str, object] = Field(default_factory=dict)

    def flat_row(self) -> dict[str, object]:
        """Flatten for columnar storage, prefixing payload keys with ``p_``."""
        row: dict[str, object] = {
            "episode_id": self.episode_id,
            "seq": self.seq,
            "component": self.component,
            "event_type": self.event_type.value,
            "t_sim_ns": self.t_sim_ns,
            "t_wall_ns": self.t_wall_ns,
            "trace_id": self.trace_id,
        }
        for key, value in self.payload.items():
            scalar = isinstance(value, (int, float, str, bool, type(None)))
            row[f"p_{key}"] = value if scalar else str(value)
        return row
