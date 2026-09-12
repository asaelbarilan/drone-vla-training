"""The debugger must preserve evidence timing and refuse a false replay."""

import asyncio
import json

import pytest

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.analysis.flight_debugger import build_decisions, html_document, load_run
from uavlab.contracts import ControlCommand, MissionSpec, TaskFamily, Vec3
from uavlab.core.compose import load_architecture, load_environment


def event(kind, t, seq, payload, trace=None):
    return dict(
        event_type=kind,
        t_sim_ns=int(t * 1e9),
        seq=seq,
        payload=payload,
        trace_id=trace,
        component="test",
    )


def test_delayed_policy_and_monitor_use_source_not_completion():
    frames = [{"observation_seq": 7, "t": 0}, {"observation_seq": 8, "t": 1}]
    events = [
        event(
            "decision_proposed",
            1,
            0,
            {"producer": "onfly_decision", "source_observation_seq": 7},
            "p",
        ),
        event("decision_executed", 1, 1, {}, "p"),
        event("control", 1.05, 2, {}, "p"),
        event("monitor", 1, 3, {"evidence_observation_seq": 7, "label": "continue"}),
        event("monitor", 2, 4, {"label": "continue"}),
    ]
    decisions = build_decisions(events, frames, [])
    assert decisions[0]["source_index"] == decisions[1]["source_index"] == 0
    assert decisions[0]["first_control_t"] == 1.05
    assert decisions[2]["source_index"] is None
    assert decisions[0]["recording"] is None


def test_rejected_decision_cannot_inherit_another_decisions_controls():
    events = [
        event("decision_proposed", 1, 0, {"producer": "p", "source_observation_seq": 7}, "bad"),
        event("decision_proposed", 1, 1, {"rejected": True}, "bad"),
        event("control", 1, 2, {}, "good"),
    ]
    (decision,) = build_decisions(events, [{"observation_seq": 7, "t": 0}], [])
    assert decision["state"] == "rejected"
    assert decision["first_control_t"] is None


def test_untrusted_response_cannot_escape_data_script():
    html = html_document({"response": "</script><script>alert(1)</script>"})
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script>" in html


async def make_recorded_run(path):
    arch = load_architecture("c0")
    config = load_environment("grid_nav")
    mission = MissionSpec(
        mission_id="fixture",
        instruction=config.instruction,
        task_family=TaskFamily.LONG_HORIZON_NAV,
    )
    env = DeterministicEnv(**config.params)
    await env.reset(mission, 1061)
    events = []
    for i in range(4):
        obs = await env.observe()
        payload = {
            "position_x": obs.position.x,
            "position_y": obs.position.y,
            "position_z": obs.position.z,
            "vx": 0.1,
            "vy": 0.2,
            "vz": 0,
            "yaw_rate": 0.1,
        }
        events.append(event("control", i * 0.05, i, payload))
        await env.step(
            ControlCommand(
                t_sim_ns=i * 50_000_000, velocity=Vec3(x=0.1, y=0.2, z=0), yaw_rate_rps=0.1
            ),
            50_000_000,
        )
    distance = env.status().distance_to_goal_m
    await env.close()
    manifest = {
        "architecture_config": arch.model_dump(mode="json"),
        "environment_config": config.model_dump(mode="json"),
        "seeds": [1061],
    }
    (path / "manifest.json").write_text(json.dumps(manifest))
    (path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    (path / "result.json").write_text(json.dumps({"metrics": {"distance_to_goal_m": distance}}))


def test_replay_checks_every_pose_and_final_state_without_inference(tmp_path, monkeypatch):
    from uavlab.core.orchestrator import Orchestrator

    def forbidden(*args, **kwargs):
        raise AssertionError("Debugger must not run an architecture")

    monkeypatch.setattr(Orchestrator, "run", forbidden)
    asyncio.run(make_recorded_run(tmp_path))
    run = asyncio.run(load_run(tmp_path))
    assert len(run["frames"]) == 5
    assert run["frames"][-1]["t"] == 0.2
    assert run["provenance"]["checked_positions"] == 4
    assert run["provenance"]["final_distance_error_m"] == 0
    path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    events[1]["payload"]["position_x"] += 1
    path.write_text("\n".join(json.dumps(e) for e in events))
    with pytest.raises(ValueError, match="position mismatch"):
        asyncio.run(load_run(tmp_path))


def test_adaptive_plan_state_is_joined_only_to_its_own_decision():
    events = [
        event(
            "memory_update",
            1,
            0,
            {"kind": "adaptive_visual_plan", "response": {"active_id": "inspect"}},
            "a",
        ),
        event(
            "decision_proposed",
            1,
            1,
            {"producer": "adaptive_visual_plan", "source_observation_seq": 7},
            "a",
        ),
        event(
            "decision_proposed",
            2,
            2,
            {"producer": "onfly_decision", "source_observation_seq": 8},
            "b",
        ),
    ]
    decisions = build_decisions(
        events, [{"observation_seq": 7, "t": 0}, {"observation_seq": 8, "t": 1}], []
    )
    assert decisions[0]["chain"][0]["payload"]["response"]["active_id"] == "inspect"
    assert not any(e["event_type"] == "memory_update" for e in decisions[1]["chain"])


def test_capability_replay_updates_scene_and_rejects_wrong_score(tmp_path):
    from scripts.validate_capability_scenarios import record

    folder, _ = asyncio.run(record("closing_passage", tmp_path))
    data = asyncio.run(load_run(folder))
    assert len(data["frames"][0]["scene"]["obstacles"]) == 2
    assert len(data["frames"][-1]["scene"]["obstacles"]) == 3
    assert data["frames"][-1]["scene"]["task_status"]["task_complete"]
    result = json.loads((folder / "result.json").read_text())
    result["status"]["task_complete"] = False
    (folder / "result.json").write_text(json.dumps(result))
    with pytest.raises(ValueError, match="Replay task status mismatch"):
        asyncio.run(load_run(folder))
