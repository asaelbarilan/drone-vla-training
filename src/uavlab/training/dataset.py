"""Expert data collection and action discretisation.

The teacher is an ordinary architecture flown with the camera on; the student
sees only what any policy sees — camera frames and its own attitude — and learns
to reproduce the commands that were actually issued. Privileged teacher,
unprivileged student, which is the standard teacher/student setup and what the
drone-VLA papers that generate their own data (GRaD-Nav++, Exp2VLA) do.

Which teacher matters more than it looks. C0 reads the true goal position and so
flies toward a target that is off-camera most of the time; C2 decides from live
detections, but is *also* partly privileged relative to the student, because it
decides at 2 Hz and controls at 20 Hz and its search heading advances on a sim
clock. Both leave labels that a single frame cannot determine, which is why the
policy takes a history of frames rather than one. See CHANGES.md.

Two decisions here are measured rather than assumed, and both are recorded in
docs/SMALL_VLA_SEARCH.md:

* **Per-dimension bins, not a joint codebook.** A joint codebook over the 4-D
  action space needs exponentially many prototypes; K=1024 measured *worse* than
  16 per-dimension bins. 64 bins per dimension gives 0.068 m/s error, which is
  3 mm over a control tick.
* **Only successful episodes are kept.** Failed episodes run to the full timeout,
  so they are over-represented per sample while demonstrating precisely the
  behaviour we do not want cloned. (DAgger rollouts are the deliberate exception
  — see `training/dagger.py`.)
* **`episodes.npy` records which flight each sample came from.** Samples from
  different flights are adjacent in these arrays, so anything reading a window
  of history needs the boundaries to avoid stitching two episodes together.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.training.splits import check_collection_range

ACTION_DIMS = ("vx", "vy", "vz", "yaw_rate")
DEFAULT_BINS = 64
IMAGE_SIZE = 112
"""Frames are stored at 112x112 rather than the rendered 224x224.

Purely a disk decision: 224x224x3 uint8 is 150 kB per sample, and a useful
dataset would be tens of gigabytes. At 112 it is 37 kB. The policy is a small
convnet that would downsample anyway.
"""


@dataclass(slots=True)
class ActionCodec:
    """Per-dimension uniform binning of the 4-D action, with its own inverse."""

    low: np.ndarray
    high: np.ndarray
    bins: int = DEFAULT_BINS

    @classmethod
    def fit(cls, actions: np.ndarray, bins: int = DEFAULT_BINS, margin: float = 0.02) -> ActionCodec:
        low, high = actions.min(0), actions.max(0)
        span = np.maximum(high - low, 1e-6)
        # A small margin keeps the extreme values off the edge of the outermost
        # bin, where they would be reconstructed at half a bin width of error.
        return cls(low - span * margin, high + span * margin, bins)

    def encode(self, actions: np.ndarray) -> np.ndarray:
        """(N, 4) continuous -> (N, 4) integer bin indices."""
        scaled = (actions - self.low) / (self.high - self.low)
        return np.clip((scaled * self.bins).astype(np.int64), 0, self.bins - 1)

    def decode(self, indices: np.ndarray) -> np.ndarray:
        """(N, 4) bin indices -> (N, 4) continuous, at bin centres."""
        centres = (indices.astype(np.float64) + 0.5) / self.bins
        return self.low + centres * (self.high - self.low)

    def roundtrip_error(self, actions: np.ndarray) -> dict[str, float]:
        """What this codec costs. Report it before trusting a trained policy."""
        recovered = self.decode(self.encode(actions))
        velocity_error = np.linalg.norm(recovered[:, :3] - actions[:, :3], axis=1)
        return {
            "velocity_error_mean_mps": float(velocity_error.mean()),
            "velocity_error_p95_mps": float(np.percentile(velocity_error, 95)),
            "yaw_error_mean_rps": float(np.abs(recovered[:, 3] - actions[:, 3]).mean()),
        }

    def to_dict(self) -> dict:
        return {"low": self.low.tolist(), "high": self.high.tolist(), "bins": self.bins}

    @classmethod
    def from_dict(cls, data: dict) -> ActionCodec:
        return cls(np.array(data["low"]), np.array(data["high"]), int(data["bins"]))


def _resize(image, size: int = IMAGE_SIZE) -> np.ndarray:
    return np.asarray(image.resize((size, size)), dtype=np.uint8)


async def collect_episode(arch, env, seed: int, stride: int) -> tuple[list, list, bool]:
    """Run one expert episode, recording (frame, state) -> action pairs.

    Recording happens inside the environment's ``step``, which is the only place
    where the frame the policy saw and the command actually issued are both
    available and guaranteed to correspond.
    """
    from uavlab.adapters.gym.deterministic_env import DeterministicEnv
    from uavlab.core.frame_store import global_store

    frames: list[np.ndarray] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    terminates: list[int] = []
    original = DeterministicEnv.step
    tick = 0

    async def recording_step(self, command, dt_ns):
        nonlocal tick
        if tick % stride == 0:
            uri = f"frame://{id(self)}/rgb/{max(self._seq - 1, 0)}"
            image = global_store().get(uri)
            if image is not None:
                frames.append(_resize(image))
                v = self.vehicle.velocity
                states.append(
                    np.array(
                        [v[0], v[1], v[2], np.cos(self.vehicle.yaw), np.sin(self.vehicle.yaw)],
                        dtype=np.float32,
                    )
                )
                actions.append(
                    np.array(
                        [
                            command.velocity.x,
                            command.velocity.y,
                            command.velocity.z,
                            command.yaw_rate_rps,
                        ],
                        dtype=np.float32,
                    )
                )
                # The oracle ends a mission with a *directive*, which is not in
                # the action space. Without this label a cloned policy would fly
                # to the goal and hover there forever - reaching the target but
                # never completing the mission, which scores as failure under
                # require_terminal_stop. So terminal intent is learned as its own
                # binary output, exactly as a real VLA carries a discrete
                # terminate/gripper dimension alongside continuous motion.
                status = self.status()
                terminates.append(
                    int(status.distance_to_goal_m <= self.goal_radius_m)
                )
        tick += 1
        await original(self, command, dt_ns)

    DeterministicEnv.step = recording_step
    try:
        result = await Orchestrator(
            arch, env, EpisodeSpec(episode_id=f"expert_{seed}", seed=seed)
        ).run()
    finally:
        DeterministicEnv.step = original

    return (
        list(zip(frames, states, strict=True)),
        list(zip(actions, terminates, strict=True)),
        bool(result.success),
    )


def collect(
    out_dir: Path,
    episodes: int = 200,
    env_name: str = "grid_nav_vision",
    expert: str = "c0",
    stride: int = 2,
    start_seed: int = 1000,
    keep_failures: bool = False,
    config_root: Path | None = None,
    progress: bool = True,
) -> dict:
    """Generate an expert dataset. Returns a manifest describing it."""
    check_collection_range(start_seed, episodes)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    arch = load_architecture(expert, config_root)
    env = load_environment(env_name, config_root)

    all_frames: list[np.ndarray] = []
    all_states: list[np.ndarray] = []
    all_actions: list[np.ndarray] = []
    all_terminates: list[int] = []
    all_episodes: list[int] = []
    kept = skipped = 0

    for i in range(episodes):
        seed = start_seed + i
        pairs, actions, success = asyncio.run(collect_episode(arch, env, seed, stride))
        if not success and not keep_failures:
            skipped += 1
            continue
        kept += 1
        for (frame, state), (action, terminate) in zip(pairs, actions, strict=True):
            all_frames.append(frame)
            all_states.append(state)
            all_actions.append(action)
            all_terminates.append(terminate)
            all_episodes.append(kept - 1)
        if progress and (i + 1) % 25 == 0:
            print(
                f"  {i + 1}/{episodes} episodes  kept={kept} skipped={skipped} "
                f"samples={len(all_frames)}",
                flush=True,
            )

    if not all_frames:
        raise RuntimeError(
            "the expert produced no successful episodes; check that the oracle "
            "still passes `uavlab verify c0` before collecting"
        )

    frames = np.stack(all_frames)
    states = np.stack(all_states)
    actions = np.stack(all_actions)
    terminates = np.array(all_terminates, dtype=np.int64)
    episodes_index = np.array(all_episodes, dtype=np.int64)

    np.save(out_dir / "episodes.npy", episodes_index)
    np.save(out_dir / "frames.npy", frames)
    np.save(out_dir / "states.npy", states)
    np.save(out_dir / "actions.npy", actions)
    np.save(out_dir / "terminates.npy", terminates)

    codec = ActionCodec.fit(actions)
    manifest = {
        "expert": expert,
        "environment": env_name,
        "episodes_requested": episodes,
        "episodes_kept": kept,
        "episodes_skipped_as_failures": skipped,
        "samples": int(len(frames)),
        "stride": stride,
        "image_size": IMAGE_SIZE,
        "seeds": [start_seed, start_seed + episodes - 1],
        "codec": codec.to_dict(),
        "codec_error": codec.roundtrip_error(actions),
        "action_dims": list(ACTION_DIMS),
        "frames_bytes": int(frames.nbytes),
        "terminate_positive_rate": float(terminates.mean()),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load(data_dir: Path):
    """-> frames, states, actions, terminates, episodes, codec, manifest.

    ``episodes`` is the episode index of each sample, and is ``None`` for a
    dataset collected before it was recorded. Anything that stacks frames over
    time must refuse to run without it rather than guess: samples from different
    flights sit next to each other in these arrays, so stacking across a boundary
    would silently feed the network the end of one episode as the history of
    another.
    """
    data_dir = Path(data_dir)
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    frames = np.load(data_dir / "frames.npy", mmap_mode="r")
    states = np.load(data_dir / "states.npy")
    actions = np.load(data_dir / "actions.npy")
    terminates = np.load(data_dir / "terminates.npy")
    episode_path = data_dir / "episodes.npy"
    episodes = np.load(episode_path) if episode_path.is_file() else None
    return (
        frames, states, actions, terminates, episodes,
        ActionCodec.from_dict(manifest["codec"]), manifest,
    )
