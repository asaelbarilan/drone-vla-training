"""Injected failures must be survivable.

A recovery scenario is only a recovery scenario if recovery is possible. This
suite exists because it was not: `block_path` used to place its obstacle at the
midpoint between the vehicle and the goal, and by the time the failure fired the
vehicle was usually past that point — so the box materialised on top of a drone
at cruise speed.

That bug was invisible in aggregate. It hit every architecture equally, so the
table still looked like a plausible set of architecture results; it just made
`failure_recovery` measure "was the vehicle teleported into a wall" instead of
"can this architecture recover". The oracle control ceiling is what exposed it:
a configuration with perfect semantics has no business colliding 62% of the time.
"""

from __future__ import annotations

import asyncio

import pytest

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import ControlCommand, Vec3, s_to_ns
from uavlab.core.config import EpisodeSpec
from uavlab.core.orchestrator import Orchestrator

from tests.conftest import run_one

SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)


def test_injected_blockage_never_spawns_on_the_vehicle(arch_factory, env_factory):
    """The strict version: an injected box must never overlap the drone."""
    spawns: list[float] = []
    original = DeterministicEnv._apply_injections

    def patched(self, t_s):
        before = len(self.obstacles)
        original(self, t_s)
        for obstacle in self.obstacles[before:]:
            spawns.append(obstacle.distance(self.vehicle.position))

    DeterministicEnv._apply_injections = patched
    try:
        arch = arch_factory("c0")
        env = env_factory("failure_recovery")
        for seed in SEEDS:
            run_one(arch, env, seed=seed)
    finally:
        DeterministicEnv._apply_injections = original

    assert spawns, "no blockage was injected, so this test proved nothing"
    worst = min(spawns)
    assert worst > 0.4, (
        f"an injected obstacle spawned {worst:.2f} m from the vehicle centre "
        "(drone radius 0.4 m): it was placed on top of the drone"
    )


def test_injected_blockage_leaves_room_to_react(arch_factory, env_factory):
    """The useful version: it must be avoidable, not merely non-overlapping.

    At 5 m/s with a 1.2 s reaction allowance, anything closer than about 8 m is
    an unavoidable collision dressed up as a recovery test.
    """
    clearances: list[float] = []
    arch = arch_factory("c0")
    env = env_factory("failure_recovery")
    for seed in SEEDS:
        result, _ = run_one(arch, env, seed=seed)
        assert result.status is not None
        value = result.status.extras.get("min_injected_block_clearance_m", -1.0)
        if value >= 0.0:
            clearances.append(value)

    assert clearances, "no blockage clearance was recorded"
    assert min(clearances) >= 4.0, (
        f"closest injected blockage was {min(clearances):.2f} m away; a competent "
        "stack cannot stop or deflect in that distance at cruise speed"
    )


def test_the_oracle_survives_the_recovery_regime(arch_factory, env_factory):
    """The control-ceiling gate, applied to the regime that was broken.

    The spec's rule is that a weak oracle invalidates every architecture number
    measured in the same environment. That rule is what caught this bug, so it
    is enforced per regime rather than only on the easy one.
    """
    arch = arch_factory("c0")
    env = env_factory("failure_recovery")
    results = [run_one(arch, env, seed=seed)[0] for seed in SEEDS]
    collisions = sum(r.metrics["collision_rate"] for r in results) / len(results)
    successes = sum(r.success for r in results) / len(results)

    assert collisions <= 0.25, (
        f"the oracle collided in {collisions:.0%} of recovery episodes; the regime "
        "is punishing the flight stack, not the architecture"
    )
    assert successes >= 0.5, (
        f"the oracle reached the goal in only {successes:.0%} of recovery episodes"
    )


@pytest.mark.parametrize("env_name", ["grid_nav", "object_search", "failure_recovery",
                                      "fine_maneuver", "occlusion"])
def test_the_oracle_is_competent_in_every_regime(arch_factory, env_factory, env_name):
    """Generalises the ceiling gate across all five regimes.

    Previously this was asserted on `grid_nav` alone, which is how a broken
    regime survived: the ceiling was measured where nothing was wrong.
    """
    arch = arch_factory("c0")
    env = env_factory(env_name)
    results = [run_one(arch, env, seed=seed)[0] for seed in SEEDS]
    successes = sum(r.success for r in results) / len(results)
    collisions = sum(r.metrics["collision_rate"] for r in results) / len(results)
    assert collisions <= 0.25, (
        f"[{env_name}] oracle collision rate {collisions:.0%}: fix the substrate "
        "before reading any architecture result from this regime"
    )
    assert successes >= 0.5, (
        f"[{env_name}] oracle success {successes:.0%}: architecture numbers from "
        "this regime are not interpretable yet"
    )


def test_a_blockage_with_no_room_is_skipped_not_forced():
    """When there is no fair place to stage a blockage, stage none."""
    env = DeterministicEnv(
        failures=[{"kind": "block_path", "at_s": 0.0, "params": {"size_m": 4.0}}],
        goal_distance_m=6.0,  # goal is closer than any fair blockage distance
    )
    from uavlab.contracts import MissionSpec, TaskFamily

    mission = MissionSpec(
        mission_id="m", instruction="go", task_family=TaskFamily.FAILURE_RECOVERY
    )
    asyncio.run(env.reset(mission, 1))
    asyncio.run(env.step(ControlCommand(t_sim_ns=0, velocity=Vec3(x=1.0, y=0.0, z=0.0)),
                         s_to_ns(0.05)))
    assert env.status().extras["skipped_injections"] >= 1.0
    assert not any(o.label == "injected_block" for o in env.obstacles)
