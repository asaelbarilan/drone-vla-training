"""The student network: a small visuomotor policy.

Deliberately small. The point is to occupy the direct-action slot in C7-C14 with
something genuinely *learned*, fast enough for the configured 10 Hz decision
loop, and trainable on a laptop in minutes. It is not a foundation model and
must never be described as one.

Design notes worth keeping:

* **Four independent per-dimension classifiers**, 64 bins each, over
  (vx, vy, vz, yaw_rate). Measured against a joint codebook and 7x more accurate;
  see docs/SMALL_VLA_SEARCH.md.
* **Proprioception is deliberately restricted to attitude.** Velocity is NOT an
  input; see STATE_FEATURES_ATTITUDE_ONLY for the measurement that forced this.
* **Yaw enters as cos/sin, never as an angle.** A raw angle has a discontinuity
  at +-pi that a network has to waste capacity learning around.
* **No language input.** The environment issues one instruction for every
  episode, so a language channel would carry zero bits and could not be learned
  from. This is a visuomotor policy; calling it vision-language-action would be
  false. Adding language means first giving the environment instruction
  diversity to condition on.
* **A dilated history of frames, not a single frame.** See FRAME_OFFSETS.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

STATE_DIM = 5
"""vx, vy, vz, cos(yaw), sin(yaw)."""


STATE_FEATURES_ATTITUDE_ONLY: tuple[int, ...] = (3, 4)
"""Indices into the stored 5-D state: cos(yaw), sin(yaw). No velocity.

**Velocity is deliberately withheld from the policy.** Measured on the expert
data, ``corr(own velocity, expert action)`` is 0.92, because velocity is just a
lagged copy of the previous command. Given it as an input, the network learns to
echo it and ignores the image entirely: the first trained policy scored 1.307 m/s
where *simply echoing your own velocity* scores 1.174 m/s — it had learned the
shortcut and nothing else.

Closed-loop that is catastrophic rather than merely mediocre. Starting from rest,
echoing your own velocity means commanding zero, so the vehicle never moves: the
first policy froze at 0.12 m/s on a fixed heading for the whole episode while
predicting 4.17 m/s on held-out expert states.

This is causal confusion / the copycat problem (de Haan et al. 2019; Wen et al.
2020), and removing the shortcut feature is the standard remedy. Yaw stays,
because the camera is body-fixed and the action is in ENU: without attitude the
mapping from "target is left of frame" to a world-frame velocity is not
determined.
"""


FRAME_OFFSETS: tuple[int, ...] = (0, 5, 15, 40)
"""How far back, in stored samples, the history frames are taken from.

**Why a history at all.** A single frame cannot determine the label. The target
is out of view in 76% of frames, and the teacher's command in those frames
depends on a waypoint it committed to up to half a second earlier and on a
search heading that advances on a clock. Two frames that look identical to a
memoryless student therefore carry different labels, and no amount of data or
relabelling fixes that — behaviour cloning and DAgger both failed here first,
0.00 and 0.03 success on held-out seeds. History is what makes the label a
function of the input.

**Why dilated rather than consecutive.** Samples are stored every other control
tick, so four consecutive frames span 0.3 s — long enough to see motion blur,
far too short to remember where a target was last seen. These offsets span
0.0, 0.5, 1.5 and 4.0 seconds, which covers the interval over which a target
leaves the frame and the vehicle must keep flying toward it.

At an episode's start there is no history, so the oldest available frame is
repeated. That is the honest padding: it says "nothing happened before this",
which is true.
"""


@dataclass(slots=True)
class PolicyConfig:
    bins: int = 64
    action_dims: int = 4
    image_size: int = 112
    width: int = 32
    hidden: int = 256
    dropout: float = 0.1
    state_features: tuple[int, ...] = STATE_FEATURES_ATTITUDE_ONLY
    frame_offsets: tuple[int, ...] = FRAME_OFFSETS

    @property
    def state_dim(self) -> int:
        return len(self.state_features)

    @property
    def in_channels(self) -> int:
        return 3 * len(self.frame_offsets)


class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, stride: int = 2) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, stride=stride, padding=1, bias=False),
            nn.GroupNorm(min(8, out_ch), out_ch),
            nn.SiLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class VisuomotorPolicy(nn.Module):
    """Frame + proprioception -> per-dimension action-bin logits."""

    def __init__(self, config: PolicyConfig | None = None) -> None:
        super().__init__()
        self.config = config or PolicyConfig()
        c = self.config
        w = c.width

        self.vision = nn.Sequential(
            ConvBlock(c.in_channels, w),  # 112 -> 56
            ConvBlock(w, w * 2),      # 56  -> 28
            ConvBlock(w * 2, w * 4),  # 28  -> 14
            ConvBlock(w * 4, w * 4),  # 14  -> 7
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
        )
        self.state = nn.Sequential(
            nn.Linear(c.state_dim, 64), nn.SiLU(inplace=True), nn.Linear(64, 64)
        )
        self.trunk = nn.Sequential(
            nn.Linear(w * 4 + 64, c.hidden),
            nn.SiLU(inplace=True),
            nn.Dropout(c.dropout),
            nn.Linear(c.hidden, c.hidden),
            nn.SiLU(inplace=True),
        )
        # One head per action dimension. Separate heads rather than a single
        # flattened output so the per-dimension structure stays explicit and a
        # dimension can be inspected or frozen on its own.
        self.heads = nn.ModuleList(
            [nn.Linear(c.hidden, c.bins) for _ in range(c.action_dims)]
        )
        # Terminal intent is its own binary output, not an action bin. The oracle
        # ends a mission with a *directive* rather than a velocity, so without
        # this the cloned policy would fly to the goal and hover there forever —
        # reaching the target but never completing the mission, which scores as
        # failure under require_terminal_stop. Real VLAs carry a discrete
        # terminate/gripper dimension alongside continuous motion for the same
        # reason.
        self.terminate_head = nn.Linear(c.hidden, 2)

    def select_state(self, state: torch.Tensor) -> torch.Tensor:
        """Keep only the permitted state features. Slicing happens here, once,
        so a caller cannot accidentally feed the policy a channel it must not
        see."""
        idx = torch.tensor(self.config.state_features, device=state.device)
        return state.index_select(-1, idx)

    def forward(
        self, frame: torch.Tensor, state: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """``frame`` (B, 3*len(frame_offsets), H, W) in [0,1], ``state`` (B,5).

        Returns ``(action_logits (B, dims, bins), terminate_logits (B, 2))``.
        """
        features = torch.cat([self.vision(frame), self.state(self.select_state(state))], dim=-1)
        hidden = self.trunk(features)
        action_logits = torch.stack([head(hidden) for head in self.heads], dim=1)
        return action_logits, self.terminate_head(hidden)

    @torch.no_grad()
    def act(self, frame: torch.Tensor, state: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Greedy bin indices (B, dims) and terminate flag (B,).

        Greedy, never sampled. Sampling would make the policy nondeterministic
        and break paired-by-seed comparison — the same trap the inference backend
        already fell into.
        """
        action_logits, terminate_logits = self(frame, state)
        return action_logits.argmax(dim=-1), terminate_logits.argmax(dim=-1)

    def parameter_count(self) -> int:
        return sum(p.numel() for p in self.parameters())


def build(config: PolicyConfig | None = None) -> VisuomotorPolicy:
    return VisuomotorPolicy(config)


class FrameHistory:
    """The inference-time counterpart of the dataset's history stacking.

    Kept next to the network rather than in the plugin because two
    implementations of "what does the model see" drift apart, and the DAgger
    rollout driver needs the identical one — the states it visits become the
    next training distribution, so a driver that saw a different history would
    be collecting data for a policy that does not exist.

    One `push` per decision. The stored dataset samples every other control tick
    at 20 Hz, and the direct-action architectures decide at 10 Hz, so one
    decision is one stored sample and the offsets carry over unchanged.
    """

    __slots__ = ("_frames", "_max")

    def __init__(self, offsets: tuple[int, ...]) -> None:
        self._max = max(offsets) + 1
        self._frames: list = []

    def reset(self) -> None:
        self._frames.clear()

    def push(self, frame) -> None:
        self._frames.append(frame)
        if len(self._frames) > self._max:
            del self._frames[0 : len(self._frames) - self._max]

    def stack(self, offsets: tuple[int, ...]):
        """Newest-first by offset, oldest available repeated when history is short.

        Matches the dataset's clamp to the episode's first sample: at the start
        of an episode every offset resolves to the current frame, which says
        "nothing happened before this" — true, and the same thing training saw.
        """
        import numpy as np

        if not self._frames:
            raise RuntimeError("FrameHistory.stack called before any push")
        newest = len(self._frames) - 1
        return np.concatenate(
            [self._frames[max(newest - offset, 0)] for offset in offsets], axis=-1
        )
