"""Scene-replay adapter: the same dynamics, a scene loaded from data.

This is the second *working* environment adapter, and it exists to keep the
adapter boundary honest.  A boundary with only one implementation behind it is
an assumption, not an interface: the same architecture YAML must run here with
nothing changed but the environment config, and if it ever cannot, the leak is
visible immediately rather than at PX4-integration time.

It also makes scenes reproducible independently of the generator.  A seeded
procedural scene is only reproducible while the generator is unchanged; a scene
file stays fixed across refactors, which is what a benchmark needs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from uavlab.adapters.gym.deterministic_env import DeterministicEnv, Landmark, Obstacle
from uavlab.contracts import MissionSpec, ObservationPacket
from uavlab.core.registry import register


@register("environment", "scene_replay")
class SceneReplayEnv(DeterministicEnv):
    """Deterministic dynamics over a scene read from a JSON file.

    Scene schema::

        {
          "start":     [x, y, z],
          "goal":      [x, y, z],
          "obstacles": [{"center": [x,y,z], "half": [hx,hy,hz], "label": "wall"}],
          "landmarks": [{"position": [x,y,z], "label": "target",
                         "is_target": true, "is_lure": false}],
          "subgoals":  [[x, y, z]]
        }
    """

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        self.scene_path = params.get("scene_path")
        if self.scene_path is None:
            raise ValueError(
                "scene_replay requires a 'scene_path' parameter pointing at a scene JSON file"
            )
        self._scene = self._load(Path(self.scene_path))

    @property
    def name(self) -> str:
        return "scene_replay"

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"scene file not found: {path}")
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        for key in ("start", "goal"):
            if key not in data:
                raise ValueError(f"scene file {path} is missing required key {key!r}")
        return data

    async def reset(self, mission: MissionSpec, seed: int) -> ObservationPacket:
        # The seed still drives detection noise, so repeated episodes on a fixed
        # scene remain statistically meaningful without changing the geometry.
        packet = await super().reset(mission, seed)

        scene = self._scene
        start = np.array(scene["start"], dtype=float)
        self.goal = np.array(scene["goal"], dtype=float)
        self._start = start.copy()
        self._shortest = float(np.linalg.norm(self.goal - start))
        self.vehicle.position = start.copy()
        self.vehicle.velocity = np.zeros(3)
        self.vehicle.yaw = float(
            np.arctan2(self.goal[1] - start[1], self.goal[0] - start[0])
        )

        self.obstacles = [
            Obstacle(
                center=np.array(o["center"], dtype=float),
                half=np.array(o["half"], dtype=float),
                label=str(o.get("label", "obstacle")),
            )
            for o in scene.get("obstacles", [])
        ]
        self.landmarks = [
            Landmark(
                position=np.array(m["position"], dtype=float),
                label=str(m.get("label", self.target_label)),
                is_target=bool(m.get("is_target", False)),
                is_lure=bool(m.get("is_lure", False)),
            )
            for m in scene.get("landmarks", [])
        ]
        if not any(m.is_target for m in self.landmarks):
            self.landmarks.append(
                Landmark(position=self.goal.copy(), label=self.target_label, is_target=True)
            )
        self.subgoals = [np.array(s, dtype=float) for s in scene.get("subgoals", [])]

        self._rebuild_obstacle_arrays()
        self._fan_cache = None
        self._fan_cache_seq = -1
        self._last_hits = ()
        self._seq = 0
        return await self.observe()


def write_scene(env: DeterministicEnv, path: Path) -> Path:
    """Freeze a procedurally generated scene into a replayable file.

    Used to promote an interesting seed — one that exposed a failure — into a
    fixed benchmark case that survives changes to the scene generator.
    """
    scene = {
        "start": [float(v) for v in env._start],
        "goal": [float(v) for v in env.goal],
        "obstacles": [
            {
                "center": [float(v) for v in o.center],
                "half": [float(v) for v in o.half],
                "label": o.label,
            }
            for o in env.obstacles
        ],
        "landmarks": [
            {
                "position": [float(v) for v in m.position],
                "label": m.label,
                "is_target": m.is_target,
                "is_lure": m.is_lure,
            }
            for m in env.landmarks
        ],
        "subgoals": [[float(v) for v in s] for s in env.subgoals],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scene, indent=2), encoding="utf-8")
    return path
