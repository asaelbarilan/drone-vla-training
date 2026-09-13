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


def test_bounded_refinement_moves_to_observed_ray_not_fabricated_range():
    ctx = context()
    depth = np.full((224, 224), np.inf)
    depth[100:115, 103:121] = 12.0
    answer = ObjectLocation(visible=True, u=499, v=533)
    assert locate_in_depth(answer, ctx, depth, 0)[0] is None
    position, range_m = locate_in_depth(answer, ctx, depth, 0, 0.03)
    assert range_m == 12.0 and position is not None
    # Nearest observed pixel is (111,114), not the original empty ray near (111,119).
    assert position.y == pytest.approx(12 / 112)
    assert position.z == pytest.approx(3 - 24 / 112)
    depth[123:125, 103:121] = 30.0
    assert locate_in_depth(answer, ctx, depth, 0, 0.03)[0] is None
    depth[123:125, 103:121] = 12.0
    assert locate_in_depth(answer, ctx, depth, 0, 0.03)[0] is None


def test_refinement_never_searches_the_full_image():
    depth = np.full((224, 224), np.inf)
    depth[50:90, 90:130] = 12
    assert (
        locate_in_depth(ObjectLocation(visible=True, u=499, v=533), context(), depth, 0, 0.03)[0]
        is None
    )


def test_visual_search_strategy_explains_that_scan_does_not_detect():
    p, _ = policy([action("detect_object", {"query": "red pillar"})])
    p.visual_search_strategy = True
    text = p._build_prompt(context())
    assert "A scan rotates the camera but never identifies objects." in text
    assert "When phase is inspect_current_viewpoint, first call detect_object" in text
    assert "## Additional perception hard skill" in text
    assert "## BODY-derived coverage reference" in text
    assert asyncio.run(p.decide(context())) is None


def test_inspected_search_retries_after_physical_full_turn_and_bounds_scan():
    from uavlab.plugins.reasoning.aerialclaw import _AgentAction

    p, model = policy([action("scan", {"yaw_rate_rps": 0.6, "duration_s": 2})])
    mission = MISSION.model_copy(update={"task_family": TaskFamily.OBJECT_SEARCH})
    p.reset(mission, 1061)
    ctx = replace(context(), mission=mission)
    p._scan_angle_since_motion_rad = 7.5  # exact prior-flight full-turn state
    assert p._local_search_complete(ctx)  # historical behavior retained
    p.inspected_search = True
    assert not p._local_search_complete(ctx)  # zero inspected views
    envelope = asyncio.run(p.decide(ctx))
    assert envelope.payload.skill_name == "scan" and len(model.requests) == 1
    rejected = p._action_protocol_error(
        _AgentAction(skill="scan", args={"yaw_rate_rps": 1.5, "duration_s": 5}), ctx
    )
    assert "at most 1.3 radians" in rejected


def test_actual_inspected_views_cover_circle_once_and_reset_after_translation():
    import math

    p, _ = policy([])
    p.inspected_search = True
    ctx = context()
    p._record_inspected_view(ctx)
    initial = len(p._inspected_bins)
    assert 0 < initial < 72
    p._record_inspected_view(ctx)
    assert len(p._inspected_bins) == initial
    assert not p._local_search_complete(ctx)
    for index in range(8):
        view = replace(
            ctx, observation=ctx.observation.model_copy(update={"yaw_rad": index * math.pi / 4})
        )
        p._record_inspected_view(view)
    assert p._local_search_complete(ctx)
    assert not p._local_search_complete(context(position=Vec3(x=1, y=0, z=3)))
    assert len(p._inspected_bins) == 0


def test_only_requested_negative_detection_marks_inspected_search():
    p, model = policy(
        [action("detect_object", {"query": "red pillar"}), '{"visible":false,"u":null,"v":null}']
    )
    p.inspected_search = True
    asyncio.run(p.decide(context()))
    assert not p._inspected_bins
    asyncio.run(p.decide(context(9)))
    assert p._inspected_bins and len(model.requests) == 2
    assert p._active_skill is None  # inspection has no movement authority
