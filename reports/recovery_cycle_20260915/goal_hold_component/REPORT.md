# D-120 accepted-goal execution: detour restores target view

The common SUPER planner/controller can execute a detour from the actual51s state
when the already accepted target-bound waypoint is kept. The red target reappears
by64s in sampled camera frames and remains visible through71s. Evaluation-only
true target distance decreases16.885→10.143m; no target truth steers execution.

The frozen primary endpoint did **not** pass: the stored intermediate waypoint is
not reached within20s. Distance to that waypoint starts5.282m, gets as close as
4.928m, and ends6.150m while the vehicle goes around the obstacle. It is a detour,
not a stationary stuck state. Do not call this mission success or proof that
holding a waypoint alone solves navigation. Original flight's distance to the
same stored point at71s is6.067m (closest3.976m during51–71s).

## What was held constant and verified

- Exact cycle2 seed1061 environment/config and goal accepted51s from sourceobs1000.
- Event-ordered replay:1,020 control poses and all61 original planner output point
  lists/feasibility flags match before the intervention. First branch velocity and
  yaw-rate command match. Planning uses the actual previous observation according
  to recorded event order, not the next control observation.
- Common SUPER replanned the same goal1Hz for20s; common controller ran20Hz.
  Twenty new plans all feasible, each with known-free stopping backup and
  reaches_goal=false. No collision; recorded minimum obstacle distance1.851m
  includes the prefix and therefore is not a branch-only clearance statistic.
- No VLM, monitor, replacement goals, or semantic freshness authorization occurs
  in the component. Bounded execution persistence is the explicit intervention.
  This is not a live architecture run and consumes no model-flight slot.
-21 camera/map seeks checked in Edge; actual dashboard and six-image camera
  sequence inspected. Current views show the obstacle on the left, travel around
  its right side, then red target reappearance. Full rows/plans and PNGs retained.

The stored goal center is only0.423m outside a simulator obstacle box (diagnostic
truth geometry). This is below the mission0.6m clearance requirement, but the goal
has1m tolerance: center clearance alone does not prove the goal region infeasible.
It may also explain why a center-distance endpoint is not a sufficient executor
assessment. Do not silently alter the goal or claim this proves a SUPER bug.

## Decision and next step

The component supports testing whether premature replacement of target intent
interrupts a useful local detour. It does not isolate replacement from the LOST
yaw action because both are absent in this execution-only component.

Next named extension: a bounded target-goal execution commitment, while normal
current-only VLM observations continue. During brief loss, keep the last accepted
model target waypoint for at most20s; allow a fresh visible-target goal to supersede
it. Preserve geometric planning/STOP checks. Do not manufacture fresh image
provenance for an old goal: use an explicit stored-goal authorization with original
source and bounded lifetime. LOST yaw recovery needs explicit ownership arbitration
with that commitment; test state transitions and expiry before one model flight.
Keep this separate from the native OnFly baseline and from D-117 observed-view
return. No temporal-prompt retuning of the three D-118/D-119 frames.

Code/freeze6cb9dc7. Flight slots2/4; saved-frame calls15. No model process started
for this component. D-118/D-119 memory-cadence correction remains in their reports.
Dashboard: http://127.0.0.1:8766/goal_hold.html
