"""A bounded, process-local store for rendered frames.

`ObservationPacket` deliberately carries a *reference* to imagery rather than the
imagery itself, so that an observation stays cheap to log, hash and compare. But
a real vision model needs the actual pixels, so something has to resolve the
reference. This is that something.

It is intentionally small and bounded. Holding every frame of a 90-second
episode at 20 Hz would be 1800 images per run, and a sweep would exhaust memory
long before it exhausted seeds. Only the recent window is retained, which is all
any policy can legitimately use: a decision made from a frame older than the
staleness bound is rejected by the router anyway.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

DEFAULT_CAPACITY = 64


class FrameStore:
    """Maps a ``SensorRef.uri`` to the image behind it."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self.capacity = capacity
        self._frames: OrderedDict[str, Any] = OrderedDict()
        self.stores = 0
        self.hits = 0
        self.misses = 0

    def put(self, uri: str, image: Any) -> None:
        self._frames[uri] = image
        self._frames.move_to_end(uri)
        self.stores += 1
        while len(self._frames) > self.capacity:
            self._frames.popitem(last=False)

    def get(self, uri: str) -> Any | None:
        image = self._frames.get(uri)
        if image is None:
            self.misses += 1
        else:
            self.hits += 1
        return image

    def clear(self) -> None:
        self._frames.clear()
        self.stores = self.hits = self.misses = 0

    def __len__(self) -> int:
        return len(self._frames)


_GLOBAL = FrameStore()


def global_store() -> FrameStore:
    """The store the environment writes to and vision plugins read from.

    Process-global because the environment and the policy are deliberately not
    allowed to hold references to each other — a policy that could reach the
    environment could reach ground truth. Routing pixels through a keyed store
    keeps the only shared channel a content-addressed one.
    """
    return _GLOBAL
