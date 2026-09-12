# D-101 implementation and offline verification

Implemented `adaptive_visual_plan` and the separately named
`vlm_adaptive_plan_gemma_dev` architecture. Model outputs own the ordered
subgoals, active subgoal, expected observations, scene memory, assessment,
image point and intended travel. There is no classical semantic-goal chooser.
An explicit retain action preserves the world point from its original observation.
It does not reproject an old pixel from a new camera pose. Geometry alone never
advances the semantic plan, including after reaching the model's proposed point.

Strict typed JSON rejects undeclared fields, invalid IDs/coordinates, duplicate
subgoals and invalid retain actions before changing state. Actual routing feedback
is associated with the issued decision ID and returned with measured pose history.
A missing or malformed model response has no invented navigation fallback.
The plan snapshot is copied, so later feedback cannot rewrite historical evidence.

The debugger now shows plan revision, active objective, expected view, model memory,
point origin and previous feedback in the VLM evidence panel. The full event chain
and source-code snapshot remain available. Old runs without plan records hide this
panel. No fabricated plan was attached to a historical run. UI_CONTRACT_FIXTURE.png
is clearly marked synthetic test data, not model inference or a flight result.

## Validation

- 361 unit/contract tests passed; 17 directly test the new policy, including a
  model waypoint accepted through the shared SUPER/router/controller in clear space.
- Added decision-trace isolation test; no cross-decision plan mixing.
- Eight Edge browser checks passed with zero JavaScript errors; screenshot inspected.
- Changed Python files pass Ruff. One existing third-party dateutil deprecation warning.
- Shared planner/controller/shield/monitor/scheduler/staleness/perception/memory
  equal the frozen C5 profile. The standalone config intentionally removes irrelevant
  inherited OnFly-only parameters; tests detect shared-component drift.
- Zero inference calls, zero flights, no cloud use or model changes.

The added integration-test fixture initially missed its Vec3 import; corrected
before the final 361-test pass. Source-cache comparison initially differed because
Windows translated CRLF to CRCRLF; normalized matches and both hashes are recorded
in the research SOURCE_AUDIT.json. Neither was an observed flight defect.

## Explicit differences and limits

This is the MapGPT adaptive-plan component plus the existing clean-room SPF
point/distance equations, with a fused expected-view assessment inspired by FineCog.
It is not complete MapGPT: no supplied graph, panoramic node views or arbitrary
remembered-node action is implemented. It retains the current forward-camera
point interface, which limits turning/backtracking. History is bounded to 12
steps plus a model summary; it is not a verified spatial map or full FineCog
hierarchical memory. Wrong plans can still be expressed and can still fail.

SPF uses model-named travel rather than C5's depth-derived range. A common
semantic/geometric verifier replaces the incompatible OnFly depth-equality
verifier; repair is disabled so a semantic destination is not silently rewritten.
The maximum camera-forward scale is 7 m. SUPER and the monitor retain their existing
local safety/recovery and stopping authority. No new clearance guarantee is claimed.
Output allowance is 768 tokens versus the earlier 192; context stays 8192.
Simulation charge remains the inherited fixed 1.0 s policy / 1.2 s monitor, while
actual wall latency is logged. Fixed charge is not a measured latency claim.

No real Gemma response has passed this new schema yet. First perform one explicitly
bounded saved-frame call with exact request/output capture to check this integration;
then consider a single development flight under `grid_nav_onfly_depth_v2_dev`.
Neither a flight nor an API/model sweep is scheduled. A planning-effect claim
requires a matched no-plan SPF control, because C5 differs in action representation
and verifier as well as planning. No success or improvement claim is justified yet.

Research basis: ../../docs/research/vlm_authored_planning_20260912/REPORT.md.
