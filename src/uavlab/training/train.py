"""Behaviour-cloning training loop.

Deliberately plain: cross-entropy over per-dimension action bins, Adam, a
held-out split, early stopping on validation. There is nothing clever here and
there should not be — the interesting question is whether a learned policy can
hold the C7-C14 action slot at all, not whether this training recipe is optimal.

Two things it reports that a bare loss curve would not:

* **Decoded velocity error in m/s**, not just bin accuracy. A policy can be 60 %
  bin-accurate and fly fine (adjacent bins are 0.16 m/s apart) or be 90 %
  accurate and unusable if the errors cluster on the turns. Physical units are
  what tell you which.
* **The codec's own error as a floor.** No policy can beat the quantisation
  error of its action encoding, so that number is printed alongside, and a
  reported error near it means the model is done learning, not that it is bad.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from uavlab.training.dataset import ActionCodec, load
from uavlab.training.policy_net import PolicyConfig, VisuomotorPolicy


@dataclass(slots=True)
class TrainConfig:
    epochs: int = 12
    batch_size: int = 128
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    val_fraction: float = 0.15
    seed: int = 0
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    patience: int = 4


class ExpertDataset(Dataset):
    """Frames are memory-mapped; only the batch is materialised."""

    def __init__(self, frames, states, bins, terminates, indices, episode_starts, offsets) -> None:
        self.frames = frames
        self.states = states
        self.bins = bins
        self.terminates = terminates
        self.indices = indices
        self.episode_starts = episode_starts
        self.offsets = offsets

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, i: int):
        j = int(self.indices[i])
        # Clamp each history offset to the first sample of *this* episode. The
        # arrays hold many flights back to back, so an unclamped j-40 near an
        # episode start reads the end of the previous flight and hands the
        # network a history that never happened.
        start = int(self.episode_starts[j])
        history = [
            np.asarray(self.frames[max(j - offset, start)]) for offset in self.offsets
        ]
        frame = torch.from_numpy(np.concatenate(history, axis=-1).copy())
        frame = frame.permute(2, 0, 1).float() / 255.0
        return (
            frame,
            torch.from_numpy(self.states[j]),
            torch.from_numpy(self.bins[j]),
            torch.tensor(int(self.terminates[j])),
        )


def episode_start_index(episodes: np.ndarray) -> np.ndarray:
    """For each sample, the index of the first sample of its episode."""
    boundaries = np.flatnonzero(np.diff(episodes, prepend=episodes[0] - 1)) if len(episodes) else []
    starts = np.zeros(len(episodes), dtype=np.int64)
    boundaries = np.asarray(boundaries, dtype=np.int64)
    for k, begin in enumerate(boundaries):
        end = boundaries[k + 1] if k + 1 < len(boundaries) else len(episodes)
        starts[begin:end] = begin
    return starts


def _split(n: int, val_fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Split by contiguous block, not at random.

    Consecutive control ticks are almost identical frames. A random split would
    put a frame in train and its neighbour 50 ms later in validation, and the
    validation score would measure memorisation rather than generalisation.
    """
    cut = int(n * (1.0 - val_fraction))
    return np.arange(cut), np.arange(cut, n)


def evaluate(model, loader, codec: ActionCodec, device: str) -> dict[str, float]:
    model.eval()
    loss_fn = nn.CrossEntropyLoss()
    total_loss = 0.0
    correct = np.zeros(4)
    count = 0
    velocity_errors: list[np.ndarray] = []
    term_tp = term_fp = term_fn = 0

    with torch.no_grad():
        for frame, state, bins, terminate in loader:
            frame, state = frame.to(device), state.to(device)
            bins, terminate = bins.to(device), terminate.to(device)
            logits, term_logits = model(frame, state)
            total_loss += sum(
                loss_fn(logits[:, d], bins[:, d]).item() for d in range(logits.shape[1])
            )
            total_loss += loss_fn(term_logits, terminate).item()
            predicted = logits.argmax(-1)
            correct += (predicted == bins).float().sum(0).cpu().numpy()
            count += bins.shape[0]
            velocity_errors.append(
                np.linalg.norm(
                    codec.decode(predicted.cpu().numpy())[:, :3]
                    - codec.decode(bins.cpu().numpy())[:, :3],
                    axis=1,
                )
            )
            pt = term_logits.argmax(-1)
            term_tp += int(((pt == 1) & (terminate == 1)).sum())
            term_fp += int(((pt == 1) & (terminate == 0)).sum())
            term_fn += int(((pt == 0) & (terminate == 1)).sum())

    errors = np.concatenate(velocity_errors)
    # Terminate is heavily imbalanced, so accuracy would be meaningless —
    # predicting "never stop" would score ~95%. Recall is what matters: a missed
    # stop means the mission never completes even after reaching the goal.
    return {
        "loss": total_loss / max(len(loader), 1),
        "bin_accuracy": float((correct / max(count, 1)).mean()),
        "velocity_error_mean_mps": float(errors.mean()),
        "velocity_error_p95_mps": float(np.percentile(errors, 95)),
        "terminate_recall": term_tp / max(term_tp + term_fn, 1),
        "terminate_precision": term_tp / max(term_tp + term_fp, 1),
    }


def train(
    data_dir: Path,
    out_path: Path,
    config: TrainConfig | None = None,
    policy_config: PolicyConfig | None = None,
    progress: bool = True,
) -> dict:
    config = config or TrainConfig()
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)

    frames, states, actions, terminates, episodes, codec, manifest = load(data_dir)
    bins = codec.encode(actions)
    policy_config = policy_config or PolicyConfig(bins=codec.bins, image_size=manifest["image_size"])
    if len(policy_config.frame_offsets) > 1 and episodes is None:
        raise ValueError(
            f"{data_dir} has no episodes.npy, so episode boundaries are unknown and a "
            "frame history cannot be built without stitching separate flights together. "
            "Re-collect the dataset, or train with frame_offsets=(0,)."
        )
    if episodes is None:
        episodes = np.zeros(len(frames), dtype=np.int64)
    episode_starts = episode_start_index(episodes)

    train_idx, val_idx = _split(len(frames), config.val_fraction, config.seed)
    loaders = {
        "train": DataLoader(
            ExpertDataset(frames, states, bins, terminates, train_idx,
                          episode_starts, policy_config.frame_offsets),
            batch_size=config.batch_size, shuffle=True, num_workers=0, drop_last=True,
        ),
        "val": DataLoader(
            ExpertDataset(frames, states, bins, terminates, val_idx,
                          episode_starts, policy_config.frame_offsets),
            batch_size=config.batch_size, shuffle=False, num_workers=0,
        ),
    }

    model = VisuomotorPolicy(policy_config).to(config.device)
    optimiser = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=config.epochs)
    loss_fn = nn.CrossEntropyLoss()
    # Terminal ticks are a small fraction of the data, so an unweighted loss
    # would learn "never stop", score well, and produce a policy that reaches
    # the goal and hovers. Weight the positive class by its inverse frequency.
    positive_rate = max(float(terminates[train_idx].mean()), 1e-4)
    terminate_loss_fn = nn.CrossEntropyLoss(
        weight=torch.tensor([1.0, min(1.0 / positive_rate, 50.0)], device=config.device)
    )

    floor = codec.roundtrip_error(actions)
    if progress:
        print(f"samples {len(frames)}  train {len(train_idx)}  val {len(val_idx)}")
        print(f"policy parameters: {model.parameter_count():,}  device: {config.device}")
        print(
            f"quantisation floor: {floor['velocity_error_mean_mps']:.4f} m/s mean "
            f"(no policy can beat this)"
        )
        print(f"terminal ticks in training data: {positive_rate:.1%}")

    best = float("inf")
    best_metrics: dict[str, float] = {}
    stale = 0
    started = time.perf_counter()

    for epoch in range(1, config.epochs + 1):
        model.train()
        running = 0.0
        for frame, state, target, terminate in loaders["train"]:
            frame, state = frame.to(config.device), state.to(config.device)
            target, terminate = target.to(config.device), terminate.to(config.device)
            logits, term_logits = model(frame, state)
            loss = sum(loss_fn(logits[:, d], target[:, d]) for d in range(logits.shape[1]))
            loss = loss + terminate_loss_fn(term_logits, terminate)
            optimiser.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimiser.step()
            running += loss.item()
        scheduler.step()

        metrics = evaluate(model, loaders["val"], codec, config.device)
        if progress:
            print(
                f"  epoch {epoch:2d}  train_loss {running / max(len(loaders['train']), 1):6.3f}"
                f"  val_loss {metrics['loss']:6.3f}"
                f"  bin_acc {metrics['bin_accuracy']:.3f}"
                f"  vel_err {metrics['velocity_error_mean_mps']:.3f} m/s"
                f"  stop_recall {metrics['terminate_recall']:.2f}",
                flush=True,
            )

        if metrics["loss"] < best - 1e-4:
            best, best_metrics, stale = metrics["loss"], metrics, 0
            out_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "state_dict": model.state_dict(),
                    "policy_config": asdict(policy_config),
                    "codec": codec.to_dict(),
                    "metrics": metrics,
                    "data_manifest": manifest,
                },
                out_path,
            )
        else:
            stale += 1
            if stale >= config.patience:
                if progress:
                    print(f"  early stop at epoch {epoch} (no improvement for {stale})")
                break

    summary = {
        "checkpoint": str(out_path),
        "parameters": model.parameter_count(),
        "epochs_run": epoch,
        "wall_seconds": round(time.perf_counter() - started, 1),
        "quantisation_floor": floor,
        "best": best_metrics,
        "train_config": asdict(config),
    }
    out_path.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
