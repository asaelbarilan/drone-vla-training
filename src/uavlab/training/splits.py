"""The seed split. Declared once, enforced in code, so it cannot drift.

Scenes are generated deterministically from the episode seed, so the seed *is*
the unit of separation: two episodes with different seeds are different scenes,
and two episodes with the same seed are the same scene down to obstacle
placement. Splitting on seeds therefore splits on scenes, which is the only
split that means anything here. Splitting frames instead would put neighbouring
frames of one flight on both sides and report a fictional score.

``EVAL_SEEDS`` is held out. Nothing trained may ever have seen a frame from it:
it is what every reported architecture number is measured on, including the
scripted baselines, so that a learned policy and a scripted one are compared on
identical scenes. ``TRAIN_SEEDS`` is the only range data collection may draw
from, and ``collect()`` raises if asked for anything outside it.

The ranges are far apart rather than adjacent purely so that an off-by-one in
some future caller lands in empty space instead of silently crossing the line.
"""

from __future__ import annotations

EVAL_SEEDS = range(1, 41)
"""Held out for scoring. 40 scenes. Never collected from, never trained on."""

TRAIN_SEEDS = range(1000, 2000)
"""The only range expert demonstrations may be drawn from."""

assert not (set(EVAL_SEEDS) & set(TRAIN_SEEDS)), "seed splits overlap"


def check_collection_range(start_seed: int, episodes: int) -> None:
    """Raise if a requested collection range would touch held-out scenes.

    Deliberately an exception rather than a warning. A warning scrolls past in
    a five-minute collection run and the resulting checkpoint is indistinguishable
    from a clean one afterwards — the contamination would only ever be found by
    someone rereading the manifest.
    """
    requested = range(start_seed, start_seed + episodes)
    leaked = sorted(set(requested) & set(EVAL_SEEDS))
    if leaked:
        raise ValueError(
            f"collection range {start_seed}..{start_seed + episodes - 1} includes "
            f"held-out evaluation seeds {leaked[:5]}"
            f"{'...' if len(leaked) > 5 else ''}; training data must come from "
            f"TRAIN_SEEDS ({TRAIN_SEEDS.start}..{TRAIN_SEEDS.stop - 1})"
        )
    outside = sorted(set(requested) - set(TRAIN_SEEDS))
    if outside:
        raise ValueError(
            f"collection range {start_seed}..{start_seed + episodes - 1} falls "
            f"outside TRAIN_SEEDS ({TRAIN_SEEDS.start}..{TRAIN_SEEDS.stop - 1}); "
            f"widen TRAIN_SEEDS deliberately rather than collecting from unclaimed seeds"
        )
