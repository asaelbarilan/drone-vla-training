"""Perception remains a requested information skill, with no motion authority."""

import asyncio
import json
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from uavlab.contracts import (
    MemorySnapshot,
    MissionSpec,
    ObservationPacket,
    PerceptionState,
    SensorRef,
    TaskFamily,
    Vec3,
)
from uavlab.contracts.observation import CameraIntrinsics
from uavlab.core.clock import SimClock
from uavlab.core.event_log import EventLog
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.frame_store import global_store
from uavlab.core.services import RuntimeServices, bind
from uavlab.interfaces import DecisionContext, InferenceResult
from uavlab.plugins.reasoning.aerialclaw_visual import (
    AerialClawVisualAgentPolicy,
    ObjectLocation,
    locate_in_depth,
)

MISSION = MissionSpec(
    mission_id="tool",
    instruction="Fly to the red pillar and stop.",
    task_family=TaskFamily.SEMANTIC_GOAL_NAV,
    allowed_skills=("detect_object", "goto", "scan", "hover", "stop"),
)


class Model:
    name = "stub_real"
    model_id = "test-model"

    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        return InferenceResult(payload=next(self.replies))


def action(skill, args):
    return json.dumps(
        {
            "thinking": "select skill",
            "reflection": None,
            "goal_progress": "working",
            "decision": "act",
            "action": {"skill": skill, "args": args},
        }
    )


def context(t=0, position=None):
    rgb, dep = f"mem://test-rgb-{t}", f"mem://test-depth-{t}"
    global_store().put(rgb, Image.new("RGB", (224, 224), (220, 40, 40)))
    global_store().put(dep, np.full((224, 224), 12.0))
    obs = ObservationPacket(
        seq=t + 1,
        t_sim_ns=t * 10**9,
        t_wall_ns=0,
        position=position or Vec3(x=0, y=0, z=3),
        velocity=Vec3(x=0, y=0, z=0),
        yaw_rad=0,
        battery_frac=1,
        rgb=SensorRef(kind="rgb", uri=rgb, digest=str(t)),
        depth=SensorRef(kind="depth", uri=dep, digest=str(t)),
        intrinsics=CameraIntrinsics(width=224, height=224, fx=112, fy=112, cx=112, cy=112),
    )
    return DecisionContext(
        mission=MISSION,
        observation=obs,
        perception=PerceptionState(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        memory=MemorySnapshot(observation_seq=obs.seq, t_sim_ns=obs.t_sim_ns),
        t_sim_ns=obs.t_sim_ns,
        t_wall_ns=0,
        episode_id="tool",
    )


def policy(replies):
    model = Model(replies)
    p = AerialClawVisualAgentPolicy(
        model_id=model.model_id,
        visual_target_query="red pillar",
        camera_pitch_rad=0,
        allowed_skills=MISSION.allowed_skills,
    )
    bind(
        p,
        RuntimeServices(
            clock=SimClock(),
            log=EventLog("tool"),
            feature_cache=FeatureCache(),
            inference=model,
            episode_id="tool",
        ),
    )
    p.reset(MISSION, 1061)
    return p, model


def test_model_requests_detection_then_independently_selects_flight():
    p, model = policy(
        [
            action("detect_object", {"query": "red pillar"}),
            '{"visible":true,"u":502,"v":502}',
            action("goto", {"x": 12, "y": 0, "z": 3}),
        ]
    )
    assert asyncio.run(p.decide(context())) is None
    assert len(model.requests) == 1 and not model.requests[0].images
    assert asyncio.run(p.decide(context(9))) is None
    assert model.requests[1].role == "perception" and len(model.requests[1].images) == 1
    assert model.requests[1].observation_seq == 10  # fresh frame, not initial planning frame
    assert p._visual_memory.t_sim_ns == 9 * 10**9
    decision = asyncio.run(p.decide(context(11)))
    assert decision.payload.skill_name == "goto"
    assert not model.requests[2].images
    assert p._active_skill.target_evidence_t_sim_ns == 9 * 10**9
    assert p._context_with_visual_memory(context(20)).memory.items == ()  # cannot rejuvenate memory
    assert p.stats()["aerialclaw_visual_tool_calls"] == 1
    p.reset(MISSION, 1061)
    assert p._visual_memory is None and p._pending is None


@pytest.mark.parametrize(
    "response",
    [
        '{"visible":false,"u":null,"v":null}',
        '{"visible":true,"u":502,"v":502}',
    ],
)
def test_absence_or_missing_depth_never_creates_target_or_motion(response):
    p, model = policy([action("detect_object", {"query": "red pillar"}), response])
    assert asyncio.run(p.decide(context())) is None
    ctx = context(9)
    global_store().put(ctx.observation.depth.uri, np.full((224, 224), np.inf))
    assert asyncio.run(p.decide(ctx)) is None
    assert p._visual_memory is None and p._active_skill is None
    assert len(model.requests) == 2


def test_wrong_query_cannot_inject_a_target_detection():
    p, model = policy([action("detect_object", {"query": "blue pillar"})])
    assert asyncio.run(p.decide(context())) is None
    assert p._pending is None and p._visual_memory is None
    assert len(model.requests) == 1
    assert not p._history[-1]["feedback"]["dispatch_accepted"]


@pytest.mark.parametrize(
    "bad",
    [
        {"visible": True, "u": 1000, "v": 500},
        {"visible": True, "u": True, "v": 500},
        {"visible": "yes", "u": 500, "v": 500},
    ],
)
def test_detection_schema_rejects_invalid_pixels(bad):
    with pytest.raises(ValidationError):
        ObjectLocation.model_validate(bad)


def test_projected_object_location_uses_pose_and_calibration():
    from uavlab.core.camera import Camera

    ctx = context(position=Vec3(x=3, y=-2, z=4))
    yaw, pitch = 0.7, -0.1
    ctx = replace(ctx, observation=ctx.observation.model_copy(update={"yaw_rad": yaw}))
    camera = Camera(width=224, height=224, pitch_rad=pitch)
    point = np.array([[14, 8, 3]])
    uv, depth = camera.project(point, np.array([3, -2, 4]), yaw)
    u, v = [round(x * 999 / 223) for x in uv[0]]
    result, _ = locate_in_depth(
        ObjectLocation(visible=True, u=u, v=v), ctx, np.full((224, 224), depth[0]), pitch
    )
    assert result.distance_to(Vec3(x=14, y=8, z=3)) < 0.03


def test_debugger_matches_perception_tool_image_to_fresh_observation():
    from uavlab.analysis.flight_debugger import build_decisions

    events = [
        {
            "event_type": "skill_tool",
            "seq": 3,
            "t_sim_ns": 10 * 10**9,
            "trace_id": "tool-result",
            "payload": {"phase": "completed", "role": "perception", "source_observation_seq": 10},
        }
    ]
    record = {"role": "perception", "observation_seq": 10, "completed_t_sim_ns": 10 * 10**9}
    result = build_decisions(events, [{"observation_seq": 10, "t": 9}], [record])[0]
    assert result["source_seq"] == 10 and result["recording"] == record
    assert result["role"] == "perception" and result["state"] == "completed"
    assert result["first_control_t"] is None
