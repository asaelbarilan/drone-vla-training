"""Shared machinery for semantic policies.

Everything here is about *fairness*, not about capability.  Every policy builds
its envelope the same way, times it the same way, forms its belief about the
target the same way, and explores the same way when it has no belief.  What
differs between architectures is where authority sits, when reasoning runs, and
what is remembered — which is the only thing the study wants to vary.

These are simulated policies.  They stand in for LLM/VLM/VLA components so that
the runtime, the contracts, the scheduling and the metrics can be validated
before a single real model is integrated.  Numbers produced with them describe
the *harness*, not the literature.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any

from uavlab.contracts import (
    DecisionEnvelope,
    DecisionKind,
    MemoryItem,
    MissionSpec,
    Vec3,
    s_to_ns,
)
from uavlab.core.services import RuntimeServices
from uavlab.interfaces import DecisionContext, InferenceRequest


def recall_target(
    ctx: DecisionContext, target_label: str, kinds: frozenset[str] | None = None
) -> MemoryItem | None:
    """Retrieve the most salient *matching* memory of the target.

    Filtering by label is not optional.  Retrieval by salience alone returns
    whichever landmark was seen closest and largest, and a nearby distractor
    beats the true target every time — the vehicle then flies confidently to the
    wrong object while every component reports success.

    ``kinds`` filters by provenance. Most items in a memory store come from
    ``perception.detections``, i.e. from the simulated detector. A policy whose
    premise is that a real model does the perceiving must pass
    ``kinds=frozenset({"decision"})`` so that it recalls only what it concluded
    itself; otherwise it recovers the detector's sightings through memory and
    the configuration stops measuring what it claims to.
    """
    return max(
        (
            item
            for item in ctx.memory.items
            if item.position is not None
            and item.salience > 0.0
            and item.label == target_label
            and (kinds is None or item.kind in kinds)
        ),
        key=lambda item: item.salience,
        default=None,
    )


@dataclass(slots=True)
class TargetBelief:
    """What the policy currently thinks the target is, and on what basis."""

    position: Vec3 | None
    confidence: float
    source: str
    """``detection`` | ``memory`` | ``privileged`` | ``none``."""

    @property
    def known(self) -> bool:
        return self.position is not None


class BasePolicy:
    """Common lifecycle, belief formation, timing and exploration."""

    role = "policy"

    def __init__(self, **params: Any) -> None:
        self.model_id = str(params.get("model_id", "sim-policy"))
        self.use_memory = bool(params.get("use_memory", True))
        self.follow_directives = bool(params.get("follow_directives", True))
        """Whether this executor consumes a slow reasoner's target hint.

        Setting it false makes an architecture *flat* even when a reasoner is
        scheduled, which is the honest way to ablate hierarchy without also
        removing the reasoner's compute cost.
        """
        self.target_label = str(params.get("target_label", "target"))
        self.stop_radius_m = float(params.get("stop_radius_m", 2.0))
        self.self_terminate = bool(params.get("self_terminate", True))
        self.stop_confidence = float(params.get("stop_confidence", 0.35))
        self.sensor_range_m = float(params.get("sensor_range_m", 45.0))
        self.sensor_fov_deg = float(params.get("sensor_fov_deg", 90.0))
        """The vehicle's own camera spec, used to size the search lanes.

        Declared here rather than read from the environment. A policy
        legitimately knows what camera it is carrying — that is a property of
        the airframe, not of the scene — but reaching into the environment for
        it would be a channel through which anything else could follow.

        If these disagree with the environment the sweep is merely mis-sized,
        which shows up as a worse score rather than as a silent advantage.
        """
        self.search_altitude_m = float(params.get("search_altitude_m", 0.0))
        """Altitude to search from. 0 keeps whatever altitude the vehicle is at.

        A search pattern is a plan over the *ground*, and flying it at cruise
        altitude threads the vehicle between obstacles rather than over them.
        Measured on grid_nav: obstacles top out at 11.1 m, the mission permits
        25 m, and the vehicle searched at 3.0 m — below every obstacle in the
        scene. With the target at z=2.9 m and 35 m away, every sight line
        crossed a tower, which is why coverage at any lane spacing acquired
        nothing.

        Climbing is not a trick: altitude is inside the mission's stated band,
        and trading it for sight lines is the ordinary reason survey aircraft
        fly high. It costs approach time, which is what makes it a real
        architectural choice rather than a free win.
        """
        self.sweep_overlap = float(params.get("sweep_overlap", 0.8))
        """Lane pitch as a fraction of the view width at half sensor range.

        Lower means more, closer lanes. It is a coverage knob, not a detection
        knob: with a target the vehicle can already range but cannot see past an
        obstacle, tightening this changes nothing.
        """
        self.search_pattern = str(params.get("search_pattern", "spiral"))
        """`spiral` (default) or `sweep`.

        The spiral was the original and is measurably bad. It is anchored at
        launch with the heading advancing on a clock, so the vehicle circles at
        roughly constant radius with a body-fixed camera pointing tangentially.
        Measured on grid_nav seed 3: c2 detected the target in 0 of 104 belief
        queries, while c7 — which yaws continuously — detected it in 70 of 132
        in the same scene, with the target inside sensor range throughout.

        `sweep` is a boustrophedon over the mission's stated geofence, ported
        from drone_control, where the same argument was settled by measurement:
        frontier and spiral searches exist for *unknown* extent, and when the
        extent is known coverage planning applies and is provably complete.
        See `plugins/reasoning/coverage.py`.

        **`spiral` remains the default, because `sweep` has not earned it.**
        Measured on grid_nav seed 3, c2: spiral ends 33.2 m out over a 368 m
        path, sweep 36.4 m over 312 m, and *neither acquires the target at all*
        — 0 of 104 belief queries either way, at every lane spacing from 25.5 m
        down to 4.8 m.

        The reason is not coverage. Instrumenting the geometry: for c2 the
        target is within sensor range on 100% of ticks and within the field of
        view on 43%, and on **100%** of those it is occluded by an obstacle. For
        c7, which flies toward it, the same figure is 13%. The blocker is line
        of sight, and no lane pattern fixes line of sight. drone_control reached
        the same conclusion from the other direction: the objective is
        "observed", not "flown over".
        """
        self.explore_step_m = float(params.get("explore_step_m", 8.0))
        self.explore_turn_rad = float(params.get("explore_turn_rad", math.radians(50.0)))
        self.explore_dwell_s = float(params.get("explore_dwell_s", 0.0))
        """Seconds committed to one search leg before turning. 0 derives it.

        Held on a clock, not per decision, so search coverage is not a function
        of decision rate — a 10 Hz executor must not sweep ten times faster than
        a 1 Hz skill agent for reasons nobody chose.

        **It was a fixed 3.0 s, and that number was the single largest defect in
        the scripted search.** The leg must be long enough to fly, and it was
        not: the heading advances 50 deg every dwell, so consecutive commanded
        points are a chord apart, and at the geofence radius that chord is 45 m
        — 9 s of flight at the mission's 5 m/s. Given 3 s the vehicle got a third
        of the way, the target moved on, and the net motion cancelled.

        Measured on c2, grid_nav seed 3: the search commanded points up to 54 m
        from launch while the vehicle never exceeded **21.5 m** and oscillated
        between 6 and 21 m for the entire episode. It was not searching, it was
        chasing a point that outran it.

        Deriving it from the mission's own geometry — chord length over permitted
        speed — makes the leg completable by construction, and keeps the value
        identical across architectures because it depends on nothing an
        architecture chooses. Setting it explicitly overrides the derivation.
        """
        self.explore_growth = float(params.get("explore_growth", 0.55))
        """How much the search radius grows per leg, as a fraction of the step."""
        self.validity_s = float(params.get("validity_s", 2.0))
        self.services: RuntimeServices | None = None
        self._explore_base_yaw: float | None = None
        self._explore_anchor: Vec3 | None = None
        self._decisions = 0
        self._stopped = False
        self._geofence_m = 100.0
        self._min_alt = 0.5
        self._max_alt = 30.0

    @property
    def name(self) -> str:
        return "base"

    @property
    def emits(self) -> tuple[str, ...]:
        return ()

    def bind_runtime(self, services: RuntimeServices) -> None:
        self.services = services

    def reset(self, mission: MissionSpec, seed: int) -> None:
        self._explore_base_yaw = None
        self._explore_anchor = None
        self._sweep = None
        self._derived_dwell_s = self.explore_dwell_s or 3.0
        self._decisions = 0
        self._stopped = False
        self._geofence_m = mission.constraints.geofence_radius_m
        self._min_alt = mission.constraints.min_altitude_m
        self._max_alt = mission.constraints.max_altitude_m
        if self.explore_dwell_s <= 0.0:
            # Chord between consecutive search points at the widest radius the
            # spiral reaches, over the speed the mission permits. Both are given
            # constraints, so this is derived rather than tuned.
            radius = self._geofence_m * 0.9
            chord = 2.0 * radius * math.sin(self.explore_turn_rad / 2.0)
            speed = max(mission.constraints.max_speed_mps, 0.1)
            self._derived_dwell_s = max(chord / speed, 1.0)
        else:
            self._derived_dwell_s = self.explore_dwell_s

    # -- belief -------------------------------------------------------------

    def believe(self, ctx: DecisionContext) -> TargetBelief:
        """Form a target belief from privileged truth, detections, then memory.

        The ordering is the interesting part.  A policy without memory falls off
        the end of this chain the moment the target leaves the field of view,
        which is precisely the failure mode compact history is supposed to fix.
        """
        privileged = ctx.observation.privileged
        if privileged is not None and "goal" in privileged:
            gx, gy, gz = privileged["goal"]  # type: ignore[misc]
            return TargetBelief(Vec3(x=float(gx), y=float(gy), z=float(gz)), 1.0, "privileged")

        best = None
        for det in ctx.perception.detections:
            if det.label != self.target_label or det.position is None:
                continue
            if best is None or det.score > best.score:
                best = det
        if best is not None and best.position is not None:
            return TargetBelief(best.position, float(best.score), "detection")

        # A slow reasoner's hint outranks the executor's own memory: that is the
        # whole justification for paying for the second, slower semantic loop.
        directive = ctx.last_directive
        if self.follow_directives and directive is not None and directive.target_hint is not None:
            return TargetBelief(directive.target_hint, 0.7, "directive")

        if self.use_memory:
            remembered = recall_target(ctx, self.target_label)
            if remembered is not None and remembered.position is not None:
                # Remembered evidence is worth less than a live detection, and
                # saying so keeps "confident because I once saw it" out of the
                # stopping decision.
                return TargetBelief(remembered.position, float(remembered.salience) * 0.8, "memory")

        return TargetBelief(None, 0.0, "none")

    def _explore_leg(self, ctx: DecisionContext) -> int:
        return int(ctx.t_sim_ns / max(s_to_ns(self._derived_dwell_s), 1))

    def explore_heading(self, ctx: DecisionContext) -> float:
        """Search heading, advanced on a clock rather than per decision.

        This matters for fairness, not just for behaviour.  If the heading
        advanced once per decision, a 10 Hz executor would sweep ten times
        faster than a 1 Hz skill agent purely because of its decision rate, and
        the authority comparison would be quietly contaminated by an
        exploration-rate difference that nobody chose.
        """
        if self._explore_base_yaw is None:
            self._explore_base_yaw = ctx.observation.yaw_rad
        return self._explore_base_yaw + self._explore_leg(ctx) * self.explore_turn_rad

    def explore_target(self, ctx: DecisionContext) -> Vec3:
        """The next place to look. Sweep by default; see `search_pattern`."""
        if self.search_pattern == "sweep":
            return self._sweep_target(ctx)
        return self._spiral_target(ctx)

    def _sweep_target(self, ctx: DecisionContext) -> Vec3:
        """Boustrophedon lane coverage of the mission's operating volume.

        Sized from the mission's own geofence and the sensor model it publishes,
        so nothing here is privileged: both are given constraints, and a search
        that leaves its stated volume measures the harness rather than the
        architecture.
        """
        from uavlab.plugins.reasoning.coverage import sweep_for_mission

        if self._sweep is None:
            self._sweep = sweep_for_mission(
                self._geofence_m, self.sensor_range_m, self.sensor_fov_deg,
                self.sweep_overlap,
            )
        p = ctx.observation.position
        self._sweep.note_arrival(p.x, p.y)
        waypoint = self._sweep.next_waypoint(p.x, p.y)
        if waypoint is None:
            # Every lane covered and still nothing found. Start again rather
            # than stopping: the target may have been occluded on the first pass,
            # and a policy that gives up scores the same as one that never looked.
            self._sweep.reset()
            waypoint = self._sweep.next_waypoint(p.x, p.y) or (p.x, p.y)
        altitude = self.search_altitude_m or p.z
        return Vec3(
            x=float(waypoint[0]),
            y=float(waypoint[1]),
            z=min(self._max_alt, max(self._min_alt, altitude)),
        )

    def _spiral_target(self, ctx: DecisionContext) -> Vec3:
        """Outward spiral anchored to the launch point.

        The anchor matters.  Offsetting from the *current* position each tick
        produces a circle of fixed radius around wherever the vehicle happens to
        be: it turns continuously, never gets further from home, and searches
        nothing.  Anchoring to the start and growing the radius per leg is what
        makes this an actual search pattern.

        Clamped to the mission's stated geofence and altitude band.  Those are
        given constraints, not privileged information, so respecting them is not
        cheating — and a policy that leaves its operating volume is measuring the
        harness rather than the architecture.
        """
        if self._explore_anchor is None:
            self._explore_anchor = ctx.observation.position
        anchor = self._explore_anchor
        heading = self.explore_heading(ctx)
        leg = self._explore_leg(ctx)
        radius = min(
            self._geofence_m * 0.9,
            self.explore_step_m * (1.0 + leg * self.explore_growth),
        )
        return Vec3(
            x=anchor.x + radius * math.cos(heading),
            y=anchor.y + radius * math.sin(heading),
            z=min(self._max_alt, max(self._min_alt, anchor.z)),
        )

    def should_stop(self, belief: TargetBelief, ctx: DecisionContext) -> bool:
        """Terminal intent from the policy's own evidence.

        Note what this does *not* use: ground truth.  A policy stops when it
        believes it has arrived, and whether that belief was right is scored
        afterwards from the environment.  That gap is exactly what an
        independent progress monitor is supposed to close.
        """
        if not self.self_terminate or self._stopped or not belief.known:
            return False
        if belief.confidence < self.stop_confidence:
            return False
        assert belief.position is not None
        return ctx.observation.position.distance_to(belief.position) <= self.stop_radius_m

    # -- timing -------------------------------------------------------------

    async def charge(self, ctx: DecisionContext, role: str | None = None, images: int = 1) -> None:
        """Charge this call's simulated compute to the shared clock."""
        if self.services is None or self.services.inference is None:
            return
        await self.services.inference.invoke(
            InferenceRequest(
                model_id=self.model_id,
                role=role or self.role,
                prompt_hash=f"{self.name}:{ctx.observation.seq}",
                input_tokens=64 + ctx.memory.tokens_used,
                image_count=images,
                observation_seq=ctx.observation.seq,
            )
        )

    def envelope(
        self,
        ctx: DecisionContext,
        kind: DecisionKind,
        payload: Any,
        confidence: float,
        note: str = "",
        extra: dict[str, str] | None = None,
    ) -> DecisionEnvelope:
        """Build the envelope, stamping observation time and production time.

        ``source_t_sim_ns`` is the *observation's* timestamp, not now.  Recording
        it here is what lets the router measure how obsolete the world had become
        by the time this decision reached the vehicle.
        """
        now_ns = self.services.clock.now_ns() if self.services else ctx.t_sim_ns
        wall_ns = self.services.clock.wall_ns() if self.services else ctx.t_wall_ns
        self._decisions += 1
        return DecisionEnvelope(
            decision_id=uuid.uuid4().hex[:12],
            kind=kind,
            payload=payload,
            source_observation_seq=ctx.observation.seq,
            source_t_sim_ns=ctx.observation.t_sim_ns,
            produced_t_wall_ns=wall_ns,
            produced_t_sim_ns=now_ns,
            valid_until_t_sim_ns=now_ns + s_to_ns(self.validity_s),
            confidence=confidence,
            producer=self.name,
            provenance={
                "model_id": self.model_id,
                **({"note": note} if note else {}),
                **(extra or {}),
            },
        )
