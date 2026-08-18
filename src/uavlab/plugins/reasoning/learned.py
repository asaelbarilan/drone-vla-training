"""A trained visuomotor policy occupying the direct-action slot.

This is a real learned network — a small convnet behaviour-cloned from C2 —
emitting `KinematicAction` at the same authority level as `mock_vla`. Swapping
between them is a YAML edit, which is the property the whole testbed exists to
have.

Three of the four action channels come from the network; yaw comes from a rule.
That split is measured, not assumed — see `yaw_mode`.

**What it is not.** Not a foundation model, and not vision-*language*-action.
The environment issues one instruction for every episode, so there is no
language signal to condition on and none is used. Calling this a VLA would be
false; it is a visuomotor policy in the slot a VLA would occupy. Language
conditioning requires giving the environment instruction diversity first.

Determinism: greedy argmax, never sampled, and the simulated compute cost is
charged as a configured constant rather than the measured forward-pass time.
Both for the same reason — charging live wall-clock jitter to the simulation
clock destroys paired-by-seed comparison, as already measured for the Ollama
backend.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    KinematicAction,
    MissionDirective,
    MissionSpec,
    ProgressLabel,
    Vec3,
)
from uavlab.core.registry import register
from uavlab.interfaces import DecisionContext
from uavlab.plugins.reasoning.base import BasePolicy


def course_aligned_yaw_rate(
    vx: float,
    vy: float,
    yaw_rad: float,
    gain_per_s: float = 2.0,
    max_rate_rps: float = 1.5,
    min_speed_mps: float = 0.5,
) -> float:
    """Turn the nose toward the commanded velocity.

    A free function rather than a method because DAgger rollouts need exactly
    this rule while driving the vehicle outside the plugin, and two copies of a
    control law drift apart.
    """
    if float(np.hypot(vx, vy)) < min_speed_mps:
        return 0.0
    desired = float(np.arctan2(vy, vx))
    # Wrap into (-pi, pi] before applying the gain: without this a heading error
    # just past +-pi commands a turn the long way round, and the vehicle spins
    # away from a target it is nearly facing.
    error = (desired - yaw_rad + np.pi) % (2 * np.pi) - np.pi
    return float(np.clip(error * gain_per_s, -max_rate_rps, max_rate_rps))


@register("policy", "learned_visuomotor")
class LearnedVisuomotorPolicy(BasePolicy):
    """Loads a behaviour-cloned checkpoint and drives from camera frames."""

    requires_vision = True

    def __init__(self, **params: Any) -> None:
        params.setdefault("model_id", "bc-visuomotor")
        super().__init__(**params)
        self.checkpoint_path = params.get("checkpoint", "models/bc_grid_nav.pt")
        self.device = str(params.get("device", "auto"))
        self.terminate_enabled = bool(params.get("terminate_enabled", True))
        self.min_terminal_speed_mps = float(params.get("min_terminal_speed_mps", 1.5))
        """Ignore a stop prediction while still moving fast.

        A single spurious terminate at cruise speed would end the mission tens of
        metres out. The oracle only ever stops when already slow, so requiring
        that costs nothing on true positives.
        """
        self.action_duration_s = float(params.get("action_duration_s", 0.2))

        self.yaw_mode = str(params.get("yaw_mode", "course_aligned"))
        """`course_aligned` (default) or `learned`.

        The network's yaw output is measurably worthless: on held-out frames its
        yaw_rate error is 0.319 against 0.294 for the best possible *constant*,
        i.e. worse than never turning at all, while the same network beats any
        constant by 2.5x on vx/vy. Yaw is the one channel the teacher cannot
        convey through a single frame, because C2's yaw command depends on the
        waypoint it committed to earlier and on its exploration clock - hidden
        state the student never sees.

        Left in the loop this is fatal rather than merely noisy. The camera is
        body-fixed, so a policy that does not turn toward the target loses it
        from frame and never recovers: 76% of training frames already have no
        target in view and a non-turning policy drives that to ~100% within
        seconds. Measured closed-loop consequence: 0/40, drifting 74 m from goal.

        `course_aligned` replaces that channel with a rule - point the nose along
        the commanded velocity - so the camera always looks where the vehicle is
        going. The learned channels are untouched. Keep `learned` available so
        the comparison stays runnable rather than asserted.
        """
        self.yaw_gain_per_s = float(params.get("yaw_gain_per_s", 2.0))
        self.max_yaw_rate_rps = float(params.get("max_yaw_rate_rps", 1.5))
        self.yaw_align_min_speed_mps = float(params.get("yaw_align_min_speed_mps", 0.5))
        """Below this the commanded direction is numerically meaningless, so hold
        the current heading rather than chase the direction of rounding noise."""

        self.terminate_consecutive = int(params.get("terminate_consecutive", 3))
        """How many decisions in a row must predict "done" before stopping.

        The stop head has recall 0.97 but precision 0.44 against C2 data: two of
        every three raised stops are false. One of them ends the mission. With
        `terminate_consecutive: 1` that cost 9 of 20 episodes to `agent_stopped`
        while still 28 m from the goal.

        Requiring agreement across consecutive frames is the cheap fix: false
        positives are driven by frame-level noise and do not persist, whereas a
        true arrival holds for as long as the vehicle sits there. At the
        configured decision rate three in a row is under half a second, so it
        costs a true stop almost nothing.
        """
        self._terminate_streak = 0

        self._model = None
        self._codec = None
        self._torch = None
        self.forward_calls = 0
        self.forward_seconds = 0.0
        self.terminate_predictions = 0

    @property
    def name(self) -> str:
        return "learned_visuomotor"

    @property
    def emits(self) -> tuple[str, ...]:
        return ("kinematic_action", "mission_directive")

    # -- loading ------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import torch

        from uavlab.training.dataset import ActionCodec
        from uavlab.training.policy_net import FrameHistory, PolicyConfig, VisuomotorPolicy

        path = Path(self.checkpoint_path)
        if not path.is_file():
            raise FileNotFoundError(
                f"no trained policy at {path}. Train one first:\n"
                f"  uavlab collect --episodes 200\n"
                f"  uavlab train"
            )
        blob = torch.load(path, map_location="cpu", weights_only=False)
        stored = dict(blob["policy_config"])
        # Tuples survive the checkpoint round-trip as lists, and PolicyConfig is
        # a slots dataclass whose fields are indexed positionally downstream.
        for key in ("state_features", "frame_offsets"):
            if key in stored:
                stored[key] = tuple(stored[key])
        config = PolicyConfig(**stored)
        model = VisuomotorPolicy(config)
        model.load_state_dict(blob["state_dict"])
        model.eval()

        device = self.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._torch = torch
        self._model = model.to(device)
        self._device = device
        self._codec = ActionCodec.from_dict(blob["codec"])
        self._image_size = config.image_size
        self._frame_offsets = config.frame_offsets
        self._history = FrameHistory(config.frame_offsets)

    def reset(self, mission: MissionSpec, seed: int) -> None:
        super().reset(mission, seed)
        self.forward_calls = 0
        self.forward_seconds = 0.0
        self.terminate_predictions = 0
        self._terminate_streak = 0
        if self._model is not None:
            # A stale history would hand the first decision of a new episode the
            # last frames of the previous one.
            self._history.reset()

    # -- inference ----------------------------------------------------------

    def _observe(self, ctx: DecisionContext):
        """Build the network's inputs from the observation contract only."""
        from uavlab.core.frame_store import global_store

        ref = ctx.observation.rgb
        if ref is None:
            raise RuntimeError("the learned policy needs an rgb sensor reference")
        image = global_store().get(ref.uri)
        if image is None:
            raise RuntimeError(
                f"no frame behind {ref.uri!r}. This policy is visuomotor: set "
                "`render: true` in the environment params."
            )
        if image.size != (self._image_size, self._image_size):
            image = image.resize((self._image_size, self._image_size))

        torch = self._torch
        self._history.push(np.asarray(image, dtype=np.uint8))
        stacked = self._history.stack(self._frame_offsets)
        frame = torch.from_numpy(stacked.copy())
        frame = frame.permute(2, 0, 1).float().div_(255.0).unsqueeze(0)

        velocity = ctx.observation.velocity
        yaw = ctx.observation.yaw_rad
        state = torch.tensor(
            [[velocity.x, velocity.y, velocity.z, np.cos(yaw), np.sin(yaw)]],
            dtype=torch.float32,
        )
        return frame.to(self._device), state.to(self._device)

    async def decide(self, ctx: DecisionContext) -> DecisionEnvelope | None:
        self._ensure_loaded()
        # Charged as a configured constant via the inference backend, not as the
        # measured forward time; the real time is recorded separately in stats.
        await self.charge(ctx)

        frame, state = self._observe(ctx)
        started = time.perf_counter()
        bins, terminate = self._model.act(frame, state)
        self.forward_seconds += time.perf_counter() - started
        self.forward_calls += 1

        action = self._codec.decode(bins.cpu().numpy())[0]
        speed = float(np.linalg.norm(action[:3]))

        raised = self.terminate_enabled and int(terminate.item()) == 1
        self._terminate_streak = self._terminate_streak + 1 if raised else 0
        if raised:
            self.terminate_predictions += 1
            if (
                self._terminate_streak >= self.terminate_consecutive
                and speed <= self.min_terminal_speed_mps
                and not self._stopped
            ):
                self._stopped = True
                return self.envelope(
                    ctx,
                    DecisionKind.MISSION_DIRECTIVE,
                    MissionDirective(
                        label=ProgressLabel.STOP, rationale="learned policy: terminal state"
                    ),
                    0.8,
                )

        yaw_rate = self._yaw_rate(action, ctx.observation.yaw_rad)
        return self.envelope(
            ctx,
            DecisionKind.KINEMATIC_ACTION,
            KinematicAction(
                velocity=Vec3(x=float(action[0]), y=float(action[1]), z=float(action[2])),
                yaw_rate_rps=yaw_rate,
                duration_s=self.action_duration_s,
            ),
            0.8,
            note=f"behaviour-cloned, yaw={self.yaw_mode}",
        )

    def _yaw_rate(self, action: np.ndarray, yaw_rad: float) -> float:
        """Turn the nose toward the commanded velocity, or use the learned bin."""
        if self.yaw_mode == "learned":
            return float(action[3])
        return course_aligned_yaw_rate(
            float(action[0]),
            float(action[1]),
            yaw_rad,
            self.yaw_gain_per_s,
            self.max_yaw_rate_rps,
            self.yaw_align_min_speed_mps,
        )

    def stats(self) -> dict[str, float]:
        return {
            "policy_forward_calls": float(self.forward_calls),
            "policy_forward_s_total": self.forward_seconds,
            "policy_forward_s_mean": (
                self.forward_seconds / self.forward_calls if self.forward_calls else 0.0
            ),
            "policy_terminate_predictions": float(self.terminate_predictions),
        }
