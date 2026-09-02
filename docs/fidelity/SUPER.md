# SUPER fidelity record

Status: **accepted and frozen (2026-08-25)**. This record froze the mechanism
and acceptance gate before parameter tuning and now records the resulting
evidence.

## Sources inspected

- Ren et al., *Safety-assured high-speed navigation for MAVs*, Science
  Robotics 10, eado6187 (2025), DOI
  <https://doi.org/10.1126/SCIROBOTICS.ADO6187>.
- Official HKU-MaRS source repository,
  <https://github.com/hku-mars/SUPER>, commit
  `2ad3419c127a617c6d7df6925e81a14175a9c096`, inspected 2026-08-25.
- Archived paper/code record, <https://zenodo.org/records/14528604>.

The repository has no top-level licence file, but source headers state
LGPL-3.0-or-later. No official source is copied into this MIT repository; the
local implementation is an independent, interface-normalized reproduction of
the published mechanism.

## Paper-defining mechanism

At every replan SUPER produces an exploratory trajectory and, unless the
exploratory trajectory is wholly known-free, a backup trajectory. The
exploratory path may enter unknown space. Its committed prefix and the entire
backup must be known-free. The backup branches from a state on the exploratory
trajectory and terminates at rest. A failed or over-time replan preserves the
previous committed trajectory, whose backup therefore remains executable.

The official implementation supplies these parts:

1. a point-cloud map with spatial and temporal sliding;
2. A* with unknown treated as free for the exploratory front end;
3. path shortening into visible line seeds;
4. CIRI configuration-space safe corridors around those seeds;
5. smooth corridor-constrained polynomial trajectory optimization;
6. a known-free backup corridor from the current position to the farthest
   visible exploratory point;
7. joint optimization of backup switch time and a rest endpoint;
8. retention/execution of the last committed trajectory on replan failure;
9. trajectory tracking by an on-manifold MPC controller.

Disabling item 6/7 or returning a simple reactive detour is not SUPER.

## Testbed normalization

The benchmark reproduces the planning and commitment mechanism inside the
existing `PlannerPlugin`; it does not embed a second ROS application.

| Paper component | Local-testbed realization | Fidelity class |
|---|---|---|
| 3-D LiDAR point cloud | 360-degree deterministic range fan, projected into persistent world-frame hit/free cells | surrounding infrastructure normalized |
| ROG point-cloud map | planner-owned, time-decayed 2-D configuration-space evidence map | mechanism-preserving approximation |
| 3-D A* | 2-D local A* at the current flight altitude, unknown-free exploratory search | mechanism-preserving approximation |
| CIRI polyhedra | robot-radius/clearance-inflated free-cell corridor around shortened line seeds | mechanism-preserving approximation |
| MINCO/L-BFGS polynomial | clearance-checked, resampled and corner-smoothed trajectory with mission kinematic timing | lower-fidelity surrounding optimizer |
| backup optimization | latest known-free branch point plus a braking tail ending at rest | mechanism-preserving approximation |
| committed-trajectory FSM | planner state retains the last safe committed plan on a failed replan | reproduced |
| OMMPC and differential flatness | existing frozen `mock_velocity` controller | surrounding infrastructure normalized |

The adaptation is intentionally two-dimensional because the local simulator's
geometric sensor is a horizontal range fan and its obstacles are vertical
columns. Altitude is interpolated and bounded by the mission constraints. No
environment object, obstacle list, or other privileged state is accessible to
the planner.

## Shared-substrate placement

The plugin is selected by configuration and is shared by C0, C1, C2 and C3-C6.
C0 changes semantic input only: its goal is privileged, while obstacle geometry
still comes exclusively from the same sensor contract as every other waypoint
architecture. Direct-VLA configurations C7+ do not invoke this planner.

## Predeclared SUPER acceptance gate

Development scenes use seeds **1000-1019**; held-out evaluation seeds 1-40 are
not used for tuning.

SUPER is accepted only if all of the following hold:

- unit tests demonstrate separate exploratory and backup branches, a
  known-free backup ending at zero velocity, and retention of the previous
  commitment after an injected replan failure;
- the planner never reads `ObservationPacket.privileged`;
- C0 completes at least 19/20 `grid_nav` development episodes, with zero
  collisions;
- C0 completes at least 18/20 `failure_recovery` development episodes, with
  zero collisions;
- two repeated runs of the same seed produce identical result metrics and
  planner diagnostics;
- the full existing local test suite passes.

Failure of this gate blocks all later paper-family conclusions; it must not be
hidden by the downstream shield.

## Acceptance evidence

The frozen verifier is `scripts/verify_super_gate.py`; its machine-readable
result is `reports/paper_implementation/super_gate.json`.

- `grid_nav`, seeds 1000-1019: **20/20 success**, zero collisions, zero
  downstream shield interventions;
- `failure_recovery`, seeds 1000-1019: **20/20 success**, zero collisions,
  zero downstream shield interventions;
- repeated `grid_nav` seed 1000 matched on path length, final distance,
  collisions, executed decisions and infeasible-plan count;
- SUPER mechanism/plugin contract tests: 50 passed at the focused checkpoint;
- complete repository regression at the original freeze: **253 passed** in
  268.41 s.
- Ruff: all changed implementation/integration files clean.

Mypy could not run under the installed local tool set because NumPy 2.5's stub
package contains Python-3.12 type syntax while this repository deliberately
sets mypy's target to Python 3.10. This is recorded as a tooling dependency
mismatch, not counted as implementation evidence.

## Frozen normalized parameters

The shared C0/C1/C2-derived configurations use 0.5 m cells, a 16 m exploratory
horizon, a 2.5 m controller-aware committed horizon, 25 m sensing, a 12 s
temporal evidence window, and a 1.2 m tracking-tube margin in addition to the
mission clearance. A* hot-start prefers the prior exploratory corridor only
while the semantic goal remains within 4 m; a genuinely new semantic goal
clears that preference, matching the official `new_goal` distinction.

The 2.5 m committed horizon is the normalization for the testbed's proportional
velocity tracker. It prevents its 3 m carrot from cutting across a curved safe
corridor; the paper's OMMPC does not require this approximation because it
tracks the optimized polynomial directly.

## Post-freeze corrective revalidation

AerialClaw's elevated reconnaissance goal exposed a shared edge case: once the
vehicle reached the goal's XY cell, the 2-D A* returned one cell and SUPER
collapsed the remaining vertical segment to zero length. The planner now
preserves that vertical segment, and a unit test pins it. The same audit found
that random boxes could float above the horizontal sensing plane despite this
record declaring ground-attached columns; random clutter is now generated as
the declared 2.5-D column model.

These are substrate correctness fixes, not SUPER parameter tuning. The frozen
gate was rerun afterward and again passed `grid_nav` 20/20 and
`failure_recovery` 20/20 with zero collisions, zero shield interventions and a
passing deterministic repeat. The complete repository freeze suite now passes
280 tests in 405.05 s. The current evidence remains
`reports/paper_implementation/super_gate.json`.
