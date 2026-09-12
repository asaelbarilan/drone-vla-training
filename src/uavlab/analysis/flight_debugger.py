"""Export a portable flight debugger from saved controls. Never invokes a model.

Reconstruction is restricted to grid3d. Positions and final distance are checked
against the log; imagery is labeled replay-rendered, not a recorded model input.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import base64
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import (
    ControlCommand,
    Frame,
    MissionConstraints,
    MissionSpec,
    SuccessCriteria,
    Vec3,
)
from uavlab.core.config import ArchitectureConfig, EnvironmentConfig
from uavlab.core.frame_store import global_store

ROOT = Path(__file__).resolve().parents[3]
SOURCE_MODULES = {
    "adaptive_policy": (
        "plugins/reasoning/adaptive_visual_plan.py",
        "AdaptiveVisualPlanPolicy",
        "decide",
    ),
    "policy": ("plugins/reasoning/onfly.py", "OnFlyDecisionAgent", "decide"),
    "monitor": ("plugins/reasoning/onfly.py", "OnFlyMonitor", "assess"),
    "router": ("core/decision_router.py", "DecisionRouter", "accept"),
    "control": ("core/orchestrator.py", "Orchestrator", "_control_loop"),
    "routing": ("core/orchestrator.py", "Orchestrator", "_handle_envelope"),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_events(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _image_uri(image) -> str | None:
    if image is None:
        return None
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _sources() -> dict:
    sources = {}
    for key, (relative, owner, function) in SOURCE_MODULES.items():
        path = ROOT / "src" / "uavlab" / relative
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef) and cls.name == owner:
                for node in cls.body:
                    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                        continue
                    if node.name == function:
                        lines = content.splitlines()
                        sources[key] = {
                            "path": str(path),
                            "line": node.lineno,
                            "function": f"{owner}.{function}",
                            "status": "Current checkout reference; not historical execution",
                            "code": "\n".join(
                                f"{i + 1:4}  {lines[i]}"
                                for i in range(node.lineno - 1, node.end_lineno)
                            ),
                        }
    return sources


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Diagnostic artifact path escapes its run directory")
    return path


def _recordings(run_dir: Path) -> list[dict]:
    records = []
    for path in sorted((run_dir / "debug" / "calls").glob("*.json")):
        record = read_json(path)
        record["images"] = []
        for relative in record.get("image_files", []):
            image = _inside(run_dir, relative)
            if image.exists():
                record["images"].append(
                    "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode("ascii")
                )
            else:
                record["images"].append(None)
        records.append(record)
    return records


def _recorded_sources(run_dir: Path, events: list[dict], recordings: list[dict]) -> dict:
    sources = {}
    refs = [e["payload"].get("_debug_source") for e in events]
    refs += [r.get("source") for r in recordings]
    for ref in refs:
        if not ref or ref["snapshot"] in sources:
            continue
        path = _inside(run_dir, ref["snapshot"])
        if path.exists():
            sources[ref["snapshot"]] = path.read_text(encoding="utf-8")
    return sources


def build_decisions(events: list[dict], frames: list[dict], recordings: list[dict]) -> list[dict]:
    """Join delayed outputs to their source observation, never the display time."""
    by_observation = {frame["observation_seq"]: i for i, frame in enumerate(frames)}
    by_trace: dict[str, list[dict]] = {}
    for event in events:
        if event.get("trace_id"):
            by_trace.setdefault(event["trace_id"], []).append(event)
    decisions = []
    for event in events:
        payload = event["payload"]
        policy = event["event_type"] == "decision_proposed" and "producer" in payload
        monitor = event["event_type"] == "monitor"
        if not policy and not monitor:
            continue
        role = "policy" if policy else "monitor"
        seq = payload.get("source_observation_seq" if policy else "evidence_observation_seq")
        source_index = by_observation.get(seq)
        chain = by_trace.get(event.get("trace_id"), []) if policy else [event]
        controls = [e for e in chain if e["event_type"] == "control"]
        accepted = any(e["event_type"] == "decision_executed" for e in chain)
        rejected = any(e["payload"].get("rejected") for e in chain)
        candidates = [
            r
            for r in recordings
            if r.get("role") == role
            and r.get("observation_seq") == seq
            and r.get("completed_t_sim_ns") == event["t_sim_ns"]
        ]
        # Memory-based monitors may use an older evidence frame than their request
        # observation. Only accept a unique same-role/completion-time fallback.
        if not candidates:
            candidates = [
                r
                for r in recordings
                if r.get("role") == role and r.get("completed_t_sim_ns") == event["t_sim_ns"]
            ]
        recording = candidates[0] if len(candidates) == 1 else None
        inference = [
            e
            for e in events
            if e["event_type"] == "inference_call"
            and e["payload"].get("role") == role
            and e["t_sim_ns"] == event["t_sim_ns"]
        ]
        decisions.append(
            {
                "id": event.get("trace_id") or f"monitor-{event['seq']}",
                "event_seq": event["seq"],
                "role": role,
                "t": event["t_sim_ns"] / 1e9,
                "source_index": source_index,
                "source_seq": seq,
                "source_t": frames[source_index]["t"] if source_index is not None else None,
                "state": ("accepted" if accepted else "rejected" if rejected else "unresolved")
                if policy
                else payload.get("label", "unknown"),
                "payload": payload,
                "chain": [e for e in chain if e["event_type"] != "control"],
                "first_control_t": controls[0]["t_sim_ns"] / 1e9 if controls else None,
                "control_count": len(controls),
                "recording": recording,
                "inference": inference[0]["payload"] if len(inference) == 1 else None,
                "inference_link": "Unique role/completion-time match"
                if len(inference) == 1
                else "Not recorded or ambiguous",
            }
        )
    return decisions


async def load_run(run_dir: Path) -> dict:
    manifest = read_json(run_dir / "manifest.json")
    result = read_json(run_dir / "result.json")
    events = read_events(run_dir / "events.jsonl")
    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    config = EnvironmentConfig.model_validate(manifest["environment_config"])
    if config.adapter.name != "grid3d":
        raise ValueError(f"Replay supports grid3d, not {config.adapter.name}")
    if len(manifest["seeds"]) != 1:
        raise ValueError("One explicit seed is required for an exact replay")
    seed = int(manifest["seeds"][0])
    if 1 <= seed <= 40:
        raise ValueError("Held-out seeds 1-40 must not be inspected for development")
    mission = MissionSpec(
        mission_id=f"debug:{run_dir.name}",
        instruction=config.instruction,
        task_family=config.task_family,
        success=SuccessCriteria.model_validate(config.params.get("success", {})),
        constraints=MissionConstraints.model_validate(config.params.get("constraints", {})),
        allowed_skills=tuple(config.params.get("allowed_skills", ())),
    )
    params = dict(config.params)
    params.update(config.adapter.params)
    if params.get("failures") or any(e["event_type"] == "failure_injected" for e in events):
        raise ValueError("Debugger observer reconstruction does not yet support injected failures")
    params["allow_privileged"] = False
    env = DeterministicEnv(**params)
    await env.reset(mission, seed)
    scene = {
        "obstacles": [
            {"center": o.center.tolist(), "half": o.half.tolist()} for o in env.obstacles
        ],
        "landmarks": [
            {"position": lm.position.tolist(), "label": lm.label, "target": lm.is_target}
            for lm in env.landmarks
        ],
        "goal": env.goal.tolist(),
        "fence": mission.constraints.geofence_radius_m,
        "goal_radius": env.goal_radius_m,
        "fov": env.fov_deg,
    }
    controls = [e for e in events if e["event_type"] == "control"]
    if not controls:
        raise ValueError("This run has no recorded controls to replay")
    dt_ns = int(1e9 / arch.scheduler.control_hz)
    frames = []
    max_position_error = 0.0
    pose_checks = 0
    reference_checks = 0
    proposals = {
        e["payload"]["source_observation_seq"]: e["payload"]
        for e in events
        if e["event_type"] == "decision_proposed" and "source_observation_seq" in e["payload"]
    }

    def capture(obs, event=None):
        status = env.status()
        rgb = global_store().get(obs.rgb.uri) if obs.rgb else None
        payload = event["payload"] if event else {}
        return {
            "t": obs.t_sim_ns / 1e9,
            "observation_seq": obs.seq,
            "position": [obs.position.x, obs.position.y, obs.position.z],
            "yaw": obs.yaw_rad,
            "velocity": [obs.velocity.x, obs.velocity.y, obs.velocity.z],
            "distance": status.distance_to_goal_m,
            "collided": status.collided,
            "rgb": _image_uri(rgb),
            "control": payload,
            "trace_id": event.get("trace_id") if event else None,
        }

    try:
        for event in controls:
            obs = await env.observe()
            if obs.t_sim_ns != event["t_sim_ns"]:
                raise ValueError("Control timestamps disagree with replay clock")
            payload = event["payload"]
            if all(f"position_{axis}" in payload for axis in "xyz"):
                logged = np.array([payload[f"position_{a}"] for a in "xyz"])
                actual = np.array([obs.position.x, obs.position.y, obs.position.z])
                max_position_error = max(max_position_error, float(np.linalg.norm(logged - actual)))
                pose_checks += 1
                if max_position_error > 1e-7:
                    raise ValueError(f"Replay position mismatch: {max_position_error:.9g} m")
            provenance = proposals.get(obs.seq, {}).get("provenance", {})
            if provenance.get("rgb_digest"):
                if obs.rgb is None or obs.rgb.digest != provenance["rgb_digest"]:
                    raise ValueError(f"Source frame reference mismatch at observation {obs.seq}")
                reference_checks += 1
            frames.append(capture(obs, event))
            await env.step(
                ControlCommand(
                    t_sim_ns=event["t_sim_ns"],
                    velocity=Vec3(x=payload["vx"], y=payload["vy"], z=payload["vz"]),
                    yaw_rate_rps=payload["yaw_rate"],
                    frame=Frame.ENU,
                ),
                dt_ns,
            )
        final_distance = env.status().distance_to_goal_m
        frames.append(capture(await env.observe()))
    finally:
        await env.close()
    error = abs(final_distance - float(result["metrics"]["distance_to_goal_m"]))
    if not math.isfinite(error) or error > 1e-7:
        raise ValueError(f"Replay final distance mismatch: {error:.9g} m")
    recordings = _recordings(run_dir)
    decisions = build_decisions(events, frames, recordings)
    return {
        "name": run_dir.name,
        "path": str(run_dir.resolve()),
        "seed": seed,
        "architecture": arch.id,
        "instruction": config.instruction,
        "model_ids": sorted(
            {
                e["payload"].get("model_id", "unknown")
                for e in events
                if e["event_type"] == "inference_call"
            }
        ),
        "result": result,
        "scene": scene,
        "frames": frames,
        "decisions": decisions,
        "events": [
            e
            for e in events
            if e["event_type"] not in {"control", "perception", "memory_update"}
            or e["payload"].get("kind") == "adaptive_visual_plan"
        ],
        "recordings": recordings,
        "recorded_sources": _recorded_sources(run_dir, events, recordings),
        "provenance": {
            "run_commit": manifest.get("git_sha"),
            "run_dirty": manifest.get("git_dirty"),
            "max_position_error_m": max_position_error,
            "checked_positions": pose_checks,
            "final_distance_error_m": error,
            "source_reference_checks": reference_checks,
            "missing_source_frames": sum(d["source_index"] is None for d in decisions),
            "recorded_calls": len(recordings),
            "events_sha256": hashlib.sha256((run_dir / "events.jsonl").read_bytes()).hexdigest(),
            "image_status": (
                "Replay-rendered with current simulator; "
                "reference digests are pose IDs, not pixel hashes"
            ),
        },
    }


def html_document(data: dict) -> str:
    template = Path(__file__).with_name("flight_debugger.html").read_text(encoding="utf-8")
    # Run logs and model prose are untrusted. Escape script-closing characters;
    # the client renders strings with textContent, never innerHTML.
    blob = json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace(
        "<", chr(92) + "u003c"
    )
    return template.replace("/*__FLIGHT_DATA__*/null", blob)


async def export(run_dirs: list[Path], output: Path) -> dict:
    runs = []
    for run in run_dirs:
        print(f"Replaying {run.name} (no inference)", flush=True)
        runs.append(await load_run(run))
    data = {"schema": 1, "runs": runs, "sources": _sources()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_document(data), encoding="utf-8")
    summary = {
        "html": str(output.resolve()),
        "runs": [
            {
                "name": r["name"],
                "frames": len(r["frames"]),
                "decisions": len(r["decisions"]),
                **r["provenance"],
            }
            for r in runs
        ],
    }
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reports/debugger/index.html"))
    args = parser.parse_args(argv)
    print(json.dumps(asyncio.run(export(args.run_dirs, args.out)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
