"""Mission-progress supervision and bounded reasoning admission.

Supports both families the literature contrasts:

* a persistent low-rate monitor emitting CONTINUE/STOP/LOST (OnFly-like), and
* a reasoner that is absent during nominal execution and admitted only on a
  trigger (PMR-like).

They are competing hypotheses about *when* expensive reasoning should run, so
the runtime represents both and lets the experiment decide.
"""

from __future__ import annotations

from pydantic import Field

from uavlab.contracts.common import ProgressLabel, StrictModel, Vec3


class ProgressState(StrictModel):
    """A monitor's verdict plus the evidence behind it."""

    label: ProgressLabel
    observation_seq: int
    t_sim_ns: int
    confidence: float = 1.0
    evidence: str = ""
    distance_to_goal_m: float | None = None
    stalled_for_s: float = 0.0
    """Seconds without meaningful progress; the usual no-progress trigger."""
    monitor_name: str = "none"
    recovery_anchor_valid: bool = True
    """Whether this verdict may replace the executive's last-normal pose.

    A verdict can permit motor-level CONTINUE without establishing a fresh
    semantic-normal observation.  The producer must set this only when its own
    bounded evidence also establishes temporal continuity.
    """
    recovery_reacquired: bool = False
    """Whether current monitor evidence may cancel an active LOST maneuver.

    Reacquisition and anchor replacement are deliberately distinct. A visual
    STOP vetoed by far depth is not a trustworthy new normal anchor, but its
    explicit latest-frame visibility can still mean that reorientation should
    end and nominal waypoint execution should resume.
    """
class RecoveryTrigger(StrictModel):
    """Why recovery reasoning was admitted.

    Recording the trigger separately from the outcome is what makes the
    "trigger misses important semantic corrections" falsification testable.
    """

    name: str
    fired_t_sim_ns: int
    observation_seq: int
    cause: str
    metrics: dict[str, float] = Field(default_factory=dict)


class RecoveryRequest(StrictModel):
    """A bounded request for expensive semantic help."""

    trigger: RecoveryTrigger
    state_summary: str
    allowed_skills: tuple[str, ...] = ()
    """The reasoner may only choose from this bounded set."""
    last_known_target: Vec3 | None = None
    call_index: int = 0
    """Which reasoner call this is; enforces the ``max_calls`` budget."""
