"""Semantic mission memory.

Strictly separate from geometric planner state.  A memory plugin answers "am I
still accomplishing the mission?"; the planner's occupancy map answers "will I
hit that wall?".  The two must never be merged, or the memory ablations
(C4 -> C5, C8 -> C9) stop measuring what they claim to measure.
"""

from __future__ import annotations

from pydantic import Field

from uavlab.contracts.common import StrictModel, Vec3


class MemoryItem(StrictModel):
    """One retained mission fact."""

    observation_seq: int
    t_sim_ns: int
    kind: str
    """e.g. "keyframe", "subgoal_done", "landmark", "decision"."""
    summary: str
    position: Vec3 | None = None
    yaw_rad: float | None = None
    """Vehicle yaw synchronized with retained visual evidence, when available."""
    label: str | None = None
    """What the remembered evidence was *of*.

    Without this, a consumer retrieving "the most salient thing I remember"
    happily returns a nearby distractor — a close, high-scoring detection of the
    wrong object outranks a distant, correct one.  Memory must carry identity,
    not just position and score.
    """
    salience: float = 0.0
    """Selection score.  Keyframe memories keep the top-k by salience."""
    image_uri: str | None = None
    """Optional retained sensor image used by a visual monitor.

    The URI resolves only to sensor pixels copied by a memory plugin; it is not
    a simulator or environment handle.  Text-only memories leave it unset.
    """
    depth_uri: str | None = None
    """Optional depth image synchronized with :attr:`image_uri`."""


class MemorySnapshot(StrictModel):
    """The bounded semantic history handed to a policy or monitor.

    ``token_budget`` is part of the contract because "compact history" versus
    "short context" is an architecture axis, and an unbounded memory would
    silently turn a cheap configuration into an expensive one.
    """

    observation_seq: int
    t_sim_ns: int
    items: tuple[MemoryItem, ...] = ()
    semantic_summary: str | None = None
    token_budget: int = 0
    tokens_used: int = 0
    policy_name: str = "no_memory"
    stats: dict[str, float] = Field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.items and not self.semantic_summary
