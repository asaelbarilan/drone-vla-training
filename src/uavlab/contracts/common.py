"""Primitive types shared by every contract.

Two rules are enforced here rather than by researcher discipline:

1. Time is always nanoseconds, and simulation time is never mixed with wall
   time.  Every contract that crosses a component boundary carries both.
2. A frame is never inferred from context.  Anything with a spatial meaning
   names its frame explicitly.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

NANOS_PER_SECOND = 1_000_000_000


def s_to_ns(seconds: float) -> int:
    """Convert seconds to integer nanoseconds (the canonical time unit)."""
    return int(round(seconds * NANOS_PER_SECOND))


def ns_to_s(nanos: int) -> float:
    """Convert integer nanoseconds to float seconds (display/metrics only)."""
    return nanos / NANOS_PER_SECOND


class StrictModel(BaseModel):
    """Base for every contract.

    ``extra="forbid"`` is deliberate: a plugin that smuggles model-specific
    fields through a shared contract would silently break the "architectures
    are configuration" property, because downstream components would start
    depending on the identity of the upstream model.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=False)


class Frame(str, Enum):
    """Coordinate frames the testbed knows about.

    ``ENU`` is the canonical internal frame.  ``NED`` exists because PX4 and
    most flight stacks speak it; conversion happens only in adapters, only via
    :mod:`uavlab.core.frames`, and never implicitly.
    """

    ENU = "enu"
    NED = "ned"
    BODY = "body"


class Vec3(StrictModel):
    """A 3-vector tagged with its frame."""

    x: float
    y: float
    z: float
    frame: Frame = Frame.ENU

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)

    def distance_to(self, other: Vec3) -> float:
        if other.frame is not self.frame:
            raise ValueError(
                f"refusing to compare {self.frame.value} with {other.frame.value}; "
                "convert explicitly via uavlab.core.frames"
            )
        dx, dy, dz = self.x - other.x, self.y - other.y, self.z - other.z
        return (dx * dx + dy * dy + dz * dz) ** 0.5

    def norm(self) -> float:
        return (self.x**2 + self.y**2 + self.z**2) ** 0.5


class TaskFamily(str, Enum):
    """Benchmark regimes.

    These are the five regimes the evaluation protocol requires; they exist so
    that results are always reported per-regime rather than pooled into a
    single leaderboard number.
    """

    LONG_HORIZON_NAV = "long_horizon_nav"
    OBJECT_SEARCH = "object_search"
    FAILURE_RECOVERY = "failure_recovery"
    FINE_MANEUVER = "fine_maneuver"
    PARTIAL_OBSERVABILITY = "partial_observability"


class DecisionKind(str, Enum):
    """The five semantic-authority levels a policy may exercise.

    This enum *is* the architecture axis "where learned semantic intelligence
    hands off physical authority".  Adding a member is a research decision, not
    a refactor.
    """

    SKILL = "skill"
    WAYPOINT = "waypoint"
    KINEMATIC_ACTION = "kinematic_action"
    ACTION_CHUNK = "action_chunk"
    MISSION_DIRECTIVE = "mission_directive"


class ProgressLabel(str, Enum):
    """Mission-progress verdicts a monitor may emit."""

    CONTINUE = "continue"
    STOP = "stop"
    LOST = "lost"
    BLOCKED = "blocked"
    AMBIGUOUS = "ambiguous"


class SafetyVerdict(str, Enum):
    """What the safety shield did to a proposal."""

    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"
    STOP = "stop"


class TerminationReason(str, Enum):
    """Why an episode ended.  Distinguishes *correct* stops from timeouts."""

    GOAL_REACHED = "goal_reached"
    AGENT_STOPPED = "agent_stopped"
    COLLISION = "collision"
    OUT_OF_BOUNDS = "out_of_bounds"
    TIMEOUT = "timeout"
    RUNTIME_ERROR = "runtime_error"
