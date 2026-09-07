# C5 OnFly at a 240 s horizon, against the classical baseline — 2026-09-04

## Question

The retained five-seed result (1/5 at a 90 s horizon) was consistent with two
different explanations: the architecture cannot route around obstacles, or it
simply ran out of path budget trying. Raising the horizon separates them.

## Setup

- Architecture: `c5_onfly_qwen4_native_dynamics`, unchanged
- Classical reference: `c0` (oracle semantic goal to SUPER execution)
- Environment: `grid_nav_onfly_native_long` — identical to
  `grid_nav_onfly_native_dynamics` except `max_episode_s` and
  `max_flight_time_s` raised from 90 s to 240 s
- Seeds 1060-1064; held-out seeds 1-40 untouched
- Path budget: 0.6 m/s x 240 s = 144 m for a 35 m straight-line task (was 54 m)

## Result

**1/5 at 240 s — identical to 1/5 at 90 s.** The extra 150 seconds changed no
outcome.

| seed | occluders on ray | c0 | C5 | closest | final | freeze | held | from home | geofence refusals |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1060 | 2 | 68 s | timeout | 24.55 m | 69.47 m | 143 s | 97 s | 55.3 m | 99/239 |
| 1061 | 1 | 67 s | **success, 85 s** | 0.55 m | 0.55 m | — | — | 34.8 m | **0/85** |
| 1062 | 3 | 63 s | timeout | 24.52 m | 75.74 m | 132 s | 108 s | 56.1 m | 110/239 |
| 1063 | 2 | 83 s | timeout | 19.53 m | 36.54 m | 109 s | 131 s | 55.5 m | 133/239 |
| 1064 | **0** | 84 s | timeout | 25.80 m | 89.43 m | 151 s | 89 s | 55.7 m | 91/239 |

The classical baseline solves **5/5** in 63-84 s.

## The failure is a geofence deadlock

Every failing seed ends frozen — zero commanded speed, unchanging position — for
the last 89-131 seconds of the episode, at 55.3-56.1 m from home inside a 60 m
geofence. During each freeze the verifier refuses **every** proposal, and every
refusal names the same cause:

> target is 62.1 m from home, outside the 60 m geofence

At 55 m from home with the policy's 7 m maximum reach, any outward waypoint
lands at about 62 m and is correctly refused. The decision agent keeps proposing
outward, the verifier keeps refusing, and no component turns the vehicle around.

Two independently measured defects compose here. The decision agent's chosen `u`
has median 116 against an image centre of 112, with 59% of commands within 10
degrees of straight ahead — it proposes "ahead" almost always. At the fence,
ahead is always inadmissible. A policy that could steer would escape; a
fence-aware fallback would also escape; C5 has neither.

## What this rules out

**Path budget.** The failures used 78-90 m of a 144 m budget. They were not
short of time; they were stationary for 38-60% of all control ticks.

**Obstacle routing.** Seed 1064 has a completely clear line of sight to the
target and fails identically. An earlier reading that outcome tracked occluder
count (D-64) is contradicted by this seed and is withdrawn.

**Search and viewpoint selection.** The target is dead ahead at 35 m on every
seed, so there is nothing to search for; the correct opening action is to fly
straight. Work aimed at coverage or viewpoint choice (D-55, D-60) was addressing
a problem these seeds do not pose.

## What this establishes

Geofence refusal separates the five seeds perfectly: zero refusals on the
success, 91-133 on every failure.

And where the architecture stays inside the fence it is competent. Seed 1061
reaches the target in 85 s against the classical baseline's 67 s — 1.27x the
time of a planner that already knows the goal position — with 6% stationary
ticks against 38-60% in the deadlocked seeds.

## Open decision

The deadlock is a genuine defect with an obvious remedy (a fallback when every
proposal is refused for the geofence). Whether to fix it or to report it as a
measured limitation of the architecture is a paper decision and has not been
taken. No fix was attempted. Evidence: D-64 and D-65 in `docs/RESEARCH_LOG.md`;
runs under `runs/c5_long_s*` and `runs/c0_long_s*`.
