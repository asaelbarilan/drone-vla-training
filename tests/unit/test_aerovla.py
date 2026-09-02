"""Paper/source-locked invariants for the AeroVLA testbed adapter."""

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
)
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.frame_store import global_store
from uavlab.core.registry import REGISTRY
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult
from uavlab.plugins.reasoning import aerovla as aerovla_module
from uavlab.plugins.reasoning.aerovla import (
    FORWARD_RANGE,
    VERTICAL_DOWN_RANGE,
    YAW_RANGE,
    AeroVLAOutput,
    AeroVLAOutputError,
    AeroVLAPolicy,
    action_from_output,
    dequantize,
    make_dual_view_mosaic,
    parse_aerovla_output,
)

MISSION = MissionSpec(
    mission_id="aerovla-test",
    instruction="fly to the red tower and stop there",
    task_family=TaskFamily.LONG_HORIZON_NAV,
)


class StubModel:
    name = "stub_aerovla"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.requests = []

    async def invoke(self, request) -> InferenceResult:
        self.requests.append(request)
        reply = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        return InferenceResult(payload=reply, output_tokens=4, latency_ns=0)


def context(seed: int = 1060) -> DecisionContext:
    env = REGISTRY.build(
        "environment",
        "grid3d",
        {
            "render": True,
            "render_down": True,
            "coarse_goal_direction": True,
            "sensor_range_m": 60.0,
        },
    )
    obs = asyncio.run(env.reset(MISSION, seed))
    obs = obs.model_copy(update={"privileged": {"goal": (999.0, 999.0, 999.0)}})
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=obs.t_wall_ns,
        episode_id="aerovla-test",
    )


def policy(replies: list[str]) -> tuple[AeroVLAPolicy, StubModel]:
    model = StubModel(replies)
    instance = AeroVLAPolicy(model_id="stub", output_format="json")
    services = RuntimeServices(
        clock=SimClock(),
        log=EventLog("aerovla-test", None),
        feature_cache=FeatureCache(),
        inference=model,
        episode_id="aerovla-test",
    )
    bind(instance, services)
    instance.reset(MISSION, 1060)
    return instance, model


def test_official_99_bin_codec_and_release_ranges() -> None:
    assert dequantize(0, FORWARD_RANGE) == 0.0
    assert dequantize(98, FORWARD_RANGE) == 5.0
    assert dequantize(49, VERTICAL_DOWN_RANGE) == pytest.approx(0.0)
    assert dequantize(0, YAW_RANGE) == -1.1
    assert dequantize(98, YAW_RANGE) == 1.1
    with pytest.raises(AeroVLAOutputError):
        dequantize(99, FORWARD_RANGE)


def test_parser_accepts_only_strict_json_or_official_three_tokens() -> None:
    expected = AeroVLAOutput(12, 49, 51, False)
    assert parse_aerovla_output(
        '{"forward_bin":12,"vertical_bin":49,"yaw_bin":51,"land":false}'
    ) == expected
    assert parse_aerovla_output("prompt\nAction: 12 49 51") == expected
    assert parse_aerovla_output("Action: 00 49 49 LAND").land is True
    for invalid in (
        "",
        "Action: 12 49",
        "Action: 12 49 51 60",
        '{"forward_bin":12,"vertical_bin":49,"yaw_bin":51,"land":0}',
        '{"forward_bin":12,"vertical_bin":49,"yaw_bin":99,"land":false}',
        '{"forward_bin":12,"vertical_bin":49,"yaw_bin":51,"land":false,"x":1}',
    ):
        with pytest.raises(AeroVLAOutputError):
            parse_aerovla_output(invalid)


def test_body_offset_becomes_direct_enu_action_and_zero_is_land() -> None:
    action, decoded = action_from_output(AeroVLAOutput(98, 49, 49), yaw_rad=math.pi / 2)
    assert action is not None
    assert decoded == pytest.approx({"forward_m": 5.0, "down_m": 0.0, "yaw_delta_rad": 0.0})
    assert action.velocity.x == pytest.approx(0.0, abs=1e-8)
    assert action.velocity.y == pytest.approx(1.0)
    assert action.velocity.z == pytest.approx(0.0)
    assert action.duration_s == pytest.approx(5.0)

    landing, _ = action_from_output(AeroVLAOutput(0, 49, 49), yaw_rad=0.0)
    assert landing is None

    left, _ = action_from_output(AeroVLAOutput(20, 49, 0), yaw_rad=0.0)
    assert left is not None and left.yaw_rate_rps > 0.0


def test_vertical_mosaic_keeps_front_on_top_and_down_on_bottom() -> None:
    from PIL import Image

    front = Image.new("RGB", (32, 32), (255, 0, 0))
    down = Image.new("RGB", (32, 32), (0, 0, 255))
    mosaic = make_dual_view_mosaic(front, down, 224)
    assert mosaic.size == (224, 224)
    assert mosaic.getpixel((112, 20))[0] > 240
    assert mosaic.getpixel((112, 203))[2] > 240


def test_environment_exposes_bucket_and_real_down_frame_without_truth() -> None:
    ctx = context()
    obs = ctx.observation
    assert obs.coarse_goal_direction in {
        "straight ahead",
        "forward-right",
        "to your right",
        "to your right rear",
        "forward-left",
        "to your left",
        "to your left rear",
    }
    assert obs.rgb_down is not None and obs.rgb_down.shape == (224, 224)
    assert global_store().get(obs.rgb_down.uri) is not None


def test_coarse_hint_respects_enu_left_right_sign() -> None:
    env = REGISTRY.build(
        "environment",
        "grid3d",
        {"render": False, "coarse_goal_direction": True},
    )
    asyncio.run(env.reset(MISSION, 1060))
    env.vehicle.yaw = 0.0
    env.goal = env.vehicle.position.copy()
    env.goal[1] += 10.0
    assert env._coarse_goal_direction() == "to your left"
    env.goal[1] -= 20.0
    assert env._coarse_goal_direction() == "to your right"


def test_real_dual_view_request_becomes_typed_direct_action() -> None:
    instance, model = policy(
        ['{"forward_bin":20,"vertical_bin":49,"yaw_bin":49,"land":false}']
    )
    envelope = asyncio.run(instance.decide(context()))
    assert envelope is not None and envelope.kind is DecisionKind.KINEMATIC_ACTION
    assert len(model.requests) == 1
    assert len(model.requests[0].images) == 1
    assert model.requests[0].response_schema is not None
    assert envelope.provenance["forward_bin"] == "20"
    assert envelope.provenance["coarse_goal_direction"] != "None"


def test_land_is_model_authored_and_malformed_output_fails_closed() -> None:
    instance, _ = policy(
        ['{"forward_bin":0,"vertical_bin":49,"yaw_bin":49,"land":true}']
    )
    envelope = asyncio.run(instance.decide(context()))
    assert envelope is not None and envelope.kind is DecisionKind.MISSION_DIRECTIVE
    assert instance.stats()["aerovla_land_outputs"] == 1

    broken, _ = policy(["{}"])
    with pytest.raises(AeroVLAOutputError):
        asyncio.run(broken.decide(context()))
    assert broken.stats()["aerovla_parse_errors"] == 1


def test_policy_source_has_no_detector_depth_memory_or_truth_access() -> None:
    tree = ast.parse(inspect.getsource(aerovla_module))
    accessed = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not {"semantic_hits", "depth", "privileged", "memory", "goal_hint"} & accessed


def test_aerovla_profiles_keep_direct_path_and_isolate_the_shield(arch_factory) -> None:
    c7 = arch_factory("c7_aerovla_gemma")
    c8 = arch_factory("c8_aerovla_gemma")
    assert c7.profile_of == "c7" and c8.profile_of == "c8"
    assert c7.policy == c8.policy
    assert c7.inference == c8.inference
    assert c7.planner is None and c8.planner is None
    assert c7.verifier is None and c8.verifier is None
    assert c7.shield is None and c8.shield is not None
    assert c7.memory.name == "no_memory" and c8.memory.name == "no_memory"
