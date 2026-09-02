"""Typed contracts shared by every component of the testbed.

Nothing in this package may import from :mod:`uavlab.plugins` or
:mod:`uavlab.adapters`.  Contracts are the neutral ground: if a contract had to
know about a plugin, that plugin's design would have leaked into the shared
interface and architectures would stop being interchangeable.
"""

from uavlab.contracts.admission import AdmissionDecision, AdmissionRuntime
from uavlab.contracts.common import (
    NANOS_PER_SECOND,
    DecisionKind,
    Frame,
    ProgressLabel,
    SafetyVerdict,
    StrictModel,
    TaskFamily,
    TerminationReason,
    Vec3,
    ns_to_s,
    s_to_ns,
)
from uavlab.contracts.decision import (
    ActionChunk,
    DecisionEnvelope,
    DecisionPayload,
    KinematicAction,
    MissionDirective,
    SkillCall,
    WaypointGoal,
)
from uavlab.contracts.events import EpisodeEvent, EventType
from uavlab.contracts.memory import MemoryItem, MemorySnapshot
from uavlab.contracts.mission import MissionConstraints, MissionSpec, SuccessCriteria
from uavlab.contracts.motion import ControlCommand, Trajectory, TrajectoryPoint
from uavlab.contracts.observation import (
    CameraIntrinsics,
    IMUSample,
    ObservationPacket,
    SemanticHit,
    SensorRef,
)
from uavlab.contracts.perception import (
    Detection,
    FeatureRef,
    OccupancyHint,
    PerceptionState,
)
from uavlab.contracts.progress import ProgressState, RecoveryRequest, RecoveryTrigger
from uavlab.contracts.safety import SafetyDecision

__all__ = [
    "NANOS_PER_SECOND",
    "ActionChunk",
    "AdmissionDecision",
    "AdmissionRuntime",
    "CameraIntrinsics",
    "ControlCommand",
    "DecisionEnvelope",
    "DecisionKind",
    "DecisionPayload",
    "Detection",
    "EpisodeEvent",
    "EventType",
    "FeatureRef",
    "Frame",
    "IMUSample",
    "KinematicAction",
    "MemoryItem",
    "MemorySnapshot",
    "MissionConstraints",
    "MissionDirective",
    "MissionSpec",
    "ObservationPacket",
    "OccupancyHint",
    "PerceptionState",
    "ProgressLabel",
    "ProgressState",
    "RecoveryRequest",
    "RecoveryTrigger",
    "SafetyDecision",
    "SafetyVerdict",
    "SemanticHit",
    "SensorRef",
    "SkillCall",
    "StrictModel",
    "SuccessCriteria",
    "TaskFamily",
    "TerminationReason",
    "Trajectory",
    "TrajectoryPoint",
    "Vec3",
    "WaypointGoal",
    "ns_to_s",
    "s_to_ns",
]

# Every contract the specification requires, by name, so the contract test can
# assert the set is complete rather than trusting that nothing was dropped.
REQUIRED_CONTRACTS: tuple[str, ...] = (
    "MissionSpec",
    "ObservationPacket",
    "PerceptionState",
    "MemorySnapshot",
    "DecisionEnvelope",
    "SafetyDecision",
    "ProgressState",
    "RecoveryRequest",
    "AdmissionDecision",
    "Trajectory",
    "ControlCommand",
    "EpisodeEvent",
)
