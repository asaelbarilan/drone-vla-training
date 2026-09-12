# D-103 — Eight implemented capability scenarios

## Delivered

Eight selectable environments: known coordinate, visible red pillar, turn-to-search,
overturned vehicle, conditional opening, red-then-blue visit, closing passage,
and straight-line target following. See `docs/CAPABILITY_SCENARIOS.md` for exact
instructions, scoring, seed variants, input boundaries and runnable commands.
All use the existing grid dynamics/RGB-D, with a new opt-in adapter and private
objective evaluation. No model/policy change, no MapGPT/gate repair, no training,
no external inference, and no held-out evaluation.

The latest design is ASP-UAV_Final_Research_Design.pdf outside the repository;
its location is now recorded in the documentation map. Nine refers to architecture
conditions and eight to capability regimes.

## Physical positive controls (not architecture results)

Recorded under `evidence/`; each contains manifest, control events, result,
initial camera and final camera. The driver uses scripted privileged velocity
commands through actual shared dynamics, not teleportation. It does not run SUPER
or a model. Static demonstrations finish at low speed; follow ends at 20 s.

| Scenario | Simulation seconds | Collisions | Task mechanics |
|---|---:|---:|---|
| Known goal | 7.55 | 0 | pass |
| Visible target | 7.55 | 0 | pass |
| Turn search | 10.00 | 0 | pass |
| Overturned vehicle | 7.95 | 0 | pass |
| Conditional opening | 12.50 | 0 | pass |
| Ordered visit | 12.25 | 0 | pass |
| Closing passage | 26.40 | 0 | pass |
| Following | 20.00 | 0 | pass |

Controls are fixtures, not evidence that any autonomous architecture understands
the tasks. Eight development seed-1061 fixtures do not establish generalization.
The first `validated/` recordings and incomplete initial setup directory are kept
as development history. `evidence/` is the final scoring-version dataset. Later
bounds enforcement changes no trajectory; final replay rechecks those recordings.

## Real runtime integration without real inference

`runs/capability_c0_known_goal_20260912_s1061` uses the normal orchestrator, C0
privileged oracle, SUPER, safety/controller and new known-goal environment.
Success at 5.75 s, final distance 1.565 m, correct explicit stop, zero collisions
or constraint violations. The 48 logged inference events are zero-token simulated
perception/policy charges, not network/model requests. Saved result and manifest:
`C0_RESULT.json`, `C0_MANIFEST.json`. This validates wiring and classical execution
only, not semantic capability.

## Visual evidence

- [Eight fixture replays](http://127.0.0.1:8765/capability_scenarios.html)
- [C0 runtime integration](http://127.0.0.1:8765/capability_c0_known_goal.html)
- `browser/CHECKS.json`: 32 actual dashboard seeks and 8 playback checks in
  headless Edge, no page errors.
- Screenshots are actual dashboard camera/map/observer views, not mockups.
- Visually inspected both vehicle orientations at the initial pose, wall closure
  at 3.1 s, and following at 20 s. The vehicles are coarse small box composites;
  this is basic visual orientation discrimination, not real emergency reasoning.

The dashboard uses current obstacle and landmark geometry at every frame and
shows private task status/visits/tracking duration. Scripted fixtures carry a
prominent NOT architecture performance label. Replay checks every saved pose,
final distance and final task status/counters; a deliberately corrupted task score
is rejected by a regression test. Legacy static replays remain supported.

## Validation and development corrections

Focused negative controls cover wrong vehicle, wrong order, wrong opening,
stationary following, invalid altitude/fence, and task completion independent of
point distance. Observing/status polling cannot advance task progress. Reset
reproduces initial pixels and control outcomes. Existing contract suite also
checks the new adapter.

Development corrected: pytest treating a helper named setup as a hook; eager
route-dictionary evaluation indexing absent subgoals; registration placed in core
instead of adapter discovery; missing metrics-fixture dependencies; and explicit
UTF-8 handling in the edit helper. No real model calls occurred in these attempts.

Initial wide lint identified pre-existing issues in common.py and metrics.py;
changed/new operational modules pass focused lint. Full offline tests and final
checks are recorded in VALIDATION.json. No claim of whole-repository lint cleanup.

## Limits and next use

These scenarios are intentionally small. C1's historical labeled-detection inputs
are unavailable here; existing architecture readiness must be evaluated, not
assumed. RGB-D policies receive no simulator-authored semantic answer. Following
uses a non-solid moving marker, not human motion. Complex scenarios have no
certified shortest-path denominator; zero placeholder SPL is not an efficiency
result. Begin future architecture evaluation with individually inspected tasks.
No real-model flight is active or scheduled.
