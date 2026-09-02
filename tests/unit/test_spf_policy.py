"""Paper-locked invariants for the clean-room See, Point, Fly policy."""

from __future__ import annotations

import ast
import asyncio
import inspect
import math

import pytest

from uavlab.contracts import (
    DecisionKind,
    MemorySnapshot,
    MissionSpec,
    PerceptionState,
    TaskFamily,
    Vec3,
)
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult
from uavlab.plugins.reasoning import spf as spf_module
from uavlab.plugins.reasoning.spf import (
    SPFPoint,
    SPFWaypointPolicy,
    adaptive_distance_m,
    parse_spf_point,
    point_to_enu,
)

MISSION = MissionSpec(
    mission_id="spf-test",
    instruction="fly to the red tower and stop there",
    task_family=TaskFamily.LONG_HORIZON_NAV,
)


class StubVisionModel:
    name = "stub_vision"
    model_id = "qwen3-vl:8b"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.requests = []

    @staticmethod
    def encode_image(image) -> str:
        return f"image-{image.width}x{image.height}"

    async def invoke(self, request) -> InferenceResult:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.replies) - 1)
        return InferenceResult(payload=self.replies[index], output_tokens=8, latency_ns=0)


def context(seed: int = 1040) -> DecisionContext:
    env = REGISTRY.build(
        "environment",
        "grid3d",
        {"render": True, "render_depth": True, "sensor_range_m": 60.0},
    )
    obs = asyncio.run(env.reset(MISSION, seed))
    # Include every tempting non-RGB channel. The policy must still use only the
    # RGB reference, mission, pose/yaw and intrinsics.
    obs = obs.model_copy(update={"privileged": {"goal": (999.0, 999.0, 999.0)}})
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="spf-test",
    )


def policy(replies: list[str]) -> tuple[SPFWaypointPolicy, StubVisionModel]:
    model = StubVisionModel(replies)
    instance = SPFWaypointPolicy(model_id=model.model_id)
    services = RuntimeServices(
        clock=SimClock(),
        log=EventLog("spf-test", None),
        feature_cache=FeatureCache(),
        inference=model,
        episode_id="spf-test",
    )
    bind(instance, services)
    instance.reset(MISSION, 1040)
    return instance, model


def test_published_adaptive_distance_equation() -> None:
    assert adaptive_distance_m(10) == pytest.approx(10.0)
    assert adaptive_distance_m(1) == pytest.approx(10 * 0.1**1.8)
    assert adaptive_distance_m(5) == pytest.approx(10 * 0.5**1.8)
    with pytest.raises(ValueError):
        adaptive_distance_m(0)


def test_schema_is_strict_and_bounded() -> None:
    assert parse_spf_point('{"u":500,"v":400,"distance":3}') == SPFPoint(500, 400, 3)
    for invalid in (
        "not json",
        '{"u":500,"v":400}',
        '{"u":500,"v":400,"distance":3,"done":false}',
        '{"u":1001,"v":400,"distance":3}',
        '{"u":true,"v":400,"distance":3}',
    ):
        with pytest.raises(ValueError):
            parse_spf_point(invalid)


def test_pinhole_lift_has_correct_body_to_enu_signs() -> None:
    centered = point_to_enu(
        SPFPoint(500, 500, 5),
        position=Vec3(x=1, y=2, z=3),
        yaw_rad=0,
        width=200,
        height=100,
        fx=100,
        fy=100,
        cx=100,
        cy=50,
        camera_pitch_rad=0,
        distance_m=4,
        min_altitude_m=0.5,
    )
    assert centered == Vec3(x=5, y=2, z=3)
    right = point_to_enu(
        SPFPoint(1000, 500, 5),
        position=Vec3(x=0, y=0, z=3),
        yaw_rad=0,
        width=200,
        height=100,
        fx=100,
        fy=100,
        cx=100,
        cy=50,
        camera_pitch_rad=0,
        distance_m=4,
        min_altitude_m=0.5,
    )
    assert right.x == pytest.approx(4)
    assert right.y == pytest.approx(-4)
    assert right.z == pytest.approx(3)


def test_real_image_schema_becomes_typed_waypoint() -> None:
    instance, model = policy(['{"u":500,"v":400,"distance":3}'])
    envelope = asyncio.run(instance.decide(context()))
    assert envelope is not None and envelope.kind is DecisionKind.WAYPOINT
    assert model.requests[0].images == ("image-224x224",)
    assert model.requests[0].response_schema is not None
    assert envelope.provenance["spf_distance_label"] == "3"
    assert float(envelope.provenance["spf_step_m"]) == pytest.approx(
        adaptive_distance_m(3), abs=1e-6
    )


def test_two_near_labels_produce_stop_without_world_distance() -> None:
    instance, _ = policy(['{"u":500,"v":500,"distance":1}', '{"u":500,"v":500,"distance":1}'])
    ctx = context()
    first = asyncio.run(instance.decide(ctx))
    second = asyncio.run(instance.decide(ctx))
    assert first.kind is DecisionKind.WAYPOINT
    assert second.kind is DecisionKind.MISSION_DIRECTIVE
    assert instance.stats()["spf_stop_outputs"] == 1


def test_invalid_model_output_fails_closed() -> None:
    instance, _ = policy(["{}"])
    with pytest.raises(RuntimeError, match="invalid SPF model output"):
        asyncio.run(instance.decide(context()))
    assert instance.stats()["spf_invalid_outputs"] == 1


def test_policy_source_has_no_forbidden_observation_channels() -> None:
    tree = ast.parse(inspect.getsource(spf_module))
    accessed = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not {"semantic_hits", "privileged", "depth"} & accessed


def test_camera_pitch_is_applied_not_ignored() -> None:
    level = point_to_enu(
        SPFPoint(500, 500, 5),
        position=Vec3(x=0, y=0, z=3),
        yaw_rad=math.pi / 2,
        width=224,
        height=224,
        fx=112,
        fy=112,
        cx=112,
        cy=112,
        camera_pitch_rad=0,
        distance_m=2,
        min_altitude_m=0.5,
    )
    pitched = point_to_enu(
        SPFPoint(500, 500, 5),
        position=Vec3(x=0, y=0, z=3),
        yaw_rad=math.pi / 2,
        width=224,
        height=224,
        fx=112,
        fy=112,
        cx=112,
        cy=112,
        camera_pitch_rad=-0.15,
        distance_m=2,
        min_altitude_m=0.5,
    )
    assert pitched.z < level.z
