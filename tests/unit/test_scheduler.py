"""Deterministic periodic scheduling contracts."""

from __future__ import annotations

import asyncio

from uavlab.contracts import s_to_ns
from uavlab.core.clock import SimClock
from uavlab.core.config import SchedulerSpec
from uavlab.core.scheduler import Scheduler


async def _advance_by(clock: SimClock, dt_s: float) -> None:
    task = asyncio.create_task(clock.sleep(dt_s))
    await asyncio.sleep(0)
    assert clock.advance()
    await task


def test_tick_waits_only_for_remainder_of_start_to_start_period():
    async def scenario() -> None:
        clock = SimClock()
        scheduler = Scheduler(SchedulerSpec(decision_hz=2.0), clock)
        decision = next(
            schedule
            for schedule in scheduler.build(has_monitor=False, has_recovery=False)
            if schedule.role == "decision"
        )

        # Work occupied 0.2 s of a 0.5 s period.
        await _advance_by(clock, 0.2)
        tick = asyncio.create_task(scheduler.tick(decision))
        await asyncio.sleep(0)
        assert clock.advance()
        await tick

        assert clock.now_ns() == s_to_ns(0.5)

    asyncio.run(scenario())


def test_tick_does_not_add_a_period_after_inference_overrun():
    async def scenario() -> None:
        clock = SimClock()
        scheduler = Scheduler(SchedulerSpec(decision_hz=2.0), clock)
        decision = next(
            schedule
            for schedule in scheduler.build(has_monitor=False, has_recovery=False)
            if schedule.role == "decision"
        )

        # A 2.2 s model call already exceeded the 0.5 s period. The next
        # invocation starts now rather than at 2.7 s.
        await _advance_by(clock, 2.2)
        await scheduler.tick(decision)

        assert clock.now_ns() == s_to_ns(2.2)
        assert decision.next_deadline_ns == s_to_ns(2.7)

    asyncio.run(scenario())
