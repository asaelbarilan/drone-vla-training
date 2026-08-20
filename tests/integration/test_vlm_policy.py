"""The real-VLM policy, tested without a model server.

A stub backend returns canned replies, so these run in CI with no network, no
Ollama and no weights. What is under test is everything *around* the model: does
a pixel become the right waypoint, does a malformed reply degrade safely, and
does a missing frame fail loudly instead of quietly becoming a blind policy.

The last one matters most. A vision policy that silently continues when it has
no image still produces well-formed waypoints, and the resulting numbers would
be indistinguishable from a working vision system.
"""

from __future__ import annotations

import asyncio

import pytest

from uavlab.contracts import DecisionKind, MissionSpec, ProgressLabel, TaskFamily
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult
from uavlab.plugins.reasoning.vlm import VLMPointWaypointPolicy

MISSION = MissionSpec(
    mission_id="vlm", instruction="fly to the red tower", task_family=TaskFamily.LONG_HORIZON_NAV
)


class StubVLM:
    """An inference backend that replays scripted replies. No network."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.last_images: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return "stub_vlm"

    def reset(self, mission, seed) -> None:
        self.calls = 0

    @staticmethod
    def encode_image(image) -> str:
        return f"stub-image-{image.width}x{image.height}"

    async def invoke(self, request) -> InferenceResult:
        self.last_images = request.images
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return InferenceResult(payload=reply, output_tokens=12, latency_ns=0)

    def stats(self) -> dict[str, float]:
        return {"inference_calls_policy": float(self.calls)}


def make_policy(replies: list[str], **params) -> tuple[VLMPointWaypointPolicy, StubVLM]:
    backend = StubVLM(replies)
    policy = VLMPointWaypointPolicy(**params)
    services = RuntimeServices(
        clock=SimClock(),
        log=EventLog("vlm", None),
        feature_cache=FeatureCache(),
        inference=backend,
        episode_id="vlm",
    )
    bind(policy, services)
    policy.reset(MISSION, 0)
    return policy, backend


def rendering_context(seed: int = 11) -> DecisionContext:
    """A context whose observation carries a genuinely rendered frame."""
    from uavlab.contracts import MemorySnapshot, PerceptionState

    env = REGISTRY.build("environment", "grid3d", {"render": True, "sensor_range_m": 60.0})
    obs = asyncio.run(env.reset(MISSION, seed))
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="vlm",
    )


def test_a_found_target_becomes_a_waypoint_envelope():
    policy, backend = make_policy(['{"found": true, "u": 112, "v": 120, "arrived": false}'])
    envelope = asyncio.run(policy.decide(rendering_context()))
    assert envelope is not None
    assert envelope.kind is DecisionKind.WAYPOINT
    assert envelope.kind.value in policy.emits
    assert backend.calls == 1
    assert backend.last_images, "the policy must actually send the image"
    assert policy.found == 1 and policy.parse_failures == 0


def test_the_image_is_really_sent_to_the_model():
    """Guards the failure where a 'vision' policy never looks at the frame."""
    policy, backend = make_policy(['{"found": true, "u": 100, "v": 100, "arrived": false}'])
    asyncio.run(policy.decide(rendering_context()))
    assert backend.last_images and backend.last_images[0].startswith("stub-image-224x224")


def test_pointing_left_and_right_produce_waypoints_on_opposite_sides():
    """The geometry, not the model, is under test here."""
    ctx = rendering_context()
    left_policy, _ = make_policy(['{"found": true, "u": 20, "v": 112, "arrived": false}'])
    right_policy, _ = make_policy(['{"found": true, "u": 204, "v": 112, "arrived": false}'])

    left = asyncio.run(left_policy.decide(ctx)).payload.target
    right = asyncio.run(right_policy.decide(ctx)).payload.target

    import math

    yaw = ctx.observation.yaw_rad
    position = ctx.observation.position

    def bearing_offset(target):
        b = math.atan2(target.y - position.y, target.x - position.x) - yaw
        return math.atan2(math.sin(b), math.cos(b))

    # Image u increases to the right, so a larger u must give a more clockwise
    # (more negative) bearing offset.
    assert bearing_offset(left) > bearing_offset(right), (
        "pointing left and right produced waypoints on the same side; the "
        "unprojection has a sign error"
    )


def test_arrival_becomes_a_directive_not_motion():
    policy, _ = make_policy(['{"found": true, "u": 112, "v": 112, "arrived": true}'])
    envelope = asyncio.run(policy.decide(rendering_context()))
    assert envelope.kind is DecisionKind.MISSION_DIRECTIVE
    assert envelope.payload.label is ProgressLabel.STOP


def test_target_not_found_falls_back_to_search():
    policy, _ = make_policy(['{"found": false, "u": 0, "v": 0, "arrived": false}'])
    envelope = asyncio.run(policy.decide(rendering_context()))
    assert envelope.kind is DecisionKind.WAYPOINT
    assert "searching" in envelope.provenance.get("note", "")
    assert policy.not_found == 1


@pytest.mark.parametrize(
    "reply",
    [
        "I think the tower is on the left.",           # prose, no JSON
        '{"found": true, "u": "banana", "v": 5}',      # wrong types
        '{"found": true, "u": 9999, "v": 3}',          # pixel out of frame
        "",                                            # empty
    ],
)
def test_a_malformed_reply_degrades_safely(reply):
    """A model that cannot answer in format must not crash the episode."""
    policy, _ = make_policy([reply])
    envelope = asyncio.run(policy.decide(rendering_context()))
    assert envelope is not None
    assert envelope.kind is DecisionKind.WAYPOINT
    assert policy.parse_failures + policy.not_found >= 1


def test_json_wrapped_in_prose_or_fences_is_still_parsed():
    """Small models add commentary; that is a formatting quirk, not a failure."""
    policy, _ = make_policy(
        ['Sure! Here is the answer:\n```json\n{"found": true, "u": 90, "v": 100, "arrived": false}\n```']
    )
    envelope = asyncio.run(policy.decide(rendering_context()))
    assert envelope.kind is DecisionKind.WAYPOINT
    assert policy.parse_failures == 0 and policy.found == 1


def test_a_missing_frame_fails_loudly():
    """Without pixels this is a blind policy, and it must say so."""
    from uavlab.contracts import MemorySnapshot, PerceptionState

    env = REGISTRY.build("environment", "grid3d", {"render": False})
    obs = asyncio.run(env.reset(MISSION, 1))
    ctx = DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="vlm",
    )
    policy, _ = make_policy(['{"found": true, "u": 1, "v": 1, "arrived": false}'])
    with pytest.raises(RuntimeError, match="render"):
        asyncio.run(policy.decide(ctx))


def test_the_policy_reports_its_own_hit_rate():
    """Found/not-found separates 'architecture wrong' from 'model could not see'."""
    policy, _ = make_policy(
        [
            '{"found": true, "u": 100, "v": 100, "arrived": false}',
            '{"found": false, "u": 0, "v": 0, "arrived": false}',
        ]
    )
    ctx = rendering_context()
    asyncio.run(policy.decide(ctx))
    asyncio.run(policy.decide(ctx))
    stats = policy.stats()
    assert stats["vlm_found"] == 1.0
    assert stats["vlm_not_found"] == 1.0
    assert stats["vlm_found_rate"] == pytest.approx(0.5)


def _context_remembering(position, age_s: float, kind: str) -> DecisionContext:
    """A context whose memory already holds one sighting of the target."""
    from uavlab.contracts import MemoryItem, MemorySnapshot

    ctx = rendering_context()
    item = MemoryItem(
        observation_seq=ctx.observation.seq,
        t_sim_ns=ctx.t_sim_ns - int(age_s * 1e9),
        kind=kind,
        summary="remembered",
        position=position,
        label="target",
        salience=0.8,
    )
    ctx.memory = MemorySnapshot(
        observation_seq=ctx.observation.seq, t_sim_ns=ctx.t_sim_ns, items=(item,)
    )
    return ctx


def test_an_unseen_target_is_recalled_from_the_policys_own_memory():
    """The whole point of the C4->C5 memory contrast for a real model.

    Runs the recall branch end to end. Worth its own test because the branch was
    once broken at runtime -- a bool in a `dict[str, str]` provenance field --
    while the entire suite still passed, since nothing exercised it.
    """
    from uavlab.contracts import Vec3

    remembered = Vec3(x=30.0, y=5.0, z=3.0)
    policy, _ = make_policy(['{"found": false, "u": 0, "v": 0, "arrived": false}'])
    envelope = asyncio.run(policy.decide(_context_remembering(remembered, 1.0, "decision")))

    assert envelope.kind is DecisionKind.WAYPOINT
    assert "remembered" in envelope.provenance.get("note", "")
    assert envelope.provenance.get("from_memory") == "true", (
        "a decision taken from memory must be marked, or memory refreshes itself"
    )


def test_a_stale_memory_stops_steering_and_search_resumes():
    from uavlab.contracts import Vec3

    policy, _ = make_policy(['{"found": false, "u": 0, "v": 0, "arrived": false}'] * 2)
    stale = _context_remembering(Vec3(x=30.0, y=5.0, z=3.0), 60.0, "decision")
    envelope = asyncio.run(policy.decide(stale))
    assert "searching" in envelope.provenance.get("note", "")


def test_the_simulated_detector_is_not_reachable_through_memory():
    """A Gemma configuration must not recover detector sightings by remembering.

    Memory stores are fed from `perception.detections`. If this policy recalled
    those, its "memory result" would really be a detector result and the real-model
    comparison would be measuring the wrong thing.
    """
    from uavlab.contracts import Vec3

    policy, _ = make_policy(['{"found": false, "u": 0, "v": 0, "arrived": false}'])
    detector_memory = _context_remembering(Vec3(x=30.0, y=5.0, z=3.0), 1.0, "keyframe")
    envelope = asyncio.run(policy.decide(detector_memory))
    assert "searching" in envelope.provenance.get("note", "")


def test_the_waypoint_is_unprojected_from_the_pose_that_took_the_frame():
    """A slow model must not have its answer read against a newer pose.

    The vehicle keeps flying while the model thinks - 1.7 s per call for Gemma
    3 4B on this hardware, which is metres of travel. The pixel the model points
    at is only meaningful together with the pose the frame was captured from, so
    the unprojection uses `ctx.observation`, and the result is a point in WORLD
    coordinates. That is what keeps it valid however far the vehicle has moved by
    the time the command is executed.

    Pinned because the failure would be silent: reading the same pixel against
    the current pose still yields a plausible waypoint, just the wrong one, and
    the error would grow with model latency and look like a model quality
    problem.
    """
    from uavlab.contracts import Vec3

    # One context only. `reset` clears the global frame store, so building a
    # second rendering context would delete the frame this one refers to.
    ctx = rendering_context()
    policy, _ = make_policy(['{"found": true, "u": 100, "v": 110, "arrived": false}'])
    first = asyncio.run(policy.decide(ctx)).payload.target

    # The same frame and the same answer, but the vehicle has since moved and
    # turned. The waypoint must be computed from the pose that took the frame.
    ctx.observation = ctx.observation.model_copy(
        update={
            "position": Vec3(
                x=ctx.observation.position.x + 12.0,
                y=ctx.observation.position.y - 7.0,
                z=ctx.observation.position.z,
            ),
            "yaw_rad": ctx.observation.yaw_rad + 1.1,
        }
    )
    policy2, _ = make_policy(['{"found": true, "u": 100, "v": 110, "arrived": false}'])
    second = asyncio.run(policy2.decide(ctx)).payload.target

    assert (first.x, first.y) != (second.x, second.y), (
        "the unprojection ignored the observation's pose entirely; a pixel cannot "
        "be turned into a world point without knowing where the camera was"
    )
