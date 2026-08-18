"""Semantic memory plugins.

Four modes, matching the axis the design-space study kept: what mission history
is available to semantic reasoning.  All four are bounded, and all four report
their token usage, because "compact history beats a sliding window" is only a
meaningful claim if both are paying a stated budget.

None of these hold geometry.  The planner's occupancy map lives in
:class:`~uavlab.contracts.perception.PerceptionState`, and keeping it out of
here is what makes the memory ablations (C4->C5, C8->C9) interpretable.
"""

from __future__ import annotations

from typing import Any

from uavlab.contracts import (
    DecisionEnvelope,
    MemoryItem,
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    Vec3,
    ns_to_s,
)
from uavlab.core.registry import register

TOKENS_PER_ITEM = 24


@register("memory", "no_memory")
class NoMemory:
    """The null hypothesis: every decision is made from the current frame."""

    def __init__(self, **params: Any) -> None:
        self._seq = 0
        self._t_ns = 0

    @property
    def name(self) -> str:
        return "no_memory"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._seq = 0
        self._t_ns = 0

    def update(
        self,
        observation: ObservationPacket,
        perception: PerceptionState,
        decision: DecisionEnvelope | None,
    ) -> None:
        self._seq = observation.seq
        self._t_ns = observation.t_sim_ns

    def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(
            observation_seq=self._seq, t_sim_ns=self._t_ns, policy_name="no_memory"
        )


@register("memory", "short_context")
class ShortContext:
    """A sliding window of the most recent observations.

    The cheap baseline that compact-history designs are supposed to beat.
    """

    def __init__(self, **params: Any) -> None:
        self.window = int(params.get("window", 5))
        self.token_budget = int(params.get("token_budget", self.window * TOKENS_PER_ITEM))
        self._items: list[MemoryItem] = []
        self._seq = 0
        self._t_ns = 0

    @property
    def name(self) -> str:
        return "short_context"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._items = []
        self._seq = 0
        self._t_ns = 0

    def update(
        self,
        observation: ObservationPacket,
        perception: PerceptionState,
        decision: DecisionEnvelope | None,
    ) -> None:
        self._seq = observation.seq
        self._t_ns = observation.t_sim_ns
        best = max(perception.detections, key=lambda d: d.score, default=None)
        self._items.append(
            MemoryItem(
                observation_seq=observation.seq,
                t_sim_ns=observation.t_sim_ns,
                kind="frame",
                summary=(
                    f"at ({observation.position.x:.1f},{observation.position.y:.1f},"
                    f"{observation.position.z:.1f}) "
                    + (f"saw {best.label}@{best.score:.2f}" if best else "no detections")
                ),
                position=best.position if best else observation.position,
                label=best.label if best else None,
                salience=best.score if best else 0.0,
            )
        )
        if len(self._items) > self.window:
            self._items = self._items[-self.window :]

    def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(
            observation_seq=self._seq,
            t_sim_ns=self._t_ns,
            items=tuple(self._items),
            token_budget=self.token_budget,
            tokens_used=len(self._items) * TOKENS_PER_ITEM,
            policy_name="short_context",
        )


@register("memory", "compact_keyframe_memory")
class CompactKeyframeMemory:
    """First frame + selected keyframes + latest frame, within a fixed budget.

    Selection is by salience and novelty rather than recency, which is the whole
    difference from a sliding window: a window forgets the moment the target was
    last seen, a keyframe store keeps it.

    Only one selection heuristic is implemented on purpose.  Tuning twenty
    keyframe selectors is a later experiment; the first question is whether
    compact relevant history beats short context at all.
    """

    def __init__(self, **params: Any) -> None:
        self.capacity = int(params.get("capacity", 6))
        self.min_separation_m = float(params.get("min_separation_m", 3.0))
        self.token_budget = int(params.get("token_budget", self.capacity * TOKENS_PER_ITEM))
        self._first: MemoryItem | None = None
        self._keyframes: list[MemoryItem] = []
        self._latest: MemoryItem | None = None
        self._seq = 0
        self._t_ns = 0
        self._replacements = 0

    @property
    def name(self) -> str:
        return "compact_keyframe_memory"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._first = None
        self._keyframes = []
        self._latest = None
        self._seq = 0
        self._t_ns = 0
        self._replacements = 0

    def update(
        self,
        observation: ObservationPacket,
        perception: PerceptionState,
        decision: DecisionEnvelope | None,
    ) -> None:
        self._seq = observation.seq
        self._t_ns = observation.t_sim_ns
        best = max(perception.detections, key=lambda d: d.score, default=None)
        item = MemoryItem(
            observation_seq=observation.seq,
            t_sim_ns=observation.t_sim_ns,
            kind="keyframe",
            summary=(
                f"t={ns_to_s(observation.t_sim_ns):.1f}s "
                + (f"{best.label}@{best.score:.2f}" if best else "no target evidence")
            ),
            position=best.position if best else observation.position,
            label=best.label if best else None,
            salience=(best.score if best else 0.0),
        )
        if self._first is None:
            self._first = item
        self._latest = item

        if best is None:
            return
        if self._too_close_to_existing(item):
            return
        self._keyframes.append(item)
        if len(self._keyframes) > self.capacity:
            weakest = min(range(len(self._keyframes)), key=lambda i: self._keyframes[i].salience)
            if self._keyframes[weakest].salience < item.salience:
                self._keyframes.pop(weakest)
                self._replacements += 1
            else:
                self._keyframes.pop()

    def _too_close_to_existing(self, item: MemoryItem) -> bool:
        if item.position is None:
            return False
        for existing in self._keyframes:
            if existing.position is None:
                continue
            if existing.position.distance_to(item.position) < self.min_separation_m:
                return True
        return False

    def snapshot(self) -> MemorySnapshot:
        items: list[MemoryItem] = []
        if self._first is not None:
            items.append(self._first)
        items.extend(self._keyframes)
        if self._latest is not None:
            items.append(self._latest)
        best = max((i for i in self._keyframes if i.position), key=lambda i: i.salience, default=None)
        summary = (
            f"best target evidence at ({best.position.x:.1f},{best.position.y:.1f}) "
            f"score={best.salience:.2f}"
            if best and best.position
            else "no persistent target evidence"
        )
        return MemorySnapshot(
            observation_seq=self._seq,
            t_sim_ns=self._t_ns,
            items=tuple(items),
            semantic_summary=summary,
            token_budget=self.token_budget,
            tokens_used=len(items) * TOKENS_PER_ITEM,
            policy_name="compact_keyframe_memory",
            stats={"keyframes": float(len(self._keyframes)), "replacements": float(self._replacements)},
        )

    def best_target(self) -> Vec3 | None:
        best = max((i for i in self._keyframes if i.position), key=lambda i: i.salience, default=None)
        return best.position if best else None


@register("memory", "compact_semantic_state")
class CompactSemanticState:
    """A running mission-state summary rather than a frame history.

    Closest to a persistent mission runtime: it tracks progress facts (best
    target evidence, distance trend, subgoal count) in constant space, which is
    what an event-triggered reasoner needs when it is woken up cold.
    """

    def __init__(self, **params: Any) -> None:
        self.token_budget = int(params.get("token_budget", 96))
        self.stall_epsilon_m = float(params.get("stall_epsilon_m", 0.75))
        self._seq = 0
        self._t_ns = 0
        self._best_label = ""
        self._best_score = 0.0
        self._best_position: Vec3 | None = None
        self._last_position: Vec3 | None = None
        self._distance_travelled = 0.0
        self._decisions = 0
        self._frames = 0

    @property
    def name(self) -> str:
        return "compact_semantic_state"

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._seq = 0
        self._t_ns = 0
        self._best_label = ""
        self._best_score = 0.0
        self._best_position = None
        self._last_position = None
        self._distance_travelled = 0.0
        self._decisions = 0
        self._frames = 0

    def update(
        self,
        observation: ObservationPacket,
        perception: PerceptionState,
        decision: DecisionEnvelope | None,
    ) -> None:
        self._seq = observation.seq
        self._t_ns = observation.t_sim_ns
        self._frames += 1
        if decision is not None:
            self._decisions += 1
        if self._last_position is not None:
            self._distance_travelled += self._last_position.distance_to(observation.position)
        self._last_position = observation.position
        for det in perception.detections:
            if det.score > self._best_score:
                self._best_score = det.score
                self._best_label = det.label
                self._best_position = det.position

    def snapshot(self) -> MemorySnapshot:
        if self._best_position is not None:
            summary = (
                f"target '{self._best_label}' last seen at "
                f"({self._best_position.x:.1f},{self._best_position.y:.1f},"
                f"{self._best_position.z:.1f}) with score {self._best_score:.2f}; "
                f"travelled {self._distance_travelled:.1f} m over {self._frames} frames"
            )
        else:
            summary = (
                f"no target evidence yet; travelled {self._distance_travelled:.1f} m "
                f"over {self._frames} frames"
            )
        items = ()
        if self._best_position is not None:
            items = (
                MemoryItem(
                    observation_seq=self._seq,
                    t_sim_ns=self._t_ns,
                    kind="landmark",
                    summary=f"best {self._best_label}",
                    position=self._best_position,
                    label=self._best_label or None,
                    salience=self._best_score,
                ),
            )
        return MemorySnapshot(
            observation_seq=self._seq,
            t_sim_ns=self._t_ns,
            items=items,
            semantic_summary=summary,
            token_budget=self.token_budget,
            tokens_used=min(self.token_budget, 32 + len(summary) // 4),
            policy_name="compact_semantic_state",
            stats={"distance_travelled_m": self._distance_travelled},
        )

    def best_target(self) -> Vec3 | None:
        return self._best_position
