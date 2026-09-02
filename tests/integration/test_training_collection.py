from __future__ import annotations

import asyncio

from uavlab.core.compose import load_architecture, load_environment
from uavlab.training.dataset import collect_episode


def test_training_collection_resolves_the_frames_the_environment_rendered():
    """A rendered expert flight must produce aligned frame/action samples.

    Frame URIs are an internal boundary between the simulator and the training
    tools.  A namespace change once left successful flights with zero samples,
    so checking only mission success is not enough.
    """
    # This is a frame/action alignment test, not a capability test for the
    # scripted C2 placeholder. Use the declared oracle control ceiling so a
    # target that starts occluded cannot turn a tooling contract test into a
    # semantic-search result. C0's privilege remains explicit in its config.
    arch = load_architecture("c0")
    env = load_environment("grid_nav_vision")

    pairs, actions, success = asyncio.run(collect_episode(arch, env, seed=2, stride=2))

    assert success
    assert len(pairs) > 0
    assert len(actions) == len(pairs)
