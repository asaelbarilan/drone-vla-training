"""Optional shared visual features.

Feature sharing is a *deployment efficiency* question, not a first-order
architecture question.  Turning it on during the first causal sweep would
confound "two semantic loops help" with "sharing a ViT is cheap", so it is off
by default and enabled only after a dual-loop architecture has earned its place.

Note what is shared and what is not: multiple semantic agents may reuse the same
visual features while keeping entirely separate contexts and KV caches.  Sharing
features is not sharing memory.
"""

from __future__ import annotations

from dataclasses import dataclass

CacheKey = tuple[str, str, int, str]
"""``(model_id, encoder_id, observation_seq, preprocessing_hash)``."""


@dataclass(slots=True)
class CacheStats:
    hits: int = 0
    misses: int = 0
    stores: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "feature_cache_hits": float(self.hits),
            "feature_cache_misses": float(self.misses),
            "feature_cache_stores": float(self.stores),
            "feature_cache_evictions": float(self.evictions),
            "feature_cache_hit_rate": self.hit_rate,
        }


class FeatureCache:
    """Bounded cache keyed on content, not on wall-clock recency."""

    def __init__(self, enabled: bool = False, capacity: int = 32) -> None:
        self.enabled = enabled
        self.capacity = capacity
        self._store: dict[CacheKey, object] = {}
        self._order: list[CacheKey] = []
        self.stats = CacheStats()

    @staticmethod
    def key(
        model_id: str, encoder_id: str, observation_seq: int, preprocessing_hash: str
    ) -> CacheKey:
        return (model_id, encoder_id, observation_seq, preprocessing_hash)

    def get(self, key: CacheKey) -> object | None:
        if not self.enabled:
            return None
        value = self._store.get(key)
        if value is None:
            self.stats.misses += 1
        else:
            self.stats.hits += 1
        return value

    def put(self, key: CacheKey, value: object) -> None:
        if not self.enabled:
            return
        if key not in self._store:
            self._order.append(key)
            self.stats.stores += 1
        self._store[key] = value
        while len(self._order) > self.capacity:
            evicted = self._order.pop(0)
            self._store.pop(evicted, None)
            self.stats.evictions += 1

    def clear(self) -> None:
        self._store.clear()
        self._order.clear()
        self.stats = CacheStats()

    def __len__(self) -> int:
        return len(self._store)
