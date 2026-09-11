"""Exact-replay error analysis for one completed OnFly local-sim run.

Simulator truth is used only after the run to score visibility and pixel error;
it is never exposed to the architecture. Logged controls must reproduce the
stored final distance exactly or the report is rejected as inadmissible.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import math
from itertools import pairwise
from pathlib import Path

import numpy as np

from uavlab.contracts import ControlCommand, Frame, Vec3
from uavlab.core.camera import Camera
from uavlab.core.config import ArchitectureConfig, EnvironmentConfig, EpisodeSpec
from uavlab.core.frame_store import global_store
from uavlab.core.orchestrator import Orchestrator


def _events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _red_bbox(image) -> tuple[int, int, int, int] | None:
    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    mask = (rgb[..., 0] > 160) & (rgb[..., 0] > rgb[..., 1] + 30) & (rgb[..., 0] > rgb[..., 2] + 30)
    ys, xs = np.nonzero(mask)
    if not xs.size:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _wrap_angle(angle: float) -> float:
    """Wrap one angle to (-pi, pi] for offline bearing-error scoring."""
    return math.atan2(math.sin(angle), math.cos(angle))


def _monitor_source_index(events: list[dict]) -> dict[int, list[dict]]:
    """Never score a delayed visual answer against its completion-time frame."""
    index: dict[int, list[dict]] = {}
    for event in events:
        seq = event["payload"].get("evidence_observation_seq")
        if type(seq) is int:
            index.setdefault(seq, []).append(event)
    return index


async def analyze(run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    events = _events(run_dir / "events.jsonl")
    decisions = [
        event
        for event in events
        if event["event_type"] == "decision_proposed"
        and event["payload"].get("producer") == "onfly_decision"
    ]
    by_observation = {int(event["payload"]["source_observation_seq"]): event for event in decisions}
    monitor_events = [event for event in events if event["event_type"] == "monitor"]
    monitors_by_observation = _monitor_source_index(monitor_events)

    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    env_cfg = EnvironmentConfig.model_validate(manifest["environment_config"])
    seed = int(manifest["seeds"][0])
    harness = Orchestrator(arch, env_cfg, EpisodeSpec(episode_id="onfly_analysis", seed=seed))
    params = dict(env_cfg.params)
    params.update(env_cfg.adapter.params)
    params["allow_privileged"] = False
    params["failures"] = []
    env = harness.registry.build("environment", env_cfg.adapter.name, params)
    await env.reset(harness.mission, seed)

    rows: list[dict] = []
    monitor_rows: list[dict] = []
    image_width: int | None = None
    image_height: int | None = None
    controls = [event for event in events if event["event_type"] == "control"]
    replay_pose_by_time: dict[int, tuple[np.ndarray, float]] = {}
    for event in controls:
        observation = await env.observe()
        replay_pose_by_time[int(event["t_sim_ns"])] = (
            np.array(
                [
                    observation.position.x,
                    observation.position.y,
                    observation.position.z,
                ],
                dtype=float,
            ),
            observation.yaw_rad,
        )
        status = env.status()
        current_image = (
            global_store().get(observation.rgb.uri) if observation.rgb is not None else None
        )
        current_bbox = _red_bbox(current_image) if current_image is not None else None
        for monitor_event in monitors_by_observation.get(observation.seq, []):
            evidence = str(monitor_event["payload"].get("evidence", ""))
            declared_latest = None
            if "latest_visible=True" in evidence:
                declared_latest = True
            elif "latest_visible=False" in evidence:
                declared_latest = False
            monitor_rows.append(
                {
                    "t_sim_s": event["t_sim_ns"] / 1e9,
                    "observation_seq": observation.seq,
                    "activation_t_sim_s": monitor_event["t_sim_ns"] / 1e9,
                    "comparison_frame": "source_observation",
                    "distance_to_goal_m": status.distance_to_goal_m,
                    "label": str(monitor_event["payload"]["label"]),
                    "declared_latest_visible": declared_latest,
                    "target_visible": current_bbox is not None,
                    "latest_visibility_correct": (
                        declared_latest == (current_bbox is not None)
                        if declared_latest is not None
                        else None
                    ),
                    "evidence": evidence,
                }
            )
        decision = by_observation.get(observation.seq)
        if decision is not None and observation.rgb is not None:
            provenance = decision["payload"]["provenance"]
            predicted_u = float(provenance["pixel_u"])
            predicted_v = float(provenance["pixel_v"])
            goal_delta = env.goal - np.array(
                [
                    observation.position.x,
                    observation.position.y,
                    observation.position.z,
                ],
                dtype=float,
            )
            goal_world_bearing = math.atan2(float(goal_delta[1]), float(goal_delta[0]))
            goal_relative_bearing = _wrap_angle(goal_world_bearing - observation.yaw_rad)
            intrinsics = observation.intrinsics
            if intrinsics is None:
                raise RuntimeError("OnFly analysis requires camera intrinsics")
            image_width = intrinsics.width
            image_height = intrinsics.height
            camera = Camera(
                width=intrinsics.width,
                height=intrinsics.height,
                fov_deg=math.degrees(2.0 * math.atan(intrinsics.width / (2.0 * intrinsics.fx))),
                pitch_rad=float(provenance.get("camera_pitch_rad", -0.15)),
            )
            predicted_ray = camera.ray_world(predicted_u, predicted_v, observation.yaw_rad)
            predicted_world_bearing = math.atan2(float(predicted_ray[1]), float(predicted_ray[0]))
            predicted_relative_bearing = _wrap_angle(predicted_world_bearing - observation.yaw_rad)
            bearing_error = _wrap_angle(predicted_relative_bearing - goal_relative_bearing)
            row = {
                "observation_seq": observation.seq,
                "t_sim_s": event["t_sim_ns"] / 1e9,
                "distance_to_goal_m": status.distance_to_goal_m,
                "predicted_pixel": [
                    predicted_u,
                    predicted_v,
                ],
                "goal_relative_bearing_deg": math.degrees(goal_relative_bearing),
                "predicted_relative_bearing_deg": math.degrees(predicted_relative_bearing),
                "goal_bearing_error_deg": math.degrees(bearing_error),
                "goal_inside_horizontal_fov": abs(goal_relative_bearing) <= math.radians(45.0),
                "sampled_depth_m": float(provenance["sampled_depth_m"]),
                "gated_range_m": float(provenance["gated_range_m"]),
                "history_pixel": provenance.get("history_pixel"),
                "decision_activation_t_sim_s": int(decision["t_sim_ns"]) / 1e9,
            }
            bbox = current_bbox
            row["target_visible"] = bbox is not None
            if bbox is not None:
                x0, y0, x1, y1 = bbox
                truth = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
                row["truth_pixel"] = list(truth)
                row["pixel_error"] = math.hypot(
                    row["predicted_pixel"][0] - truth[0],
                    row["predicted_pixel"][1] - truth[1],
                )
            rows.append(row)

        payload = event["payload"]
        await env.step(
            ControlCommand(
                t_sim_ns=int(event["t_sim_ns"]),
                velocity=Vec3(
                    x=float(payload["vx"]),
                    y=float(payload["vy"]),
                    z=float(payload["vz"]),
                ),
                yaw_rate_rps=float(payload["yaw_rate"]),
                frame=Frame.ENU,
            ),
            50_000_000,
        )

    replay_status = env.status()
    await env.close()
    stored_distance = float(result["metrics"]["distance_to_goal_m"])
    replay_error = abs(replay_status.distance_to_goal_m - stored_distance)
    if replay_error > 1e-9:
        raise RuntimeError(f"exact replay failed: final distance error {replay_error}")

    visible = [row for row in rows if row["target_visible"]]
    errors = [float(row["pixel_error"]) for row in visible]
    # Quantify how far the vehicle moves while the source-frame point is being
    # produced. OnFly's waypoint is a world point lifted from the capture pose;
    # with a short hop and a slow model it can already be behind the vehicle by
    # the time the asynchronous decision becomes authoritative.
    for row in rows:
        decision = by_observation[int(row["observation_seq"])]
        provenance = decision["payload"]["provenance"]
        activation = replay_pose_by_time.get(int(decision["t_sim_ns"]))
        if activation is None:
            continue
        source_position = np.array(
            [
                float(provenance["source_position_x"]),
                float(provenance["source_position_y"]),
                float(provenance["source_position_z"]),
            ],
            dtype=float,
        )
        source_yaw = float(provenance["source_yaw_rad"])
        source_camera = Camera(
            width=int(image_width or 224),
            height=int(image_height or 224),
            fov_deg=90.0,
            pitch_rad=float(provenance.get("camera_pitch_rad", -0.15)),
        )
        waypoint = source_camera.unproject(
            float(provenance["pixel_u"]),
            float(provenance["pixel_v"]),
            float(provenance["gated_range_m"]),
            source_position,
            source_yaw,
        )
        activation_position, activation_yaw = activation
        waypoint_delta = waypoint - activation_position
        waypoint_world_bearing = math.atan2(float(waypoint_delta[1]), float(waypoint_delta[0]))
        waypoint_relative_bearing = _wrap_angle(waypoint_world_bearing - activation_yaw)
        row["source_motion_before_activation_m"] = float(
            np.linalg.norm(activation_position - source_position)
        )
        row["waypoint_distance_at_activation_m"] = float(np.linalg.norm(waypoint_delta))
        row["waypoint_relative_bearing_at_activation_deg"] = math.degrees(waypoint_relative_bearing)
        row["waypoint_behind_at_activation"] = abs(waypoint_relative_bearing) > math.pi / 2.0
    for current, following in pairwise(rows):
        current["distance_change_to_next_decision_m"] = (
            following["distance_to_goal_m"] - current["distance_to_goal_m"]
        )
    if rows:
        rows[-1]["distance_change_to_next_decision_m"] = None
    closest = min(rows, key=lambda row: row["distance_to_goal_m"])
    closest_index = rows.index(closest)
    before_closest = rows[: closest_index + 1]
    after_closest = rows[closest_index + 1 :]

    def _bearing_summary(sample: list[dict]) -> dict:
        if not sample:
            return {
                "decisions": 0,
                "mean_abs_goal_bearing_error_deg": None,
                "goal_facing_fraction_22_5deg": None,
                "mean_distance_change_to_next_decision_m": None,
            }
        distance_changes = [
            float(row["distance_change_to_next_decision_m"])
            for row in sample
            if row.get("distance_change_to_next_decision_m") is not None
        ]
        absolute_errors = [abs(float(row["goal_bearing_error_deg"])) for row in sample]
        return {
            "decisions": len(sample),
            "mean_abs_goal_bearing_error_deg": float(np.mean(absolute_errors)),
            "goal_facing_fraction_22_5deg": sum(error <= 22.5 for error in absolute_errors)
            / len(absolute_errors),
            "mean_distance_change_to_next_decision_m": (
                float(np.mean(distance_changes)) if distance_changes else None
            ),
        }

    def _output_saturation(sample: list[dict]) -> dict:
        if not sample or image_width is None or image_height is None:
            return {
                "decisions": 0,
                "edge_fraction_1px": None,
                "corner_fraction_1px": None,
                "consecutive_repeat_fraction": None,
            }
        horizontal_edge = [
            row["predicted_pixel"][0] <= 1.0 or row["predicted_pixel"][0] >= image_width - 2.0
            for row in sample
        ]
        vertical_edge = [
            row["predicted_pixel"][1] <= 1.0 or row["predicted_pixel"][1] >= image_height - 2.0
            for row in sample
        ]
        repeats = sum(
            current["predicted_pixel"] == following["predicted_pixel"]
            for current, following in pairwise(sample)
        )
        return {
            "decisions": len(sample),
            "edge_fraction_1px": sum(
                horizontal or vertical
                for horizontal, vertical in zip(horizontal_edge, vertical_edge, strict=True)
            )
            / len(sample),
            "corner_fraction_1px": sum(
                horizontal and vertical
                for horizontal, vertical in zip(horizontal_edge, vertical_edge, strict=True)
            )
            / len(sample),
            "consecutive_repeat_fraction": (
                repeats / (len(sample) - 1) if len(sample) > 1 else 0.0
            ),
        }

    labels: dict[str, int] = {}
    for event in monitor_events:
        label = str(event["payload"]["label"])
        labels[label] = labels.get(label, 0) + 1
    scored_monitor_rows = [
        row for row in monitor_rows if row["latest_visibility_correct"] is not None
    ]
    monitor_visibility_correct = sum(
        bool(row["latest_visibility_correct"]) for row in scored_monitor_rows
    )
    false_lost_while_visible = sum(
        row["label"] == "lost" and row["target_visible"] for row in monitor_rows
    )
    missed_loss_while_absent = sum(
        row["label"] == "continue" and not row["target_visible"] for row in monitor_rows
    )
    execution_rows = [row for row in rows if "source_motion_before_activation_m" in row]
    source_motion = [float(row["source_motion_before_activation_m"]) for row in execution_rows]
    activation_waypoint_distance = [
        float(row["waypoint_distance_at_activation_m"]) for row in execution_rows
    ]

    history_distances = []
    for row in rows:
        marker = ast.literal_eval(row["history_pixel"])
        if marker is not None:
            history_distances.append(math.dist(marker, row["predicted_pixel"]))

    return {
        "previous_waypoint_echo": {
            "comparisons": len(history_distances),
            "within_one_pixel": sum(distance < 1.0 for distance in history_distances),
            "within_three_pixels": sum(distance < 3.0 for distance in history_distances),
        },
        "run": run_dir.as_posix(),
        "architecture": result["architecture_id"],
        "seed": result["seed"],
        "success": result["success"],
        "stored_final_distance_m": stored_distance,
        "replay_final_distance_m": replay_status.distance_to_goal_m,
        "replay_distance_error_m": replay_error,
        "decision_frames": len(rows),
        "visible_decision_frames": len(visible),
        "visible_fraction": len(visible) / len(rows) if rows else 0.0,
        "first_visible": visible[0] if visible else None,
        "last_visible": visible[-1] if visible else None,
        "visible_pixel_error_mean": float(np.mean(errors)) if errors else None,
        "visible_pixel_error_median": float(np.median(errors)) if errors else None,
        "visible_pixel_error_max": float(np.max(errors)) if errors else None,
        "closest_approach": closest,
        "bearing_alignment_all": _bearing_summary(rows),
        "bearing_alignment_through_closest": _bearing_summary(before_closest),
        "bearing_alignment_after_closest": _bearing_summary(after_closest),
        "output_saturation_all": _output_saturation(rows),
        "output_saturation_after_closest": _output_saturation(after_closest),
        "async_execution_geometry": {
            "decisions_scored": len(execution_rows),
            "source_motion_before_activation_mean_m": (
                float(np.mean(source_motion)) if source_motion else None
            ),
            "source_motion_before_activation_max_m": (
                float(np.max(source_motion)) if source_motion else None
            ),
            "waypoint_distance_at_activation_mean_m": (
                float(np.mean(activation_waypoint_distance))
                if activation_waypoint_distance
                else None
            ),
            "waypoint_behind_at_activation_fraction": (
                sum(bool(row["waypoint_behind_at_activation"]) for row in execution_rows)
                / len(execution_rows)
                if execution_rows
                else None
            ),
        },
        "monitor_labels": labels,
        "monitor_visibility_scored": len(scored_monitor_rows),
        "monitor_visibility_accuracy": (
            monitor_visibility_correct / len(scored_monitor_rows) if scored_monitor_rows else None
        ),
        "monitor_false_lost_while_target_visible": false_lost_while_visible,
        "monitor_continue_while_target_absent": missed_loss_while_absent,
        "monitor_rows": monitor_rows,
        "monitor_source_frames_unmatched": len(monitor_events) - len(monitor_rows),
        "rows": rows,
        "truth_scope": "offline scoring only; not exposed to the architecture",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(analyze(args.run_dir))
    text = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
