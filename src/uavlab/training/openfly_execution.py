"""OpenFly released evaluator's pose contract, separate from its token codebook.

Coordinates are source-world x/y/z-up, yaw radians counterclockwise from +x.
AirSim uses metres; reconstructed scenes need their separately verified scale.
This is kinematic navigation, not a velocity controller or flight dynamics model.
"""

import math
from itertools import pairwise
from numbers import Integral

ACTION_NAMES = (
    "STOP",
    "forward 3",
    "yaw left 30 deg",
    "yaw right 30 deg",
    "up 3",
    "down 3",
    "left 3",
    "right 3",
    "forward 6",
    "forward 9",
)


def checked_pose(pose):
    if len(pose) != 4 or not all(math.isfinite(x) for x in pose):
        raise ValueError("Expected finite [x, y, z, yaw_radians]")
    return tuple(float(x) for x in pose)


def advance_pose(pose, action_id):
    """Apply a validated native ID. Unsupported outputs never become STOP."""
    x, y, z, yaw = checked_pose(pose)
    if (
        isinstance(action_id, bool)
        or not isinstance(action_id, Integral)
        or not 0 <= action_id <= 9
    ):
        raise ValueError("Expected native action ID 0..9; invalid output is a failure")
    if action_id in (1, 8, 9):
        distance = {1: 3.0, 8: 6.0, 9: 9.0}[action_id]
        x += distance * math.cos(yaw)
        y += distance * math.sin(yaw)
    elif action_id in (2, 3):
        yaw += math.radians(30) * (1 if action_id == 2 else -1)
    elif action_id in (4, 5):
        z += 3.0 * (1 if action_id == 4 else -1)
    elif action_id in (6, 7):
        side = 1 if action_id == 6 else -1
        x -= side * 3.0 * math.sin(yaw)
        y += side * 3.0 * math.cos(yaw)
    return (x, y, z, (yaw + math.pi) % (2 * math.pi) - math.pi)


def airsim_pose_components(pose):
    """Match eval.py set_camera_pose: reflect world y/z and yaw, keep x."""
    x, y, z, yaw = checked_pose(pose)
    return (x, -y, -z, -yaw)


def navigation_metrics(poses, goal, termination, goal_radius=20.0):
    """Strict diagnostic metrics, NOT a reproduction of published benchmark SPL.

    Log legacy endpoint-only success separately: eval.py can count timeout/error
    near a goal as success. No collision-safety claim follows from these metrics.
    """
    allowed = {
        "stop",
        "timeout",
        "invalid_model_output",
        "invalid_data_label",
        "renderer_error",
        "collision",
    }
    if termination not in allowed:
        raise ValueError("Unknown termination reason")
    points = [checked_pose(p)[:3] for p in poses]
    if not points or len(goal) != 3 or not all(math.isfinite(x) for x in goal):
        raise ValueError("Need at least one pose and a finite 3D goal")
    if not math.isfinite(goal_radius) or goal_radius <= 0:
        raise ValueError("Goal radius must be positive")
    distances = [math.dist(p, goal) for p in points]
    path_length = sum(math.dist(a, b) for a, b in pairwise(points))
    endpoint_success = distances[-1] < goal_radius
    success = termination == "stop" and endpoint_success
    return {
        "termination": termination,
        "success_with_stop": success,
        "oracle_goal_reached": min(distances) < goal_radius,
        "final_distance": distances[-1],
        "closest_distance": min(distances),
        "path_length": path_length,
        "legacy_endpoint_success": endpoint_success,
        "collision_status": "detected" if termination == "collision" else "not_measured",
    }
