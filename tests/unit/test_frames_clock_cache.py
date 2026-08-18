"""Frames, the simulation clock, and the feature cache.

These three are the quiet ones. A frame bug inverts conclusions while every test
still passes; a clock bug makes every timing result a property of the machine;
a cache-key bug hands one model another model's features.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from uavlab.contracts import Frame, Vec3, s_to_ns
from uavlab.core.clock import HarnessError, SimClock, pump_until_done
from uavlab.core.feature_cache import FeatureCache
from uavlab.core.frames import (
    body_to_enu,
    convert,
    enu_to_body,
    enu_to_ned,
    ned_to_enu,
    wrap_angle,
    yaw_enu_to_ned,
    yaw_ned_to_enu,
)


# -- frames -----------------------------------------------------------------


def test_enu_ned_axis_mapping():
    """ENU (East, North, Up) -> NED (North, East, Down)."""
    v = Vec3(x=1.0, y=2.0, z=3.0, frame=Frame.ENU)
    n = enu_to_ned(v)
    assert (n.x, n.y, n.z) == (2.0, 1.0, -3.0)
    assert n.frame is Frame.NED


def test_enu_ned_roundtrip_is_exact():
    v = Vec3(x=-4.5, y=0.25, z=11.0, frame=Frame.ENU)
    assert ned_to_enu(enu_to_ned(v)) == v


def test_frame_conversion_refuses_wrong_input_frame():
    with pytest.raises(ValueError, match="expected an ENU vector"):
        enu_to_ned(Vec3(x=1.0, y=0.0, z=0.0, frame=Frame.NED))


def test_yaw_conversion_roundtrip():
    for yaw in (-3.0, -1.0, 0.0, 0.5, 2.5, 3.1):
        assert yaw_ned_to_enu(yaw_enu_to_ned(yaw)) == pytest.approx(wrap_angle(yaw))


def test_yaw_known_values():
    # ENU yaw 0 is due East, which is a NED heading of 90 degrees.
    assert yaw_enu_to_ned(0.0) == pytest.approx(math.pi / 2)
    # ENU yaw 90 degrees is due North, which is NED heading 0.
    assert yaw_enu_to_ned(math.pi / 2) == pytest.approx(0.0)


def test_body_to_enu_uses_yaw():
    forward = Vec3(x=1.0, y=0.0, z=0.0, frame=Frame.BODY)
    rotated = body_to_enu(forward, math.pi / 2)
    assert rotated.x == pytest.approx(0.0, abs=1e-9)
    assert rotated.y == pytest.approx(1.0)
    assert enu_to_body(rotated, math.pi / 2).x == pytest.approx(1.0)


def test_convert_rejects_undefined_pairs():
    v = Vec3(x=1.0, y=0.0, z=0.0, frame=Frame.ENU)
    assert convert(v, Frame.ENU) is v
    assert convert(v, Frame.NED).frame is Frame.NED


# -- clock ------------------------------------------------------------------


def test_clock_advances_to_the_earliest_pending_wakeup():
    async def scenario():
        clock = SimClock()
        order: list[tuple[str, int]] = []
        stop = asyncio.Event()

        async def role(name: str, period_s: float, ticks: int):
            try:
                for _ in range(ticks):
                    order.append((name, clock.now_ns()))
                    await clock.sleep(period_s, role=name)
            finally:
                clock.unregister_role(name)

        # Registration happens before the tasks exist, exactly as the
        # orchestrator does it.
        clock.register_role("fast")
        clock.register_role("slow")
        tasks = [
            asyncio.create_task(role("fast", 0.1, 5)),
            asyncio.create_task(role("slow", 0.25, 2)),
        ]
        await pump_until_done(clock, stop, max_sim_ns=s_to_ns(10.0))
        await asyncio.gather(*tasks, return_exceptions=True)
        return order

    order = asyncio.run(scenario())
    fast_times = [t for n, t in order if n == "fast"]
    slow_times = [t for n, t in order if n == "slow"]
    assert fast_times == [0, s_to_ns(0.1), s_to_ns(0.2), s_to_ns(0.3), s_to_ns(0.4)]
    assert slow_times == [0, s_to_ns(0.25)]


def test_clock_runs_roles_concurrently_in_simulated_time():
    """A slow role must not stop a fast one from ticking meanwhile."""

    async def scenario():
        clock = SimClock()
        fast_ticks = 0
        stop = asyncio.Event()

        async def fast():
            nonlocal fast_ticks
            try:
                for _ in range(10):
                    fast_ticks += 1
                    await clock.sleep(0.1, role="fast")
            finally:
                clock.unregister_role("fast")

        async def slow():
            try:
                await clock.sleep(0.9, role="slow")  # one expensive inference
            finally:
                clock.unregister_role("slow")

        clock.register_role("fast")
        clock.register_role("slow")
        tasks = [asyncio.create_task(fast()), asyncio.create_task(slow())]
        await pump_until_done(clock, stop, max_sim_ns=s_to_ns(5.0))
        await asyncio.gather(*tasks, return_exceptions=True)
        return fast_ticks

    assert asyncio.run(scenario()) == 10


def test_clock_never_moves_backwards():
    clock = SimClock(start_ns=s_to_ns(5.0))
    assert clock.now_ns() == s_to_ns(5.0)
    assert clock.advance() is False  # nothing pending


def test_pump_detects_a_role_that_never_parks():
    """A busy-looping role must fail loudly, not stall the run silently."""

    async def scenario():
        clock = SimClock()
        stop = asyncio.Event()
        clock.register_role("greedy")

        async def greedy():
            while not stop.is_set():
                await asyncio.sleep(0)  # yields, but never to the simulation clock

        task = asyncio.create_task(greedy())
        try:
            await pump_until_done(clock, stop, max_sim_ns=s_to_ns(1.0), max_spins=50)
        finally:
            stop.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    with pytest.raises(HarnessError, match="never parked"):
        asyncio.run(scenario())


def test_negative_sleep_is_a_harness_error():
    async def scenario():
        clock = SimClock()
        await clock.sleep_ns(-1, role="x")

    with pytest.raises(HarnessError, match="negative sleep"):
        asyncio.run(scenario())


# -- feature cache ----------------------------------------------------------


def test_feature_cache_is_disabled_by_default():
    """Sharing must be off during the first causal architecture comparison."""
    cache = FeatureCache()
    assert cache.enabled is False
    key = FeatureCache.key("m", "vit", 3, "prep")
    cache.put(key, object())
    assert cache.get(key) is None
    assert len(cache) == 0


def test_feature_cache_key_includes_every_component():
    a = FeatureCache.key("model_a", "vit", 3, "prep")
    b = FeatureCache.key("model_b", "vit", 3, "prep")
    c = FeatureCache.key("model_a", "vit2", 3, "prep")
    d = FeatureCache.key("model_a", "vit", 4, "prep")
    e = FeatureCache.key("model_a", "vit", 3, "other")
    assert len({a, b, c, d, e}) == 5, "every key component must affect the cache key"


def test_feature_cache_evicts_and_reports():
    cache = FeatureCache(enabled=True, capacity=2)
    for i in range(3):
        cache.put(FeatureCache.key("m", "vit", i, "p"), i)
    assert len(cache) == 2
    assert cache.get(FeatureCache.key("m", "vit", 0, "p")) is None  # evicted
    assert cache.get(FeatureCache.key("m", "vit", 2, "p")) == 2
    stats = cache.stats.as_dict()
    assert stats["feature_cache_evictions"] == 1.0
    assert stats["feature_cache_hits"] == 1.0
