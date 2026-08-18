"""DAgger: label the states the student actually reaches.

Plain behaviour cloning failed here in the most literal way available. The
student drove into an obstacle, the shield held it there, the view stopped
changing, and because the view stopped changing it re-emitted the same command
for the rest of the episode — position frozen for fifteen seconds, command
bit-identical across hundreds of decisions. C2 never sits pressed against a wall,
so no training frame resembles that state, so the network's output there was
arbitrary; arbitrary happened to be constant.

No amount of extra C2 flying fixes that, because the missing states are exactly
the ones C2 does not visit. DAgger (Ross et al. 2011) is the standard remedy and
targets this failure precisely: let the student drive, ask the teacher what *it*
would have commanded at each state the student reached, and train on those pairs.
The stuck-against-a-wall state gets labelled "back off and go around" instead of
being absent.

Implementation note worth understanding before changing anything here. The
teacher is a full architecture — policy, planner, controller — not a function
from image to velocity, and its waypoint is stateful across ticks. So rather than
reconstruct a teacher-evaluator, this runs an ordinary C2 orchestrator and
substitutes the executed command inside ``step``: C2's whole stack observes,
reasons and produces its command as usual (that is the label), and the vehicle
then moves according to the student instead. C2's memory and exploration clock
therefore evolve over student-visited states, which is what DAgger requires.

``beta`` is the probability of executing the *teacher's* command instead on any
given tick. Ross et al. anneal it from 1. Pure student rollouts (beta=0) with a
policy this weak end in a collision within seconds and return almost no states,
so the first iterations need a mixture to get far enough into an episode to see
anything worth labelling.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np

from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.training.dataset import IMAGE_SIZE, ActionCodec, _resize
from uavlab.training.splits import check_collection_range


def _append(base_path: Path, new: np.ndarray, out_path: Path, chunk: int = 2048) -> np.ndarray:
    """Concatenate on disk, in chunks, never holding two full copies in memory.

    The frame array is gigabytes. ``np.concatenate`` of a 2 GB base with a 1.5 GB
    addition transiently needs all three, and the machine this runs on does not
    reliably have 7 GB free.
    """
    base = np.load(base_path, mmap_mode="r")
    out = np.lib.format.open_memmap(
        out_path,
        mode="w+",
        dtype=base.dtype,
        shape=(len(base) + len(new),) + base.shape[1:],
    )
    for start in range(0, len(base), chunk):
        # Size the destination slice from the block, not from `chunk`. `out` is
        # longer than `base`, so on the final partial chunk `out[start:start+chunk]`
        # is still full-width and the assignment fails to broadcast.
        block = base[start : start + chunk]
        out[start : start + len(block)] = block
    out[len(base) :] = new
    out.flush()
    return out


class StudentDriver:
    """The trained policy, callable as observation -> velocity command.

    Deliberately reuses ``course_aligned_yaw_rate`` from the plugin rather than
    reimplementing it: the states this rollout visits are the training
    distribution for the next iteration, so a driver that steered differently
    from the deployed plugin would be collecting data for a policy that does not
    exist.
    """

    def __init__(self, checkpoint: Path, device: str = "cpu") -> None:
        import torch

        from uavlab.training.policy_net import FrameHistory, PolicyConfig, VisuomotorPolicy

        blob = torch.load(checkpoint, map_location="cpu", weights_only=False)
        stored = dict(blob["policy_config"])
        for key in ("state_features", "frame_offsets"):
            if key in stored:
                stored[key] = tuple(stored[key])
        config = PolicyConfig(**stored)
        model = VisuomotorPolicy(config)
        model.load_state_dict(blob["state_dict"])
        model.eval()
        self._torch = torch
        self._model = model.to(device)
        self._device = device
        self._codec = ActionCodec.from_dict(blob["codec"])
        self._image_size = config.image_size
        self._frame_offsets = config.frame_offsets
        self._history = FrameHistory(config.frame_offsets)

    def reset(self) -> None:
        self._history.reset()

    def act(self, frame: np.ndarray, state: np.ndarray) -> tuple[np.ndarray, bool]:
        from uavlab.plugins.reasoning.learned import course_aligned_yaw_rate

        torch = self._torch
        self._history.push(frame)
        with torch.no_grad():
            f = torch.from_numpy(self._history.stack(self._frame_offsets).astype(np.float32) / 255.0)
            f = f.permute(2, 0, 1).unsqueeze(0).to(self._device)
            s = torch.from_numpy(state.astype(np.float32)).unsqueeze(0).to(self._device)
            bins, terminate = self._model.act(f, s)
        action = self._codec.decode(bins.cpu().numpy())[0]
        yaw = float(np.arctan2(state[4], state[3]))
        action[3] = course_aligned_yaw_rate(float(action[0]), float(action[1]), yaw)
        return action, bool(int(terminate.item()) == 1)


async def rollout(
    teacher_arch,
    env_cfg,
    student: StudentDriver,
    seed: int,
    stride: int,
    beta: float,
) -> tuple[list, list, list, list, bool]:
    """One student-driven episode, labelled by the teacher at every recorded tick."""
    from uavlab.adapters.gym.deterministic_env import DeterministicEnv
    from uavlab.core.frame_store import global_store

    frames: list[np.ndarray] = []
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    terminates: list[int] = []
    rng = np.random.default_rng(seed)
    student.reset()
    original = DeterministicEnv.step
    tick = 0

    async def dagger_step(self, command, dt_ns):
        nonlocal tick
        uri = f"frame://{id(self)}/rgb/{max(self._seq - 1, 0)}"
        image = global_store().get(uri)
        executed = command
        if image is not None:
            frame = _resize(image, IMAGE_SIZE)
            v = self.vehicle.velocity
            state = np.array(
                [v[0], v[1], v[2], np.cos(self.vehicle.yaw), np.sin(self.vehicle.yaw)],
                dtype=np.float32,
            )
            if tick % stride == 0:
                # The label is the teacher's command at the state the student
                # reached — recorded before any substitution, always.
                frames.append(frame)
                states.append(state)
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
                terminates.append(int(self.status().distance_to_goal_m <= self.goal_radius_m))
            if rng.random() >= beta:
                action, _ = student.act(frame, state)
                executed = command.model_copy(
                    update={
                        "velocity": command.velocity.model_copy(
                            update={
                                "x": float(action[0]),
                                "y": float(action[1]),
                                "z": float(action[2]),
                            }
                        ),
                        "yaw_rate_rps": float(action[3]),
                    }
                )
        tick += 1
        await original(self, executed, dt_ns)

    DeterministicEnv.step = dagger_step
    try:
        result = await Orchestrator(
            teacher_arch, env_cfg, EpisodeSpec(episode_id=f"dagger_{seed}", seed=seed)
        ).run()
    finally:
        DeterministicEnv.step = original

    return frames, states, actions, terminates, bool(result.success)


def aggregate(
    base_dir: Path,
    out_dir: Path,
    checkpoint: Path,
    episodes: int = 120,
    env_name: str = "grid_nav_vision",
    teacher: str = "c2",
    stride: int = 2,
    start_seed: int = 1300,
    beta: float = 0.5,
    device: str = "cpu",
    config_root: Path | None = None,
    progress: bool = True,
) -> dict:
    """Roll the student out, label with the teacher, append to the base dataset.

    Every recorded tick is kept, successes and failures alike. That is the whole
    point: the states worth adding are the ones where the student went wrong, and
    filtering to successful episodes — correct for plain cloning — would discard
    exactly them.
    """
    check_collection_range(start_seed, episodes)
    base_dir, out_dir = Path(base_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    teacher_arch = load_architecture(teacher, config_root)
    env_cfg = load_environment(env_name, config_root)
    student = StudentDriver(Path(checkpoint), device)

    new_frames: list[np.ndarray] = []
    new_states: list[np.ndarray] = []
    new_actions: list[np.ndarray] = []
    new_terminates: list[int] = []
    successes = 0

    for i in range(episodes):
        f, s, a, t, ok = asyncio.run(
            rollout(teacher_arch, env_cfg, student, start_seed + i, stride, beta)
        )
        new_frames += f
        new_states += s
        new_actions += a
        new_terminates += t
        successes += int(ok)
        if progress and (i + 1) % 20 == 0:
            print(
                f"  {i + 1}/{episodes} rollouts  student-driven successes={successes} "
                f"new samples={len(new_frames)}",
                flush=True,
            )

    if not new_frames:
        raise RuntimeError("no DAgger samples collected; is the environment rendering?")

    base = json.loads((base_dir / "manifest.json").read_text(encoding="utf-8"))
    frames = _append(base_dir / "frames.npy", np.stack(new_frames), out_dir / "frames.npy")
    states = _append(base_dir / "states.npy", np.stack(new_states), out_dir / "states.npy")
    actions = _append(base_dir / "actions.npy", np.stack(new_actions), out_dir / "actions.npy")
    terminates = _append(
        base_dir / "terminates.npy",
        np.array(new_terminates, dtype=np.int64),
        out_dir / "terminates.npy",
    )
    actions = np.asarray(actions)

    codec = ActionCodec.fit(actions)
    manifest = {
        "expert": teacher,
        "environment": env_name,
        "collection": "dagger",
        "base_dataset": str(base_dir),
        "base_samples": int(base["samples"]),
        "dagger_samples": int(len(new_frames)),
        "dagger_rollouts": episodes,
        "dagger_rollout_successes": successes,
        "beta": beta,
        "student_checkpoint": str(checkpoint),
        "episodes_kept": episodes + int(base["episodes_kept"]),
        "samples": int(len(frames)),
        "stride": stride,
        "image_size": IMAGE_SIZE,
        "seeds": [start_seed, start_seed + episodes - 1],
        "codec": codec.to_dict(),
        "codec_error": codec.roundtrip_error(actions),
        "action_dims": base["action_dims"],
        "frames_bytes": int(frames.nbytes),
        "terminate_positive_rate": float(terminates.mean()),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
