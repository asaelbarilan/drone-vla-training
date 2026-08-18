"""Per-episode result record.

Deliberately not a single score.  The evaluation protocol requires a Pareto
surface — capability against compute — so the result carries the full vector and
leaves the trade-off visible.
"""

from __future__ import annotations

from pydantic import Field

from uavlab.contracts.common import StrictModel, TaskFamily, TerminationReason
from uavlab.contracts.env_status import EnvironmentStatus


class EpisodeResult(StrictModel):
    """Everything one episode produced, ready for paired analysis."""

    episode_id: str
    architecture_id: str
    environment_id: str
    task_family: TaskFamily
    seed: int

    success: bool
    termination_reason: TerminationReason
    termination_detail: str = ""

    sim_duration_s: float
    wall_duration_s: float
    metrics: dict[str, float] = Field(default_factory=dict)
    status: EnvironmentStatus | None = None
    config_hash: str = ""
    used_privileged_observations: bool = False
    """True when this configuration was allowed to see ground truth.

    Only the oracle control ceiling sets it. Recorded on the result rather than
    inferred from the architecture id, so the analysis layer can exclude
    reference configurations from the Pareto frontier on the basis of what they
    actually saw rather than what they are called.
    """
    error: str | None = None

    def key(self) -> tuple[str, str, int]:
        return (self.architecture_id, self.environment_id, self.seed)
