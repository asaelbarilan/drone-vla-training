"""Strict OpenFly token codec with explicit action-coverage checks.

The published vlnv11 statistics cover vertical primitives; using them is an
explicit adapter choice, not proof of the checkpoint's historical calibration.
"""

import numpy as np

CODEBOOK = np.array(
    [
        [1, 0, 0, 0, 0, 0, 0, 0],
        [0, 3, 0, 0, 0, 0, 0, 0],
        [0, 0, 15, 0, 0, 0, 0, 0],
        [0, 0, 0, 15, 0, 0, 0, 0],
        [0, 0, 0, 0, 2, 0, 0, 0],
        [0, 0, 0, 0, 0, 2, 0, 0],
        [0, 0, 0, 0, 0, 0, 5, 0],
        [0, 0, 0, 0, 0, 0, 0, 5],
        [0, 6, 0, 0, 0, 0, 0, 0],
        [0, 9, 0, 0, 0, 0, 0, 0],
    ],
    dtype=float,
)


class OpenFlyCodec:
    def __init__(self, config, norm_key):
        self.key = norm_key
        self.stats = config["norm_stats"][norm_key]["action"]
        self.low = np.asarray(self.stats["q01"])
        self.high = np.asarray(self.stats["q99"])
        self.mask = np.asarray(self.stats.get("mask", [True] * 8))
        self.bins = np.linspace(-1, 1, config["n_action_bins"])
        self.centers = (self.bins[:-1] + self.bins[1:]) / 2
        self.vocab = config["text_config"]["vocab_size"] - config["pad_to_multiple_of"]

    def encode(self, action_id):
        action = CODEBOOK[action_id]
        normalized = np.where(
            self.mask, 2 * (action - self.low) / (self.high - self.low + 1e-8) - 1, action
        )
        constant = np.asarray(self.stats["min"]) == np.asarray(self.stats["max"])
        normalized = np.where(constant, 0, normalized)
        return (self.vocab - np.digitize(np.clip(normalized, -1, 1), self.bins)).tolist()

    def decode(self, tokens):
        if len(tokens) != 8:
            raise ValueError("Expected exactly eight generated action tokens")
        ids = np.asarray(tokens)
        indices = self.vocab - ids
        if not np.all((indices >= 1) & (indices <= len(self.bins))):
            raise ValueError("Output includes a non-action token")
        normalized = self.centers[np.clip(indices - 1, 0, len(self.centers) - 1)]
        vector = np.where(
            self.mask, 0.5 * (normalized + 1) * (self.high - self.low) + self.low, normalized
        )
        rounded = np.rint(vector).astype(int)
        matches = np.flatnonzero(np.all(rounded == CODEBOOK, axis=1))
        action = int(matches[0]) if len(matches) == 1 else None
        return dict(vector=vector.tolist(), rounded=rounded.tolist(), action_id=action)

    def require_coverage(self, action_ids):
        failures = [
            a for a in sorted(set(action_ids)) if self.decode(self.encode(a))["action_id"] != a
        ]
        if failures:
            raise ValueError(f"{self.key} cannot round-trip required action IDs {failures}")
        return dict(norm_key=self.key, roundtrip_actions=sorted(set(action_ids)))
