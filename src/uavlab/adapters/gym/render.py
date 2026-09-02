"""A minimal rasteriser for the deterministic environment.

Why this has to exist
---------------------
Every architecture in this study that is named after a vision model needs
pixels, and until now nothing in this repository produced any. The environment
handed perception a list of labelled 3-D positions filtered by field of view,
which meant the "detector" was doing geometry, not seeing. A real VLM or VLA
plugged into that would have had nothing to look at.

So this renders the box world from the vehicle's camera: a pinhole projection,
painter's algorithm, flat shading by distance. It is crude on purpose — no
lighting, no texture, no anti-aliasing. It exists to give a vision model a real
image whose content is a true function of the vehicle's pose and the scene, so
that "the model found the target" is a claim about the model rather than about a
privileged data channel.

Deliberately *not* photorealistic. An architecture that only works on these
flat-shaded boxes has not been validated for the real world; that is what the
Project AirSim adapter is for. What this does buy is the ability to run a real
VLM in the loop, on a laptop, deterministically, at screening speed.
"""

from __future__ import annotations

import math

import numpy as np

# Re-exported: the geometry is shared with every adapter and policy; the
# rasteriser below is specific to this one.
from uavlab.core.camera import Camera

SKY_TOP = (96, 148, 210)
SKY_BOTTOM = (176, 202, 232)
GROUND = (104, 112, 96)
TARGET_COLOR = (206, 44, 44)
LURE_COLOR = (188, 96, 60)
DISTRACTOR_COLOR = (86, 132, 96)
OBSTACLE_BASE = (128, 128, 134)


def _box_corners(center: np.ndarray, half: np.ndarray) -> np.ndarray:
    signs = np.array(
        [
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
            [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
        ],
        dtype=float,
    )
    return center + signs * half


def _shade(
    base: tuple[int, int, int], depth: float, max_depth: float = 45.0
) -> tuple[int, int, int]:
    """Flat distance fog, so depth is legible to a vision model."""
    t = float(np.clip(depth / max_depth, 0.0, 1.0))
    return tuple(int(c * (1.0 - 0.65 * t) + 190 * 0.65 * t) for c in base)


def render_frame(
    position: np.ndarray,
    yaw: float,
    obstacles: list,
    landmarks: list,
    target_label: str,
    camera: Camera | None = None,
    visible_labels: set[str] | None = None,
):
    """Render one RGB frame. Returns a PIL Image.

    ``visible_labels`` restricts which landmarks may be drawn, so the renderer
    honours exactly the same occlusion and dropout rules the sensor model
    applies. Without that, a scheduled sensor dropout would still be visible in
    the image and the model would legitimately see what the architecture was
    supposed to have lost.
    """
    from PIL import Image, ImageDraw

    cam = camera or Camera()
    image = Image.new("RGB", (cam.width, cam.height), SKY_BOTTOM)
    draw = ImageDraw.Draw(image)

    # Sky gradient then ground plane, giving the model a horizon to orient by.
    for y in range(cam.height // 2):
        t = y / max(cam.height // 2 - 1, 1)
        colour = tuple(int(SKY_TOP[i] * (1 - t) + SKY_BOTTOM[i] * t) for i in range(3))
        draw.line([(0, y), (cam.width, y)], fill=colour)

    horizon_v = cam.height / 2.0 + cam.focal_px * math.tan(cam.pitch_rad)
    horizon_v += cam.focal_px * (position[2] / 60.0)  # altitude shifts the horizon
    draw.rectangle([0, max(0, int(horizon_v)), cam.width, cam.height], fill=GROUND)

    # Painter's algorithm: far things first.
    drawables: list[tuple[float, str, object]] = []
    for obstacle in obstacles:
        distance = float(np.linalg.norm(obstacle.center - position))
        drawables.append((distance, "box", obstacle))
    for mark in landmarks:
        if visible_labels is not None and mark.label not in visible_labels:
            continue
        distance = float(np.linalg.norm(mark.position - position))
        drawables.append((distance, "mark", mark))
    drawables.sort(key=lambda item: -item[0])

    for distance, kind, item in drawables:
        if distance > 90.0:
            continue
        if kind == "box":
            corners = _box_corners(item.center, item.half)
            pixels, depth = cam.project(corners, position, yaw)
            if (depth <= 0.2).all():
                continue
            keep = depth > 0.2
            if keep.sum() < 3:
                continue
            pts = pixels[keep]
            hull = _convex_hull([(float(x), float(y)) for x, y in pts])
            if len(hull) >= 3:
                draw.polygon(hull, fill=_shade(OBSTACLE_BASE, distance),
                             outline=_shade((70, 70, 76), distance))
        else:
            centre = np.array([item.position])
            pixels, depth = cam.project(centre, position, yaw)
            if depth[0] <= 0.2:
                continue
            u, v = float(pixels[0][0]), float(pixels[0][1])
            radius = max(2.0, cam.focal_px * 1.6 / max(depth[0], 1e-3))
            if item.label == target_label:
                colour = LURE_COLOR if getattr(item, "is_lure", False) else TARGET_COLOR
            else:
                colour = DISTRACTOR_COLOR
            # A tower, not a dot: gives the model a shape with vertical extent.
            draw.rectangle(
                [u - radius * 0.55, v - radius * 2.2, u + radius * 0.55, v + radius * 0.9],
                fill=_shade(colour, distance),
                outline=_shade((40, 20, 20), distance),
            )
    return image


def render_depth_frame(
    position: np.ndarray,
    yaw: float,
    obstacles: list,
    landmarks: list,
    target_label: str,
    camera: Camera | None = None,
    visible_labels: set[str] | None = None,
) -> np.ndarray:
    """Render calibrated camera-forward depth in metres.

    This is a geometric sensor channel, not a semantic mask. Obstacles and all
    admitted landmarks write depth; the VLM must still supply the target pixel.
    Pixels with no rendered surface are ``inf``.
    """
    from PIL import Image, ImageDraw

    cam = camera or Camera()
    depth_image = Image.new("F", (cam.width, cam.height), float("inf"))
    draw = ImageDraw.Draw(depth_image)

    drawables: list[tuple[float, str, object]] = []
    for obstacle in obstacles:
        distance = float(np.linalg.norm(obstacle.center - position))
        drawables.append((distance, "box", obstacle))
    for mark in landmarks:
        if visible_labels is not None and mark.label not in visible_labels:
            continue
        distance = float(np.linalg.norm(mark.position - position))
        drawables.append((distance, "mark", mark))
    drawables.sort(key=lambda item: -item[0])

    for distance, kind, item in drawables:
        if distance > 90.0:
            continue
        if kind == "box":
            corners = _box_corners(item.center, item.half)
            pixels, depths = cam.project(corners, position, yaw)
            keep = depths > 0.2
            if keep.sum() < 3:
                continue
            hull = _convex_hull(
                [(float(x), float(y)) for x, y in pixels[keep]]
            )
            if len(hull) >= 3:
                draw.polygon(hull, fill=float(np.min(depths[keep])))
        else:
            pixels, depths = cam.project(np.array([item.position]), position, yaw)
            if depths[0] <= 0.2:
                continue
            u, v = float(pixels[0, 0]), float(pixels[0, 1])
            radius = max(2.0, cam.focal_px * 1.6 / max(depths[0], 1e-3))
            draw.rectangle(
                [u - radius * 0.55, v - radius * 2.2, u + radius * 0.55, v + radius * 0.9],
                fill=float(depths[0]),
            )
    return np.asarray(depth_image, dtype=np.float32)


def render_down_frame(
    position: np.ndarray,
    yaw: float,
    obstacles: list,
    landmarks: list,
    target_label: str,
    camera: Camera | None = None,
    visible_labels: set[str] | None = None,
):
    """Render a nadir RGB camera for dual-view direct-action policies.

    Landmarks are painted at their ground footprint while the navigation goal
    remains an above-object 3-D pose. That is the physical distinction a down
    camera sees during an approach: the object is on the ground and the scored
    vehicle pose is safely above it.
    """
    from PIL import Image, ImageDraw

    cam = camera or Camera(pitch_rad=-math.pi / 2.0)
    image = Image.new("RGB", (cam.width, cam.height), GROUND)
    draw = ImageDraw.Draw(image)

    drawables: list[tuple[float, str, object]] = []
    for obstacle in obstacles:
        drawables.append((float(np.linalg.norm(obstacle.center - position)), "box", obstacle))
    for mark in landmarks:
        if visible_labels is not None and mark.label not in visible_labels:
            continue
        drawables.append((float(np.linalg.norm(mark.position - position)), "mark", mark))
    drawables.sort(key=lambda item: -item[0])

    for distance, kind, item in drawables:
        if kind == "box":
            corners = _box_corners(item.center, item.half)
            pixels, depths = cam.project(corners, position, yaw)
            keep = depths > 0.2
            if keep.sum() < 3:
                continue
            hull = _convex_hull([(float(x), float(y)) for x, y in pixels[keep]])
            if len(hull) >= 3:
                draw.polygon(
                    hull,
                    fill=_shade(OBSTACLE_BASE, distance),
                    outline=_shade((70, 70, 76), distance),
                )
            continue

        ground_point = np.array([[item.position[0], item.position[1], 0.0]], dtype=float)
        pixels, depths = cam.project(ground_point, position, yaw)
        if depths[0] <= 0.2:
            continue
        u, v = float(pixels[0, 0]), float(pixels[0, 1])
        radius = max(3.0, cam.focal_px * 1.3 / max(depths[0], 1e-3))
        if item.label == target_label:
            colour = LURE_COLOR if getattr(item, "is_lure", False) else TARGET_COLOR
        else:
            colour = DISTRACTOR_COLOR
        draw.ellipse(
            [u - radius, v - radius, u + radius, v + radius],
            fill=_shade(colour, distance),
            outline=_shade((40, 20, 20), distance),
        )
    return image


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Monotone chain. Boxes project to convex silhouettes, so this is exact."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]
