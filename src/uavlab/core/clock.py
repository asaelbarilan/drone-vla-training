"""Injectable simulation clock and a deterministic virtual-time driver.

Why this exists
---------------
Half the architecture axes in this study are *timing* axes: periodic versus
asynchronous reasoning, fast executor under a slow reasoner, monitor rate,
action horizon.  Measuring those on a real wall clock would make every result a
function of the machine that produced it, and would make "asynchronous" mean
"whatever the OS scheduler did that afternoon".

So simulation time is explicit and virtual.  A role that spends 800 ms of model
inference *says so*, the clock advances by 800 ms, and other roles genuinely
continue during that interval.  Runs are then both concurrent and reproducible,
and ``decision_age`` means something.

How the driver works
--------------------
Every concurrently scheduled role registers with the clock.  A role only ever
blocks by awaiting :meth:`SimClock.sleep_ns`, which parks it.  The pump yields
to the event loop until every live role is parked, then jumps simulation time
to the earliest pending wake-up.  No wall-clock sleeping ever occurs, so a
120-second mission runs in milliseconds.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

from uavlab.contracts.common import NANOS_PER_SECOND, s_to_ns

CURRENT_ROLE: ContextVar[str] = ContextVar("uavlab_current_role", default="")
"""The scheduled role owning the current task.

Set once per role task.  It lets a plugin deep in the call stack — a simulated
inference backend, say — charge its compute to the correct role without every
interface having to pass the role name down.  Inline supervision inherits the
decision loop's role, which is exactly right: an inline reasoner blocks the
decision loop, and the parking accounting should say so.
"""


class HarnessError(RuntimeError):
    """Raised when the *test rig* misbehaves, not the system under test.

    A harness that quietly produces plausible numbers is worse than one that
    crashes, so every internal invariant here is fatal rather than warned.
    """


@dataclass(order=True)
class _Waiter:
    wake_ns: int
    seq: int
    future: asyncio.Future = field(compare=False)
    role: str = field(compare=False, default="")


class WallClock:
    """Real wall-clock source, isolated so tests can freeze it."""

    def now_ns(self) -> int:
        return time.perf_counter_ns()


class FrozenWallClock(WallClock):
    """Wall clock that advances only when told. Used by deterministic tests."""

    def __init__(self, start_ns: int = 0) -> None:
        self._now = start_ns

    def now_ns(self) -> int:
        return self._now

    def advance_ns(self, dt_ns: int) -> None:
        self._now += dt_ns


class SimClock:
    """Virtual simulation time with cooperative parking."""

    def __init__(self, start_ns: int = 0, wall: WallClock | None = None) -> None:
        self._now = start_ns
        self._wall = wall or WallClock()
        self._waiters: list[_Waiter] = []
        self._counter = itertools.count()
        self._live_roles: set[str] = set()
        self._parked_roles: set[str] = set()
        self._advances = 0

    # -- time ---------------------------------------------------------------

    def now_ns(self) -> int:
        return self._now

    def now_s(self) -> float:
        return self._now / NANOS_PER_SECOND

    def wall_ns(self) -> int:
        return self._wall.now_ns()

    # -- role bookkeeping ---------------------------------------------------

    def register_role(self, role: str) -> None:
        if role in self._live_roles:
            raise HarnessError(f"role {role!r} registered twice")
        self._live_roles.add(role)

    def unregister_role(self, role: str) -> None:
        self._live_roles.discard(role)
        self._parked_roles.discard(role)

    @property
    def live_roles(self) -> frozenset[str]:
        return frozenset(self._live_roles)

    @property
    def all_parked(self) -> bool:
        """True when no live role can make progress without time advancing."""
        return self._live_roles <= self._parked_roles

    # -- blocking -----------------------------------------------------------

    async def sleep_ns(self, dt_ns: int, role: str = "") -> None:
        """Park the caller for ``dt_ns`` of simulation time."""
        if dt_ns < 0:
            raise HarnessError(f"negative sleep of {dt_ns} ns from role {role!r}")
        role = role or CURRENT_ROLE.get()
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        waiter = _Waiter(self._now + dt_ns, next(self._counter), future, role)
        heapq.heappush(self._waiters, waiter)
        if role:
            self._parked_roles.add(role)
        try:
            await future
        finally:
            if role:
                self._parked_roles.discard(role)

    async def sleep(self, dt_s: float, role: str = "") -> None:
        await self.sleep_ns(s_to_ns(dt_s), role=role)

    # -- driving ------------------------------------------------------------

    def advance(self) -> bool:
        """Jump to the earliest pending wake-up and release everything due.

        Returns False when nothing is pending, which means the episode's roles
        have all finished and the pump can stop.
        """
        if not self._waiters:
            return False
        target = self._waiters[0].wake_ns
        if target < self._now:
            raise HarnessError(
                f"clock would move backwards: pending {target} < now {self._now}"
            )
        self._now = target
        self._advances += 1
        while self._waiters and self._waiters[0].wake_ns <= self._now:
            waiter = heapq.heappop(self._waiters)
            # Un-park at resolution time, not when the coroutine happens to
            # resume.  Otherwise the pump would still see the role as parked on
            # its next check and advance time again before the role had run —
            # which silently skips work and truncates the episode.
            if waiter.role:
                self._parked_roles.discard(waiter.role)
            if not waiter.future.done():
                waiter.future.set_result(None)
        return True

    def cancel_all(self) -> None:
        """Release every parked role so the episode can unwind."""
        while self._waiters:
            waiter = heapq.heappop(self._waiters)
            if not waiter.future.done():
                waiter.future.cancel()

    @property
    def advance_count(self) -> int:
        return self._advances


MAX_PUMP_SPINS = 10_000
"""Guard against a role that busy-loops without ever parking on the clock.

If this trips, the harness is broken (a role is awaiting something other than
simulation time), and the run must fail loudly rather than silently stall.
"""


async def pump_until_done(
    clock: SimClock,
    stop: asyncio.Event,
    *,
    max_sim_ns: int,
    max_spins: int = MAX_PUMP_SPINS,
) -> None:
    """Drive virtual time until the episode stops or the horizon is reached.

    Roles must be registered *before* this is called.  If registration happened
    inside each role coroutine, the pump would find no live roles on entry,
    conclude that everything was parked, find nothing pending, and return —
    leaving the roles to park on futures nobody will ever resolve.  That
    presents as a silent hang, so it is checked instead.
    """
    if not clock.live_roles:
        raise HarnessError(
            "pump_until_done called with no registered roles; register every "
            "concurrent role with clock.register_role() before creating its task"
        )
    while not stop.is_set():
        spins = 0
        while not clock.all_parked:
            await asyncio.sleep(0)
            spins += 1
            if stop.is_set():
                return
            if spins > max_spins:
                stuck = sorted(clock.live_roles - clock._parked_roles)
                raise HarnessError(
                    f"roles {stuck} never parked on the simulation clock after "
                    f"{max_spins} spins; a role is awaiting something other than "
                    "SimClock.sleep_ns, so virtual time cannot advance"
                )
        if stop.is_set():
            return
        if not clock.advance():
            return
        if clock.now_ns() >= max_sim_ns:
            return
