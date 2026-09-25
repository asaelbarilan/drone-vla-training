## 2026-09-12 — D-103: dynamic debugger and eight scenario demonstrations

Extended the existing debugger to render time-varying obstacle/target state and
private task progress. Replay verifies task outcome/counters in addition to poses
and distance. Added reproducible no-model fixture recorder and Edge browser checks.
Eight scripted trajectories pass without collisions; 32 dashboard seeks and eight
playback checks pass. Normal C0/SUPER runtime also completes the known-goal task at
5.75 s, zero collisions, using only simulated inference accounting. Final offline
regression: 387 tests pass; 22 focused scenario checks; new tooling lint and
git diff --check pass. Real-model
capability remains untested. Read docs/CAPABILITY_SCENARIOS.md and the report under
reports/capability_scenarios_20260912. Latest external research design is now linked
from the documentation map; old concise PDF is explicitly identified as earlier.

## 2026-09-12 — D-103: enforce declared scenario altitude and fence

Review found the base simulator's world bounds are wider than the task limits.
New capability scenarios now also mark actual altitude/geofence violations in
private evaluation, so bypassing a recovery wall above the instructed 7 m cannot
pass even if a policy omits its safety filter. Dynamics and legacy scenarios are
unchanged. Three focused boundary negative controls added.

## 2026-09-12 — D-103: eight capability scenarios and task-aware evaluation

User authorized the first scenario in each of the eight task categories. Add an
opt-in adapter with shared grid dynamics/RGB-D, private objective scoring, and
no semantic-hit answers. Preserve old environments and policies. No model calls,
VLA training, gate repair, or held-out evaluation in this task.

Implemented eight capability_* YAML environments; optional colors express physical
object appearance independently of evaluator target identity. Overturned vehicles
use the same parts/colors, with wheels above versus below. Only RGB-D/odometry/range
reach policies. Added task_complete evaluator gate; legacy None retains old scoring.
Ordered visits require red before blue; conditional route has seed-controlled blockage;
recovery closes at 3 s; following scores 4-6 m / 20 degrees in the fixed 5-20 s window.
19 focused positive/negative tests pass. Eight continuous scripted physical fixtures
pass with zero collisions (geometry validation only). Dashboard evidence follows.

# Build log

## 2026-09-12 — D-102 flight completed; dashboard and boundary diagnosis saved

New vlm_adaptive_plan_20260912_s1061 timed out at 90 s with zero collisions,
11.306 m path and final/closest distance 23.995 m. Shared runtime unchanged.
Inspected actual dashboard camera/map/observer and VLM plans at eight fixed moments
per run; added corrected C5 seed 1061 for context. New replay matches 1,800 poses;
zero missing source frames; Edge playback/switching passes with no JavaScript errors.
First gate rejection is at 19 s; 71/89 proposals rejected, only 18 reach SUPER.
Model receives matched rejection feedback but repeats center point/distance (32 moves)
then retains a rejected world point (57 times). One plan revision, no active-step change.
A no-inference copied-planner probe at 19 and 32 s accepts both exact rejected goals
with full known-free paths. Replayed 641 poses, 32 gates and 18 prior plans exactly.
This demonstrates a gate/planner disagreement, not physical success after bypassing
it; model non-adaptation is a separate observed failure. No speculative runtime fix,
second full flight, cloud call or model sweep. Capture: 134 completed flight calls
plus one cancelled at the boundary, all Gemma, in addition to one preflight completion.
Harness-only corrections and unused launch error are preserved in the report. Next
is a targeted acceptance-contract change, separately from rejected-goal recovery.


## 2026-09-12 — D-102 real Gemma preflight passed

One saved initial RGB call produced valid plan JSON (310 output tokens; 13.88 s
measured wall latency, including 8.03 s reported setup; 1.0 s simulated charge).
Exact image pixels match the reconstructed seed-1061 start, and Gemma digest is
unchanged. Model proposes approaching a nearest structure while admitting color
uncertainty; this is an observed unsupported semantic assumption, not a schema
failure. No runtime change before the first full flight. Capture and result saved.

## 2026-09-12 — D-102 adaptive-plan flight/debug protocol

User authorized flying and dashboard debugging. Registered one saved-frame Gemma
preflight and an initial 90 s corrected-depth seed-1061 flight with full capture.
Bounded follow-up: at most one integration recheck and one further flight after a
concrete finding. Compare against the saved corrected C5 flight; preserve sensors,
shared execution and Gemma. No cloud calls or model sweeps. See
reports/adaptive_plan_flights_20260912/PLAN.md.
Preflight harness initially passed the adapter spec instead of its name; corrected
before any inference occurred. Runtime policy and flight configuration unchanged.

## 2026-09-12 — D-101 VLM-authored plan implemented and verified offline

Added opt-in `adaptive_visual_plan` policy and `vlm_adaptive_plan_gemma_dev` config.
VLM owns ordered subgoals, active step, expected views, scene memory, assessment,
image points and travel. Explicit retain preserves the original world waypoint;
measured pose/routing feedback returns to the next call. Strict parsing fails
closed without changing the plan; no classical semantic-goal selection or automatic
semantic completion. Reused SPF transforms and unchanged shared SUPER/controller.
Changed only the incompatible depth-equality verifier to the common endpoint gate
with repair disabled, and output cap to 768. Documented these comparison confounds.
Added visible plan/feedback/point-origin panel to flight debugger; old runs remain
unmodified and do not acquire invented plans. 361 unit/contract tests and changed-file
lint pass, including 17 new policy tests and clear-space SUPER routing. Eight browser
fixture checks pass; inspected screenshot is explicitly synthetic, not flight evidence.
No model calls or flights. Real Gemma schema compatibility and planning quality remain
unvalidated; next is one bounded saved-frame integration probe, then a development
flight only after that gate. Reports and exact source hashes saved. Baselines preserved.


## 2026-09-12 — D-101 VLM-authored planning research and implementation specification

User corrected D-100: the VLM should own planning and propose intermediate goals.
Extended the validated 24-work review to 27 with MapGPT, FineCog-Nav and WMNav;
inspected official planning code and documented supplied-graph/sensor/cost limits.
Selected a separately named adaptive-plan plus SPF waypoint adaptation, not a
full paper reproduction. Specification records model authority, persistent goals,
feedback, debugger evidence and offline falsification tests. No runtime code or
model calls changed in this documentation checkpoint. D-100 source audit remains
valid; its proposed next implementation direction is superseded by D-101.

## 2026-09-12 — D-100 drone_control graph audit and comparison design

User approved examining drone_control. Read the clean source checkout 070f2da
without modifying it or connecting to AirSim. Verified that the older graph-search
path selects viewpoints classically, with a mission-level LLM/heuristic planner.
Found a separate VLM region-menu implementation; its frontier extension defaults
off and reassigns frontier IDs per call. Recorded these as distinct paths, not one
proven LLM graph planner; historical success comments were not rescored.
Saved source hashes, line references, reuse boundaries and a matched classical-
versus-Gemma graph-selector design. Stable candidate identity, known-free route
support, explicit viewing yaw and shared image-grounding are preflight requirements.
Keep SUPER, task and C5 frozen. Next build and visually inspect the offline candidate
interface before model decisions or flights. Documentation only; no runtime changes,
model calls, tests of flight performance or additional simulations.


## 2026-09-12 — D-99 both additional flights saved and replayed

Seed 1062 timed out at 90 s: closest 21.22 m, final 37.46 m, zero collisions.
Seed 1060's closest approach is 26.24 m (final 59.27 m). Both have 134 completed
local Gemma calls and unchanged manifests. No further flights were run.
Updated the existing debugger with both new runs plus corrected and historical
seed 1061. All 7,200 logged positions and 356 policy source references match;
zero missing source frames. Browser selection/seek/playback/raw-output checks
pass without JavaScript errors. Saved and visually inspected closest/final
screenshots, preserved reports/results/manifests/console logs. Runtime unchanged.
Three corrected-depth development flights all timed out; no new causal claim
or architecture promotion. Next inspect source-aligned approach/departure.


## 2026-09-12 — D-99 first additional flight completed

Seed 1060 timed out at 90 s, final 59.27 m from target, zero collisions.
89 accepted proposals and 134 actual local Gemma calls, no inference/parse
errors; exact configuration match to previous corrected-depth flight.
Saved result/manifest/log and prepared a lint-checked offline comparison
exporter. Seed 1062 follows with no runtime or configuration changes.


## 2026-09-12 — D-99 two additional flights authorized

User requested two more runs. Preregistered development seeds 1060 and 1062,
90 seconds each, unchanged corrected-depth environment and guarded Gemma
architecture, with full debug capture. Fixed sampling/timing favors using two
additional layouts rather than repeating seed 1061. No runtime changes or
adaptive tuning; export all three corrected-depth flights into the debugger.


## 2026-09-12 — D-98 single flight completed; navigation not improved

Ran c5_depth_ray_v2_20260912_s1061 once with local Gemma and exact debug capture.
Timeout at 90 s, zero collisions; final target distance 30.01 m versus original
14.62 m, closest 14.94 m versus 14.32 m. All 89 plans accepted, 134 completed
model calls, no cloud use. Saved result/manifest/comparison and visual debugger;
both 1,800-pose replays and final distances match exactly. First model-point
change at 19 s, first trajectory divergence 28.05 s; closest approach at 40 s,
then movement away. Geometry repair remains valid; navigation is unresolved.
No follow-on run or architecture promotion. Browser replay checks pass.
User requested viewing during completion; restarted the local preview server
and provided the new run with the original selectable for comparison.

## 2026-09-12 — D-98 depth repair validated before flight

Implemented box_ray_v2: each drawn box pixel receives camera-forward ray/box
surface depth; invalid/near-clipped rays remain missing. RGB ownership and
landmark/background behavior are preserved. Legacy mode stays the default for
old profiles, and corrected depth references include their version. Added the
matched grid_nav_onfly_depth_v2_dev environment and seven focused regressions.
All 342 unit/contract tests pass. Saved replay preserves 1,800 poses and all 89
source RGB/legacy-depth images; 1,146 corrected patch pixels match independent
geometry within 4.75e-7 m. The selected sample changes 0.213216 -> 1.731457 m.
Configuration checks confirm architecture unchanged and only depth_renderer
changed in environment params. One authorized Gemma flight follows this commit.

## 2026-09-12 — D-98 authorized sensor repair and one flight

Registered a versioned per-pixel box-depth repair with historical compatibility,
saved-pixel and geometric regressions, followed by exactly one matched 90 s
Gemma seed-1061 flight with full debug capture. Only the depth-renderer setting
changes; no semantic verifier, planner tuning, model swap or cloud calls.

## 2026-09-12 — D-97 visual audit and narrowed causal claim

Saved all 89 source RGB/depth captures, source-to-waypoint trace, geometric
validation, contact sheet and interactive audit. The default decision displays
0.21 m supplied versus 1.73 m actual selected-ray depth. Source-aligned pixels
are on foreground obstacle 7; 32–41 s destinations stay within 0.116 m. This
narrows the earlier persistence hypothesis: D-96 changed destination quality
and location as well as holding it fixed. Documented the confirmed shared
sensor defect separately from unproven full-flight causes and next steps.
Edge navigation/value/patch checks pass with no JavaScript errors. Handoff and
D-97 updated. No inference, navigation repair or new architecture added.

## 2026-09-12 — D-97 confirmed depth contract defect

Added scripts/audit_waypoint_handoff.py. The historical replay matches all
1,800 poses/controls, 89 plan metadata records and 89 source depth images.
At decision 3bec7cd30542 (source 39.95 s), selected wall depth is 0.213216 m
but independent ray/box depth is 1.732390 m. The supplied depth comes from
an off-screen top corner painted over the entire box. All 46 ray hits pass
surface and camera reprojection checks; four analytical ray cases and two
existing camera geometry tests pass. Source pixels lie on obstacle 7 throughout
26–42 s. Goals from 32–41 s remain within 0.116 m, so replacement frequency
alone is not supported as the approach-stall explanation. No runtime changes,
model calls or new autonomous flights. Visual report follows.

## 2026-09-12 — D-97 source-pixel and waypoint audit

User authorized tracing the failing handoff before another navigation change.
Registered an offline replay of policy source images, selected pixels, depth
samples, accepted destinations, SUPER paths and replacements. The audit will
independently check sensor depth against scene geometry. No model calls or
reference navigation changes.

## 2026-09-12 — D-96 visual replay and research boundary

Saved the successful fixed-destination trace, summary, validation and portable
interactive replay. It shows actual movement, inferred range map and exact
planner inflation, exploratory/committed paths and 382 embedded camera frames.
Edge playback/seek/step/overlay checks pass with no JavaScript errors; physical
trace checks and focused script lint pass. Read the original design PDF: new
architecture components must be separately named and compared under frozen
shared execution and observations. Updated D-96 and AGENTS.md; no verifier
implemented and no further model calls or experiments scheduled.

## 2026-09-12 — D-96 executed: fixed goal enables a wider detour

Added scripts/probe_super_passage_4160.py. Historical replay matched all 833
positions and controls exactly, all 41 plan metadata records and 41 source
frames/depth lifts. One continuation with a fixed destination reached within
0.489 m in 38.10 s, with no collision; all 39 replans accepted. SUPER selected
a roughly 21.83 m route around the right obstacle. Minimum sampled body-to-wall
gap was 0.949 m. No VLM/API calls or runtime changes. The test jointly replaces
semantic selection, image-depth lifting and destination updates with a manual
fixed point, and removes monitor/image-verifier interventions. It establishes
local execution capability here, not which upstream component caused the stall.
Focused script lint passes. Visual export and report follow.

## 2026-09-12 — D-96 fixed-waypoint diagnostic design

User authorized testing SUPER and the controller from the disputed 41.60 s
state. Registered one 48.4 s maximum continuation, fixed destination from the
previous successful manual probe, unchanged planner settings, no inference.
Historical planner reconstruction must pass metadata checks before continuation.
Route-quality verification remains a separately named future architecture idea.

## 2026-09-12 — D-95 physical crossing results and videos

Executed exactly two manual probes from the requested t=41.60 s state, retaining
velocity and simulator dynamics. Straight heading collided after 9.85 s; an
8.04-degree rightward aim through the visible opening cleared both obstacles
in 19.50 s, with 0.213 m minimum sampled body-to-wall gap. Both restores have
zero logged-position error. Saved per-tick traces, source image, endpoint
comparisons, two H.264 videos and a standalone side-by-side page. Browser
playback checked. No VLM/API calls; no navigation implementation changed.
Nominal planner clearance is 1.8 m; the relationship to its inferred map and
original stall remains to be investigated. All evidence is privileged diagnostic,
not an autonomous performance result. See reports/passage_probe_20260912/REPORT.md.

## 2026-09-12 — reproducible manual crossing script

Added scripts/probe_passage_4160.py: restore every prior control and verify
position/time/observation, retain original velocity, then command 0.6 m/s
straight ahead or toward visually selected u=128 in the 224-pixel opening.
Each branch ends at first collision, clearance of both bounding obstacles,
or 24 seconds. Save per-tick state, collision result and map/camera MP4s.
The local planner is bypassed only for this requested physical test.

## 2026-09-12 — D-95 exact-state passage diagnostic

User explicitly requested moving through the visible gap from t=41.60 s /
observation 833 in the guarded Gemma run. Restore full dynamic state and test
manual heading/opening-center commands, stopping at contact. No VLM calls or
autonomy changes; privileged diagnostic only, with visual evidence saved.

## 2026-09-11 — debugger delivered and verified

Standalone page: reports/debugger/index.html; guide: docs/FLIGHT_DEBUGGER.md.
Three historical flights loaded, 5,305 poses and final distances exact, 396
source frames aligned. Final validation: 335 unit/contract tests pass; browser
checks pass both over localhost and as a standalone file, including responsive
layout and downloaded review notes. No model/API calls or new flight experiments.
Updated handoff to inspect one shared moment before selecting further tests.
Design and replay implementation committed at 20dfe1d/c95399c; exact capture
and browser checks committed at 1f1448a. Generated HTML/images are ignored and
rebuildable without inference; the small validation manifest is tracked.

## 2026-09-11 — opt-in exact debugger capture

Added run --debug-capture and the zero-inference debugger export command.
Capture stores exact plugin/backend request prompts, schemas, encoded images,
returned payloads, failed/cancelled call status, immutable source snapshots,
typed proposals and full planned trajectories. Raw prose stays out of controls
and the event bus. Default capture remains off; a mock paired episode preserves
controls and simulated time. Existing captures cannot be silently overwritten.
The debugger opens recorded source locations and exposes unassociated call
records, while old runs retain explicit missing-data labels. Current observer
reconstruction supports grid3d without injected failures; D-94 is the explicit
simulator-portability exception registered in the contract test.

## 2026-09-11 — synchronized replay debugger

Added a portable HTML debugger with flight map, reconstructed observer and RGB
views, policy/monitor timeline, source-frame crosshair, execution chains, code
references and downloadable review notes. Exported two Gemma failures and the
historical Qwen success using saved controls only. All 5,305 logged positions
and three final distances match exactly; all 396 decision sources align.
Four offline regression tests and focused lint pass. Headless browser renders
without JavaScript errors. Old missing prompts, raw responses and request images
are labeled; observer view and source-code references are reconstructed/current.

## 2026-09-11 — D-94 debugger design

User requested a shared visual flight debugger. Scope: saved-control replay,
synchronized flight/decision inspection, explicit evidence provenance, and
opt-in capture for future runs. No flight or model call authorized by this work.

## 2026-09-11 — final bounded-debugging outcome, D-93

Completed exactly five adaptive flights on seed 1061, all Gemma E2B: zero
mission completions, five timeouts, no collisions or premature stops. Final
distances: 14.15, 40.25, 72.45, 14.62, 77.18 m. No default promotion.
Corrected source-aligned monitor scoring: guarded-monitor trial 4 has TP=3,
FN=6, FP=0, TN=36. Earlier activation-frame accuracy values below are
superseded. Three saved-image calls reject the gray view but also reject
the positive red approach/arrival views; strict monitoring is not solved.
Final validation: 323 unit/contract tests, focused Ruff and diff checks pass.
All five runs plus baseline replay distance exactly. Every change has a
commit; no run or further model call remains scheduled. Report:
`docs/research/c5_navigation_audit_20260910/AUTONOMOUS_DEBUG_20260911.md`.


## 2026-09-11 — D-92 fix offline monitor scoring alignment

Corrected a diagnostic bug: delayed monitor replies were scored against the
completion-time image. Both analyzers now use evidence_observation_seq and
count unmatched source frames. Prior visibility accuracy numbers are
superseded; success and trajectory distances are unchanged. Added a
regression where visibility changes during inference. Rescore without calls.


## 2026-09-11 — bounded saved-image recognition controls

Prepared exactly three local monitor calls after the flights: recorded gray
false-stop view, visible red approach, and genuine-arrival red-filled view.
They use the actual monitor prompt/schema, score recognition only, and do not
claim navigation or geometric arrival. No extra flight or cloud quota.
Image/depth renderer audit confirms both include admitted landmarks.


## 2026-09-11 — run 4/5 outcome

Original policy plus guarded monitor timed out: final 14.62 m,
closest 14.32 m, no collision or false stop. Monitor visibility
accuracy 33.3%; no navigation success. Use
fifth/final run for D-91 cue-only ablation on the same development seed.


## 2026-09-11 — D-91 final-run candidate

Prepared a one-setting ablation of D-90: omit the previous-goal point cue.
Flight 4 currently copies it in 31/50 comparable decisions. Unlike D-88,
this leaves the original point schema and all monitor behavior unchanged.
Only run if flight 4 fails; otherwise use the last flight for a second seed.
No more than five flights in this session.


## 2026-09-11 — run 3/5 outcome

D-89 timed out, final 72.45 m, closest 32.94 m,
no collisions. Guard rejected 48 contradictory
model target claims, but exploration wandered away. This policy variant is
not retained as an improvement. Run 4 restores the original policy and tests
only the guarded monitor on 1061. No default change.


## 2026-09-11 — D-90 restore original policy for monitor isolation

Prepared a profile retaining the current-frame/attribute monitor while
restoring the original waypoint policy. New policy variants regressed; their
commits remain available but are not promoted. Run 4 will compare on 1061
after run 3 completes. Clarified logs that candidate scale is not a visual
measurement and point consistency is geometry only. Removed three existing
style warnings without behavior changes. Accumulated suite: 321 tests pass.


## 2026-09-11 — run 2/5 outcome

D-88 result: timeout, final 40.25 m, closest
21.80 m, collisions 0. Fresh point proposals
alone did not solve navigation. Logs expose gray descriptions labeled target.
Proceed to the independently committed D-89 attribute guard, same seed.


## 2026-09-11 — D-89 declared attribute consistency candidate

Flight 2 exposes gray-object descriptions labeled as the red target. Added
an opt-in comparison between VLM-reported object color and the single explicit
mission color. Mismatched policy candidates use a model-proposed exploration
alternative; mismatched monitor candidates cannot acquire or stop. No image
color thresholds or truth. Ambiguous color instructions fail explicitly.
This is a limited semantic-contract experiment, not a claimed source replica.


## 2026-09-11 — run 1/5 outcome

D-87 monitor-only trial on 1061 timed out at 14.15 m, no collisions or false
stop. Exact replay: 38 visible decision frames; monitor visibility accuracy
37.8%, so identity remains unreliable. The policy still lacks fresh semantic
commitment. Proceed with separately committed D-88 variant on the same seed.
No defaults promoted. Full trace and run ledger retained under reports.


## 2026-09-11 — D-88 auditable target/exploration proposals

Prepared a separate opt-in policy interface using fresh visual evidence and
an explicit target/exploration point label. Only model-identified targets
receive the target label; exploration is still chosen by Gemma. Previous
point cue omitted to address copying. Geometry/controller unchanged. This
is a combined interface experiment; run 2 awaits scoring of run 1.


## 2026-09-11 — preserve grounding evidence in normalized monitor logs

Fixed diagnostic logging: absent-target normalization previously replaced the
caption, hiding the evidence needed to debug identity. Captions now survive
normalization; no control decisions change. Added regression assertion.
Also corrected the prior report interpretation: navigation waypoints need not
lie on target pixels; monitor identity errors are the direct evidence.
Flight 1 remains on the already-loaded c87aff6 implementation.


## 2026-09-11 — D-87 current-frame grounding monitor

Added opt-in current-image identification, separating VLM identity from metric
arrival and temporal confirmations. The false-stop frame is a gray obstacle;
point consistency was only geometry, not identity. Latest image only, short
evidence/visibility/coordinate schema; no truth or color detector. Gemma
output ceiling raised to 192 for the evidence field. Same policy/controller.
Regression tests cover absent coordinates, genuine near/far targets and one
image per request. Run 1/5 will use seed 1061. Defaults unchanged.


## 2026-09-11 — rollback checkpoint before autonomous debugging

User authorized up to five further development flights and commits after each
change. Preserve the existing repaired Gemma, target-stop, provider router and
yaw-ablation state as the baseline checkpoint. No credentials or temporary
files are staged. New work will use separate commits and opt-in profiles.


## 2026-09-11 — D-86 goal-facing yaw diagnosis

Completed exact offline trace and one opt-in local Gemma flight. Yaw alone did
not rescue navigation: false stop 25.20 m away, no visible target frames.
Historical/default profiles unchanged. 308 tests pass. See
`docs/research/c5_navigation_audit_20260910/YAW_RESULT_20260911.md`.


## Behaviour-cloned policy: pipeline works, policy does not navigate

The full path is built and runs end to end — `uavlab collect` → `uavlab train` →
a registered `learned_visuomotor` plugin → `c7t`/`c8t` configs flying in the same
runtime as every other architecture. **The trained policy itself does not
navigate**, and I now know why with evidence rather than suspicion.

| stage | state |
|---|---|
| expert collection | ✅ 16,747 samples from 156 successful episodes, 630 MB, ~5 min |
| action discretisation | ✅ 64 bins/dim, 0.067 m/s quantisation floor |
| network | ✅ 427 k parameters, 1.0 ms forward pass |
| training | ✅ 110 s on GPU, stop-head recall 1.00 / precision 0.96 |
| plugin + configs | ✅ `c7t`, `c8t` run in the normal runtime |
| **navigation** | ❌ **0/5 success. c7t collides 5/5; c8t survives but wanders** |

### Two failures found by measuring, not guessing

**1. Causal confusion — the policy learned to copy its own velocity.**

First trained policy froze at 0.12 m/s on a fixed heading for a whole episode,
while scoring r = 0.87/0.93 correlation with expert actions on held-out data.
Open-loop excellent, closed-loop inert. The cause:

| | |
|---|---|
| `corr(own velocity, expert action)` | **0.92** |
| velocity error of *simply echoing your own velocity* | 1.174 m/s |
| velocity error of the trained policy | **1.307 m/s — worse than the echo** |

Velocity is a lagged copy of the previous command, so it is a near-perfect
shortcut, and the network took it and ignored the image entirely. From a
standstill, echoing your own velocity means commanding zero forever.

This is the copycat problem (de Haan et al. 2019, Wen et al. 2020). Fixed by
withholding velocity from the policy input — attitude only. After the fix the
policy genuinely moves, and its honest error rose to 1.875 m/s, which is the
real difficulty of the task rather than the shortcut's flattering number.

**2. The label is not a function of the image, 58.7 % of the time.**

| training frames | 16,747 |
|---|---|
| frames that contain the target | 6,909 (**41.3 %**) |
| frames with **no** target visible | 9,838 (**58.7 %**) |

The oracle flies toward a goal it reads directly from ground truth — *through
walls*. On the majority of frames the student is being asked to predict a
direction that the image does not determine. That is irreducible label noise, not
an optimisation failure, and no amount of training, capacity or epochs removes it.

This is the privileged-information gap in teacher/student imitation, and it was
foreseeable: it is written down in `docs/SMALL_VLA_SEARCH.md` as the covariate-
shift risk, and I under-weighted it.

### What would actually fix it

1. **Give the student memory.** A frame stack or recurrent state lets it
   integrate where the target was last seen, which is what makes the other 58.7 %
   of states predictable. Closest to what a real VLA does.
2. **Use a non-privileged expert.** Clone something whose behaviour is a function
   of the student's observation space — the scripted `vlm_waypoint` with memory,
   rather than the oracle. The teacher becomes imitable by construction.
3. **DAgger.** Still needed for covariate shift, and cheap here because the
   oracle can label any state instantly. Does not fix (2) on its own.

Options 1 and 2 are complementary and both are real work. Not started — this is
a design decision, not a tuning knob.

### Honest status

What exists is a working *pipeline* for putting a genuinely learned policy in the
C7–C14 slot, plus two measured, documented findings about why naive behaviour
cloning from a privileged oracle fails. What does not exist is a policy that
flies. Nobody should read `c7t`/`c8t` numbers as an architecture result yet.

## All 15 architectures verified functioning

```bash
uavlab verify --seeds 1 2 3 4 5 6 7 8
```

New command, and deliberately distinct from `validate-config`: that one checks a
configuration is *legal*, this one checks the architecture actually *functions*.
"It ran without raising" has already produced one wrong claim in this project,
so each check targets a specific way an architecture can look fine and be broken:

| check | the failure it catches |
|---|---|
| `runs` | raises during the episode |
| `moves` | stationary vehicle still emits a full, meaningless metric row |
| `progress` | never gets closer to the goal — not pointed at the task at all |
| `authority:<level>` | decisions routed through the wrong path for the declared authority |
| component fires | **an architecture that is really its parent under another name** — verifier never consulted, monitor never assessed, reasoner never invoked, shield not on every command, chunks never executed |
| `deterministic` | same seed produces a different episode, invalidating paired comparison |

Checks are derived from the *config*, not a hardcoded table, so a new
architecture is covered the moment it exists.

**Result, `grid_nav`, 8 seeds — all 15 PASS every check:**

| arch | SR | dist | path | coll | | arch | SR | dist | path | coll |
|---|---|---|---|---|---|---|---|---|---|---|
| c0 | 0.88 | 3.8 | 57.2 | 0.12 | | c8 | 0.62 | 13.0 | 157.6 | 0.00 |
| c1 | 0.12 | 28.2 | 201.7 | 0.00 | | c9 | 0.75 | 7.4 | 101.8 | 0.00 |
| c2 | 0.62 | 12.6 | 224.0 | 0.00 | | c10 | 0.38 | 18.5 | 141.7 | 0.00 |
| c3 | 0.50 | 15.4 | 193.6 | 0.12 | | c11 | 0.38 | 17.8 | 105.3 | 0.00 |
| c4 | 0.75 | 8.0 | 174.4 | 0.12 | | c12 | 0.62 | 9.6 | 105.9 | 0.00 |
| c5 | 0.62 | 9.6 | 158.0 | 0.12 | | c13 | 0.62 | 9.6 | 105.9 | 0.00 |
| c6 | 0.50 | 15.4 | 193.6 | 0.12 | | c14 | 0.62 | 8.7 | 88.1 | 0.00 |
| c7 | 0.75 | 8.5 | 136.4 | 0.00 | | | | | | |

**Passing means functioning, not performing.** C1 at 0.12 and C10/C11 at 0.38
are working correctly and doing badly — which is a result to explain, not a bug
to fix. The success column is printed for information only.

### A bug the verifier found in itself, immediately

Run across *all* configs, it reported the five Gemma variants as FAILED with
`no frame behind 'stub://grid3d/rgb/1'`. That was the verifier's fault, not the
architectures': it defaulted to `grid_nav`, which does not render, and the
vision policies raised exactly the loud error they were built to raise.

Scoring that as a broken architecture would have been the same category error as
scoring a teleported drone as a recovery failure. Fixed: policies now declare
`requires_vision`, and the verifier routes them to the rendering variant of the
environment, or reports **SKIP** with a reason where none exists. A skip is
never counted as a failure.

Locked by `tests/integration/test_verify.py`, which mostly tests that the
verifier *fails* when it should — a stationary policy, a randomised policy, an
inert component. A verifier that passes everything is worse than none.

## STATUS: what works and what does not

### Works — verified by measurement

| area | evidence |
|---|---|
| Runtime kernel | 195 tests pass in ~60 s. Contracts, decision router, scheduler, staleness, event log, config grammar. |
| Determinism (scripted configs) | same seed reproduces metrics exactly; different seeds produce different scenes |
| Control ceiling | C0 meets the per-regime gate in all five regimes (was only ever checked on one) |
| `grid_nav` regime | ceiling 0.88, spread 0.38–0.75, no floor/ceiling pileup — architecture contrasts here are readable |
| Safety contrast | C7→C8 (same VLA, add shield) removes collisions, as designed |
| Renderer | real 224×224 frames; `unproject` inverts `project` to 1e-15 |
| Gemma 3 4B vision | 0.93 detection accuracy on a fixed frame set, **0 parse failures** across every run |
| Gemma latency | 4.05 s → ~1.7–2.3 s per call after fixing transport and switching endpoint |
| All 5 Gemma configs | `c2g`–`c6g` run end-to-end with no errors |

### Does not work

| problem | detail |
|---|---|
| **No Gemma config completes a mission** | 0 of 5. All time out at 17–39 m from a 2 m goal. |
| **Real-model runs are not reproducible** | c2g, seed 1, twice: **5.7 m then 17.1 m**. Measured latency varies run to run, which shifts the sim clock, which changes the trajectory. This breaks paired-by-seed comparison — the core method. |
| `object_search` regime | six architectures score exactly 0.00, including the whole single-action VLA family; ceiling marginal (0.62 SR, 0.25 collisions) |
| `failure_recovery` regime | ceiling fixed (0.75) but every non-oracle architecture sits at 0.00–0.12; C3–C6 collide 38 % |
| C1 (skill agent) | 0.00–0.12 everywhere, 88 % timeouts, unexplained |
| C10/C11 | *worse* than C8 despite being C8 plus a reasoner — needs an explanation, not a shrug |
| AerialVLA | blocked: LoRA weights with no `openvla-7b` base present |
| `ruff` / `mypy` | wired into CI, never installed or run locally |

### First Gemma run of all five configs (`grid_nav_vision`, seed 1)

| arch | outcome | dist | policy calls | mean latency | decision age | found rate |
|---|---|---|---|---|---|---|
| c2g | timeout | 17.1 m | 22 | 2.21 s | 3.50 s | 0.27 |
| c3g | timeout | 35.8 m | 21 | 2.33 s | 3.70 s | 0.43 |
| c4g | timeout | 38.8 m | 21 | 2.31 s | 3.80 s | 0.67 |
| c5g | timeout | 21.9 m | 24 | 1.98 s | 3.35 s | 0.25 |
| c6g | timeout | 34.6 m | 23 | 2.12 s | 3.15 s | 0.22 |

The arithmetic explains the timeouts without needing a bug: a 60 s episode at
~2.2 s per decision yields ~22 decisions; the target starts 35 m away; hops are
12 m; and the target is visible in roughly a third of frames. There is not
enough decision budget to converge. Whether that is a real finding about a 4B
model holding waypoint authority, or simply an under-provisioned episode
horizon, is **not yet distinguishable** — and saying which would require the
paired multi-seed screen that has not been run.

### Reproducibility — FIXED, but not the way I proposed

The plan was to quantise the charged latency. **Quantising does not work**, and
the only reason I know that is that I tested it instead of shipping it.

Same seed, `c2g`, two *separate processes* (which is how a sweep runs):

| charge mode | run 1 | run 2 | verdict |
|---|---|---|---|
| `measured` | 36.76 m | 7.16 m | diverged |
| `quantised` (250 ms) | 10.94 m | 18.53 m | **diverged** |
| `fixed` (2.2 s constant) | 9.749 m | 9.749 m | **reproducible, identical to 4 dp** |

Quantisation fails for a reason that is obvious afterwards: a call landing either
side of a bucket boundary — 1.86 s rounds down, 1.92 s rounds up — flips one
decision, and that flip cascades through every decision after it. Bucketing
reduces how *often* the coupling bites, never *whether* it does.

**Default is now `charge_mode: fixed`**, charging a constant measured once
(2.2 s median for Gemma 3 4B on this machine). Live latency is still measured
and reported as `inference_latency_s_policy`, alongside `inference_charged_s_policy`,
so the gap between realism and reproducibility is visible rather than hidden.
`measured` and `quantised` remain available for latency-realism studies where
pairing is not needed.

Locked by `tests/unit/test_latency_charging.py` (no network required), including
a test asserting the *shipped* Gemma profile is the reproducible one.

### Two wrong hypotheses on the way, both killed by measurement

Worth recording, because both were plausible and both were wrong.

1. **"The model is nondeterministic at temperature 0."** Tested directly: six
   calls, identical image and prompt — **six identical replies**, with and
   without an explicit seed. Gemma was never the problem.
2. **"Latency jitter is the only coupling."** Then `fixed` mode should have been
   reproducible immediately, and in the first test it was not. Tracing every
   decision showed the decision trace was *byte-identical* across runs — same sim
   times, same positions, same image digests, same replies — and tracing all
   1200 control ticks showed those were identical too. The apparent divergence
   was an artefact of running several modes back-to-back inside one process.
   Isolated per-process, `fixed` is exact.

The general lesson is the same one as the 2.08 s transport bug: the cheap
instinct (blame the model, reach for quantisation) was wrong both times, and a
targeted measurement was decisive both times.


Built from *A Modular Testbed for Searching Single-UAV Foundation-Model Autonomy
Architectures*. Milestones A and B of the spec are complete.

## What exists

- 86 Python files (~11k lines), 34 YAML configs, 173 tests passing in 31 s.
- All 15 architectures **C0–C14** as pure configuration — no code forks.
- 5 benchmark regimes, 7 staged experiments, CLI, sweeps, paired stats, Pareto.

## Where testing runs (the AirSim question)

Everything runs on the built-in deterministic environment `grid3d`. **AirSim is
not installed and is not used.** That is the spec's own adapter priority:

1. deterministic in-process env ← all current testing
2. PX4 SITL + Gazebo — stub, raises with an install hint
3. Project AirSim — stub, raises with an install hint

Reason: screening runs in the thousands of episodes. On `grid3d` a 90-second
mission executes in <1 s wall time with no GPU, so a 15-architecture × 8-seed
sweep finishes in about a minute. Forcing every sweep through a renderer would
make cheap screening pointlessly slow, and would bake one renderer's quirks into
every result. Details in `docs/SIMULATORS.md`.

A second *working* adapter (`scene_replay`) exists so the adapter boundary has
two implementations behind it rather than one assumption.

## Bugs found and fixed while building

These were all found by measurement, not by reasoning about the code.

| Bug | Symptom | Fix |
|---|---|---|
| Clock un-parked roles late | Episodes truncated at 0.1 s | Un-park at future-resolution time, not on coroutine resume |
| Scalar ray casting | 1.7 M distance calls/episode, 15 s per run | Vectorised the whole depth fan; 0.96 s per run |
| Memory stored any label | Drone flew confidently to a distractor and "succeeded" | `MemoryItem.label` + label-filtered recall |
| Planner/shield disagreed on "clear" | C0 wedged, 1723 safety interventions | One shared `min_clearance()`; planner reserves braking distance |
| 22.5° gaps between rays | Obstacles invisible between rays | 24 rays + windowed (not single-ray) clearance |
| Exploration circled the origin | Search never expanded | Spiral anchored to launch point, radius grows per leg |
| Exploration turned per *decision* | 10 Hz VLA swept 10× faster than 1 Hz skill agent | Heading advances on the clock — would have contaminated the authority comparison |
| `ConfigError(ValueError)` | Pydantic swallowed it; CLI never printed violations | Inherit from `Exception` |
| Pump exited with no roles registered | Silent hang | Raises immediately with the reason |

## Real models: what is possible on this machine

### Answer to "are you using an actual VLA / any vision?"

**No, to both.** Before this section's work:

- `mock_vla` / `chunk_vla` / `world_model_vla` were closed-form geometry — a unit
  vector toward a believed target, scaled by cruise speed. No network, no weights.
- `vlm_waypoint` was the same arithmetic at a different authority level.
- **Nothing rendered.** `observation.rgb` was a `SensorRef` holding a hash of the
  pose, with `shape=(224,224)` reported for an image that did not exist. That
  field is now `None`, and the uri scheme is `stub://`.
- The "detector" was the environment filtering its own landmark list by range,
  FOV and occlusion, then adding noise. `IdentityPerception` copied it through.
- `grep -rE "import (torch|cv2|transformers)" src/` returned nothing.

I also had a comment in `_action_velocity` calling the hand-written potential
field "learned reactive avoidance". Corrected — that is exactly the label that
makes a scripted baseline read as a model result.

### Renderer added

`src/uavlab/adapters/gym/render.py` — pinhole projection of the box world from
the vehicle camera, painter's algorithm, distance fog, 224×224. Crude by
intent (no texture, no lighting), but the image content is a true function of
pose and scene, so a vision model has something real to look at. It honours the
same occlusion and dropout rules as the sensor model via `visible_labels`, so a
scheduled sensor dropout is not still visible in the picture.

### Gemma 3 4B — works

Available through the local Ollama daemon as `gemma3:4b` (Q4_K_M, 3.3 GB).

Ollama's own metadata lists its capabilities as `["completion"]` with **no
vision** — that is wrong. Tested directly:

| probe | result |
|---|---|
| synthetic red rectangle, "what colour?" | `Red` — correct |
| rendered frame, target occluded by a box | `No` — correct, it *was* occluded |
| rendered frame, clear line of sight | `YES`, located `Right` — correct |

So the C2–C6 waypoint family can run on a real VLM. Worth noting the third row:
the model got the occluded case right, which means it is reading the image
rather than pattern-matching the prompt.

### AerialVLA — blocked, needs a decision

`XuPeng23__AerialVLA` is **LoRA adapter weights only** (462 MB
`adapter_model.safetensors` + `adapter_config.json`). Its config says:

```json
"base_model_name_or_path": "./openvla-7b",  "r": 64,  "lora_alpha": 128
```

Four things are missing to run it:

| need | state |
|---|---|
| OpenVLA-7B base weights | not on this machine; ~14 GB download |
| `peft` (to apply the LoRA) | not installed |
| `bitsandbytes` (4-bit, to fit the GPU) | not installed |
| VRAM | RTX 4060 Laptop; a 7B in bf16 will not fit, 4-bit ≈ 5 GB will |

Alternative already local: `euphoria-64__CoTinyVLA-Qwen3.5-0.8B` (1.7 GB raw
`student_state_dict.pt` plus an action-head config). Small enough to run
comfortably, but it ships as a bare state dict, so it needs its own loader
rather than `from_pretrained`.

Also present and vision-capable in Ollama: `qwen3-vl:2b`, `qwen3-vl:8b`,
`moondream`.

### Gemma 3 4B wired into C2–C6 — done, and it flies

Five new configurations, `c2g`–`c6g`, each inheriting its scripted counterpart
and swapping exactly two things: the policy and the inference backend.

New components:

| piece | what it does |
|---|---|
| `adapters/gym/render.py` | pinhole rasteriser; real 224×224 frames from the box world |
| `core/frame_store.py` | bounded uri→image store, so `SensorRef` resolves to pixels |
| `plugins/inference/ollama.py` | calls the local daemon, charges **measured** latency to the sim clock |
| `plugins/reasoning/vlm.py` | point-and-fly policy: Gemma returns a *pixel*, code does the geometry |
| `configs/environments/grid_nav_vision.yaml` | `grid_nav` with the camera on, identical otherwise |

**Design choice worth defending.** The model is never asked for coordinates. It
is shown the frame and asked which *pixel* to head for; `Camera.unproject` turns
that into a waypoint, and the round-trip against `project` is exact to 1e-15.
Asking a 4B model for "x=12.4, y=-8.1" would test its ability to invent
plausible numbers. Asking it to point tests visual grounding, which is what C2
actually claims to be about — and it keeps the failure modes separable: a wrong
pixel is perception, a wrong waypoint from a right pixel is a geometry bug.

**Live result, `c2g` on `grid_nav_vision`, seed 1:**

| | |
|---|---|
| parse failures | **0** — Gemma returned clean JSON on every call |
| target found | 7 of 11 frames (0.64) |
| mean policy latency | **4.83 s** per decision |
| decisions in a 60 s episode | 11 |
| median decision age | **7.45 s** |
| distance to goal | 35.7 m → **22.6 m** (it navigates) |
| outcome | timeout — real, not a bug |

The headline is the decision age. Gemma 3 4B **works** as a waypoint policy and
is **far too slow to hold waypoint authority in real time on this hardware**: the
vehicle acts on where the world was 7.5 seconds ago. The staleness bound had to
be raised from 1.5 s to 8 s for the configuration to run at all, and that gap is
a finding rather than a tuning knob — it is exactly the "authority × latency
budget" interaction the study is built to expose.

**Two bugs found by running it:**

1. `IdentityPerception` was calling the inference backend to "charge detector
   latency". Harmless against a simulated backend where latency is bookkeeping;
   against Ollama it fired an **empty prompt at Gemma, 5.1 s at a time**, burning
   half the episode budget on replies nobody read. Default is now off.
2. `import uavlab` began pulling in `http.client` via the Ollama backend. Real
   model adapters now load on first use through
   `registry.OPTIONAL_PLUGINS`, the same treatment PX4 and AirSim get, so the
   core runtime still imports nothing that touches a network.

**Tests:** 195 passing. `tests/integration/test_vlm_policy.py` covers the policy
against a stub backend — no network, no weights — including that pointing left
and right yields waypoints on opposite sides, that prose-wrapped JSON still
parses, and that a **missing frame raises** rather than silently degrading to a
blind policy that would still emit plausible waypoints.

Run it:

```bash
uavlab run --arch c2g --env grid_nav_vision --seed 1
```

### "Can you quantize Gemma?" — it already is, and that was not the problem

`gemma3:4b` as installed is **Q4_K_M** GGUF, 4.3 B params, 2.88 GB, **100 % resident
on the GPU**. There is no unquantized version in play.

So I measured where the 4.05 s per call actually went, by subtracting the
server's own reported timings from measured wall time:

| component | time | share |
|---|---|---|
| unaccounted overhead | **2.08 s** | 51 % |
| reported `load_duration` | 1.42 s | 35 % |
| prefill (prompt + image) | 0.18 s | 4 % |
| decode | 0.37 s | 9 % |

Only about **0.55 s is real GPU compute**. A perfect 2× quantisation win would
have saved 0.28 s out of 4.05 s — under 7 %.

**What the 2.08 s was.** I ran the same probe against `gemma3:4b`, `moondream`
and `qwen3-vl:2b`. The overhead was 2.08 s for *all three*, to two decimals.
A constant that does not vary with model size is not model compute — it is
transport. My backend was opening a **fresh TCP connection per call**.

Reusing one keep-alive connection:

| | new connection each call | persistent connection |
|---|---|---|
| wall per call | 4.05 s | **1.80 s** |
| unaccounted overhead | 2.08 s | **0.02 s** |

**Effect on the actual mission** (`c2g`, `grid_nav_vision`, seed 1):

| | before | after |
|---|---|---|
| mean policy latency | 4.83 s | **2.56 s** |
| decisions in a 60 s episode | 11 | **19** |
| median decision age | 7.45 s | **4.00 s** |
| final distance to goal | 22.6 m | **5.7 m** |

The drone now gets within 5.7 m of a 2 m goal radius instead of stalling at
22.6 m. Same model, same quantisation, same hardware — the entire gain was a
transport bug in code I had written an hour earlier.

**The lesson worth keeping.** My first instinct when told "4.83 s per decision"
would have been to reach for a smaller or more aggressively quantised model. That
would have cost hours and bought under 7 %. Splitting measured wall time against
the server's self-reported load/prefill/decode is what made the real cause
visible, and running three different models is what proved it was transport
rather than compute.

### Chasing the 1.4 s "load"

Characterised, partially reduced, and **not fully eliminated**. What it is:

**It is real time, not a reporting artifact.** Streaming shows time-to-first-token
of 1.49 s, matching the reported `load_duration`. The wall clock really does pass.

**It is not a model load.** Forcing a genuine reload by changing `num_ctx` costs
**5.5–7.6 s**. The recurring 1.4 s is an order of magnitude cheaper, so it is a
different thing wearing the same label.

Ruled out, each by measurement:

| hypothesis | test | result |
|---|---|---|
| the vision tower reloads per image | text-only vs image calls | **1.45 s either way** — not image-driven |
| VRAM pressure evicting the model | unloaded the other two models (6.09 → 2.88 GB held) | **1.39–1.44 s unchanged** |
| model not staying resident | `keep_alive: 30m` + `/api/ps` | resident, future `expires_at`, cost persists |
| prompt-cache invalidation | identical prompt repeated | prefill drops 0.74 → 0.05 s, load **unchanged** |
| options forcing re-init | omitted the options block entirely | unchanged |

**What it correlates with is model size:**

| model | reported load |
|---|---|
| moondream (1.8 B) | 0.19 s |
| qwen3-vl:2b (2 B) | 0.62 s |
| gemma3:4b (4.3 B) | 1.42 s |

So it is per-request setup inside Ollama 0.32.14 that scales with the model,
and it is not reachable from the client.

**The one lever that worked: `/api/chat` instead of `/api/generate`.**

Because the chat endpoint applies Gemma's chat template, this could easily have
bought speed at the cost of accuracy — and the first episode after switching
*looked* like exactly that, with found-rate falling 0.474 → 0.238. That was a
confound: a faster policy flies a different trajectory and therefore sees
different, harder frames.

Controlled A/B on **identical frames with ground-truth visibility**
(`scratchpad/ab_endpoint.py`, 14 frames):

| endpoint | accuracy | TP / TN / FP / FN | unparsed | mean wall |
|---|---|---|---|---|
| `/api/generate` | 0.93 | 13 / 0 / 1 / 0 | 0 | 2.52 s |
| `/api/chat` | 0.93 | 13 / 0 / 1 / 0 | 0 | **1.70 s** |

Byte-identical quality, 33 % faster. Switched, and `load_duration` is now
reported separately as `inference_server_setup_s_*` so it can never be read as
model compute.

**Where the per-call latency ended up:**

| stage | before | after |
|---|---|---|
| transport overhead | 2.08 s | 0.02 s |
| server setup ("load") | 1.42 s | ~1.24 s |
| prefill + decode | 0.55 s | 0.46 s |
| **total** | **4.05 s** | **~1.7 s** |

**Honest limits of this result.** The residual ~1.2 s is Ollama-internal; the
remaining levers are a smaller model or a different serving stack, not anything
in this repository. And the single-seed episode outcomes quoted through this
section (5.7 m, 37.8 m) are **noise** — one seed, and timing changes shift the
whole trajectory. The paired `c2` vs `c2g` screen over multiple seeds is what
would actually measure this, and it has not been run.

The A/B benchmark is also weak on negatives: 13 of 14 frames had the target
genuinely visible, so it measures detection but barely tests false positives.
Worth rebuilding with a balanced set before any claim about VLM precision.

### Can OpenVLA run at 1-bit?

No — and it does not need to.

**Why 1-bit is not available.** `bitsandbytes` implements 8-bit and 4-bit only;
there is no 1-bit path in it. Genuine 1-bit comes in two flavours and neither
applies:

- *BitNet b1.58* (ternary weights) is **pretrained** ternary. You cannot convert
  an existing fp16 checkpoint into one — the ternary constraint has to be present
  during training. OpenVLA is not a BitNet model.
- *Post-training binarisation* (BiLLM, OneBit, PB-LLM) is research-grade, needs
  calibration or distillation, and has no working integration for a
  Prismatic-style VLM carrying two vision encoders (DINOv2 + SigLIP).

**Why it would be a bad idea even if it were available.** OpenVLA does not
regress actions directly; it **discretises each action dimension into 256 bins
and re-purposes the least-used tokens of the Llama vocabulary** to represent
them. Binarising the embedding and LM-head weights scrambles precisely that
token→action-bin mapping. The failure mode is not a crash — it is confident,
well-formed, wrong actions. In this project that is the worst possible outcome,
because it is indistinguishable from an architecture result.

**4-bit already fits.** Measured on this machine: 8.00 GB VRAM, **6.94 GB free**.

| | estimate |
|---|---|
| OpenVLA-7B params (Llama-2 7B + DINOv2 + SigLIP) | ~7.5 B |
| NF4 weights | ~3.8 GB |
| vision encoders kept in fp16 | ~0.7 GB |
| KV cache + activations, one image, short prompt | ~1.0–1.5 GB |
| **total** | **~5.5–6 GB — fits in 6.94 GB** |

4-bit loading is the documented path for OpenVLA, so this is well-trodden rather
than experimental.

**The actual blockers are mundane:**

| blocker | detail |
|---|---|
| base weights | ~14 GB download, not present |
| disk | **34 GB free on C:, 97% full** — enough, but not comfortable |
| `peft` | not installed (needed to apply the LoRA) |
| `bitsandbytes` | not installed (needed for NF4) |
| `transformers` 4.44.2 | OpenVLA loads with `trust_remote_code=True`; version is plausible but untested here |

**Throughput consequence, worth deciding on before committing.** OpenVLA-7B at
4-bit on a 4060 Laptop will realistically give low single-digit Hz for
single-image action prediction. The C7–C14 configs currently ask for a 10 Hz
decision loop. Two implications:

1. The real model cannot hit the configured rate, which is itself a legitimate
   finding — but it must be *measured* and written into the model profile, not
   assumed.
2. Episodes stop being free. The current 360-episode audit runs in ~4 minutes on
   simulated latency; against a real 7B it becomes hours. Real-model runs should
   be a small promoted subset, not the screening sweep — which is exactly the
   staging the spec already prescribes.

## Audit: are the architectures actually working?

**No — only one of three regimes produces usable numbers.** My earlier summary
was wrong, in two specific ways.

### Correction 1: "C0 = 1.00" was one regime and a lucky seed set

I measured the control ceiling on `grid_nav` with seeds `[3,5,7,11,13,17,19,23]`
and reported 1.00. On seeds `1..8` it is **0.88**, and I had never measured it in
the other regimes at all. The spec's gate is per-environment; I applied it to the
easy one and generalised.

Now enforced properly: `test_the_oracle_is_competent_in_every_regime` runs the
gate across all five regimes.

### Correction 2: `failure_recovery` was rigged, and I did not notice

`block_path` placed its obstacle at the **midpoint between the vehicle and the
goal**. By the time it fired at t=8 s the vehicle was usually past that point, so
the box materialised on top of a drone at cruise speed:

| seed | distance from drone to box at spawn | speed |
|---|---|---|
| 3 | 0.92 m | 4.6 m/s |
| 4 | 0.46 m | 4.3 m/s |
| 5 | **−2.34 m** (inside the box) | 4.6 m/s |
| 8 | **−1.23 m** (inside the box) | 4.2 m/s |

Five of eight seeds were unavoidable or literal teleport-into-wall. The regime
was measuring vehicle teleportation, not recovery.

It hid because it hit every architecture equally, so the table still looked like
a plausible spread. The oracle is what exposed it: a configuration with perfect
semantics has no business colliding 62% of the time.

**Fixed.** Blockages now stage along the direction of travel at
`max(lead_m, stopping_distance + box_depth)`, are never placed beyond the goal,
and are skipped and counted if no fair placement exists. C0 on
`failure_recovery`: SR 0.12 → **0.75**, collisions 0.62 → **0.12**. Regression
tests in `tests/integration/test_injection_fairness.py`.

### Post-fix state, 8 seeds per cell

| arch | grid_nav | object_search | failure_recovery |
|---|---|---|---|
| C0 (ceiling) | 0.88 | 0.62 *(0.25 coll)* | 0.75 |
| C1 | 0.12 | **0.00** | 0.00 |
| C2 | 0.62 | 0.62 | 0.12 |
| C3 | 0.50 | 0.50 | 0.00 *(0.38 coll)* |
| C4 | 0.75 | 0.50 | 0.12 *(0.38 coll)* |
| C5 | 0.62 | 0.38 | 0.12 *(0.38 coll)* |
| C6 | 0.50 | 0.38 | 0.00 *(0.38 coll)* |
| C7 | 0.75 | **0.00** | 0.12 |
| C8 | 0.62 | **0.00** | 0.12 |
| C9 | 0.75 | **0.00** | 0.12 |
| C10 | 0.38 | **0.00** | 0.00 |
| C11 | 0.38 | **0.00** | 0.00 |
| C12 | 0.62 | 0.12 | 0.12 |
| C13 | 0.62 | 0.12 | 0.12 |
| C14 | 0.62 | 0.12 | 0.12 |

Verdict per regime:

- **`grid_nav` — usable.** Ceiling 0.88, spread 0.38–0.75, no floor/ceiling
  pileup. Architecture contrasts here are worth reading.
- **`object_search` — not usable.** Six architectures score exactly 0.00,
  including the entire single-action VLA family. A regime where a third of the
  set cannot score discriminates nothing. The ceiling is also marginal (0.62 SR
  with 25% collisions), so the substrate is shaky there too.
- **`failure_recovery` — not usable yet.** The ceiling is fixed, but every
  non-oracle architecture sits at 0.00–0.12, and the waypoint family (C3–C6)
  collides 38% of the time. Both need diagnosis before the regime means anything.

### What the audit *did* confirm

Every architecture's distinguishing component fires in every regime — no
component is configured-but-inert. Verifiers act, monitors emit STOP/LOST,
shields intervene, reasoners run, chunks execute, triggers admit. So the wiring
is real; the calibration is not.

### Still unexplained

- **C1 (skill agent) 0.00–0.12 everywhere**, 88% timeouts on grid_nav.
- **Whole VLA family 0.00 on `object_search`**, mostly timeouts.
- **C3–C6 38% collisions on `failure_recovery`** while C7–C9 collide 0%.
- **C10/C11 worst on grid_nav (0.38)** despite being C8 plus a reasoner —
  adding the hierarchy makes it worse, which needs an explanation rather than a
  shrug.

## Known gaps

- Real LLM/VLM/VLA adapters (Milestone D) — each replaces one plugin, nothing else.
- PX4/Gazebo and Project AirSim adapters are stubs (Milestone C).
- `ruff`/`mypy` are wired into CI but not installed locally, so they have not
  been run here.

## Teacher swapped to C2, and what it did and did not fix

`uavlab collect` no longer defaults to the oracle. The seed split is now
declared in `training/splits.py` and enforced: `EVAL_SEEDS = 1..40` is held out
and `collect()` raises if a requested range touches it. (The previous run was in
fact clean — trained on seeds 1000–1199, scored on 1–40 — but by default rather
than by rule.)

### Why C2 and not C0

C0 is handed the true goal position and flies confidently toward a target that
is off-camera 61% of the time; its label is not a function of the student's
observation, so no network can recover it. C2 decides from live detections and
carries no memory, so its action *is* a function of the current view.

Teacher scores on `grid_nav_vision`, 40 held-out seeds:

| | success | collisions | path |
|---|---|---|---|
| c0 (privileged ceiling) | 0.85 | 0.10 | 43 m |
| **c2** | **0.68** | **0.00** | 167 m |
| c5 | 0.65 | 0.05 | 123 m |
| c6 | 0.62 | 0.05 | 144 m |

C5/C6 were rejected for a second reason beyond the score: their memory is
hidden state the student does not have, which reintroduces the same privileged
-information problem in miniature.

### The result

53,543 samples from 160 of 250 flights (2.0 GB). Training improved on every
open-loop number — bin accuracy 0.230 → 0.328, velocity error 1.875 → 1.500 m/s.

**Closed-loop success is still 0/40 for both c7t and c8t.** The policy flies
78 m and ends 74 m from the goal.

### The measured reason: it cannot turn

Per-dimension mean absolute error on held-out frames, against the best possible
*constant* predictor for that dimension:

| dim | policy | best constant | |
|---|---|---|---|
| vx | 0.975 | 2.480 | learned |
| vy | 0.949 | 2.524 | learned |
| vz | 0.053 | 0.053 | tie |
| **yaw_rate** | **0.319** | **0.294** | **worse than a constant** |

So the policy reads the image for translation and has learned nothing at all
about yaw. That is fatal in closed loop specifically because the camera is
body-fixed: a policy that never turns toward the target loses it from frame,
and once lost it never comes back. 76% of the training frames already have no
target in view; a non-turning policy drives that to ~100% within seconds, which
is exactly the 74 m drift observed.

Yaw is the one channel C2 cannot teach from a single frame. Its yaw command
depends on the waypoint it committed to earlier and on its exploration clock —
hidden state, the same failure as C0, isolated to one dimension.

An earlier "imitability" measurement (heading concentration R=0.983 for C2)
looked reassuring and was near-worthless: it measured the heading of the
velocity vector, which is near-zero almost always because C2 steers by yawing
and then flying forward. Concentration of a near-constant says nothing. The
per-dimension comparison against a constant baseline is the check that has
teeth, and it is the one to run first next time.

Nobody should read c7t/c8t numbers as an architecture result yet.

## Course-aligned yaw: fixed the drift, exposed a deadlock

`learned_visuomotor` gained `yaw_mode` (default `course_aligned`): the nose is
pointed along the commanded velocity by a rule, and the network's yaw output is
ignored. `learned` is still selectable so the comparison stays runnable.

Effect on 40 held-out seeds — final distance from goal 74 m -> 28 m, path 78 m
-> 25 m. So the vehicle now heads roughly the right way. Success is still 0.00.

Also added `terminate_consecutive` (default 3), requiring the stop head to agree
across consecutive decisions. **It changed nothing — every number identical.**
The false stops are therefore systematic, not frame-level noise: the policy
enters a region where it is persistently confident it has arrived. Recorded here
because the fix that does nothing is worth knowing about.

### What the trace shows

Tracing commanded velocity through one episode (`c8t`, seed 1) is unambiguous:

```
   0.0 ( 0.0, 0.0)  cmd (4.96, 0.08)  4.96 m/s
   2.2 ( 5.9, 0.0)  cmd (0.08,-0.08)  0.12 m/s
  ...  22 seconds of the identical command ...
  25.3 (13.9,-1.8)  cmd (1.38, 0.08)  1.38 m/s
  28.6 (16.0,-1.7)  cmd (1.38, 0.08)  1.38 m/s
  38.5 (16.0,-1.7)  cmd (1.38, 0.08)  1.38 m/s   <- position frozen 15 s
```

The command is bit-identical for hundreds of consecutive decisions. The vehicle
drives into an obstacle, the shield holds it there, the view stops changing, and
because the view stops changing the policy re-emits the same command forever. A
genuine fixed point: stationary -> same image -> same command -> stationary.
Without the shield (c7t) the same behaviour is a collision, 45% of episodes.

This is compounding error in behaviour cloning, in its most literal form. The
teacher never sits pressed against a wall, so no training frame resembles this
state, so the policy's output there is arbitrary — and arbitrary happens to be
constant.

### Why obstacle avoidance did not transfer

In C2 the avoidance is done by the classical local planner downstream of the
policy. The collector records the final commanded velocity, so avoidance *is*
present in the labels — but only as a correlation the student must rediscover
from pixels, and it has not.

### Next: DAgger

The standard remedy, and it targets this failure exactly. Run the student, query
C2 for what it would have commanded at the states the student actually visited,
add those pairs, retrain. The stalled-against-a-wall states get labelled "back
off and go around" instead of being absent from the dataset. All the parts exist:
C2 is queryable at any state, and the collector already patches `step`.

Nobody should read c7t/c8t numbers as an architecture result yet.

## DAgger

`uavlab dagger` — new command, `training/dagger.py`. Rolls the trained student
out, asks C2 what it would have commanded at each state the student reached, and
appends those pairs to the base dataset.

The teacher is a full architecture (policy -> planner -> controller) with a
waypoint that is stateful across ticks, not a function from image to velocity.
So rather than reconstruct a teacher-evaluator, an ordinary C2 orchestrator runs
and the executed command is substituted inside `step`: C2 observes, reasons and
produces its command as usual — that is the label — and the vehicle then moves
according to the student. C2's memory and exploration clock therefore evolve over
student-visited states, which is what DAgger requires.

`beta` is the probability of executing the teacher's command on a tick.

### Harness check before trusting it

8 seeds at three settings, confirming the substitution actually takes effect
rather than silently doing nothing:

| beta | who drives | successes |
|---|---|---|
| 1.0 | teacher | 6/8 |
| 0.5 | mixture | 6/8 |
| 0.0 | student | 0/8 |

beta=1.0 reproduces C2's own 0.68 and beta=0.0 reproduces c7t's 0.00, so the
knob is real and connected at both ends. Worth stating because a substitution
that quietly failed would have produced a plausible dataset and a wasted
retraining run.

All ticks are kept, successes and failures alike — the states worth adding are
precisely the ones where the student went wrong, and the success filter that is
correct for plain cloning would discard exactly them.

`_append` concatenates on disk through a memmap: the base frame array is 2 GB
and `np.concatenate` would transiently need three copies.

## DAgger did not help, and the reason corrects an earlier claim

150 rollouts at beta=0.25 added 52,684 teacher-labelled samples from
student-visited states; total 106,227 (4.0 GB). Retrained.

Held-out seeds 1-40, success still 0.00 / 0.03. Final distance from goal got
*worse*: 28 m -> 50 m. Open-loop also degraded (bin accuracy 0.328 -> 0.173),
which is expected on a harder aggregated set and is not the interesting part.

To separate navigation from stopping, both checkpoints were rerun with the stop
head disabled, so `reached_goal` measures navigation alone:

| checkpoint | reached_goal | final distance |
|---|---|---|
| bc_c2 | 0.03 | 28 m |
| bc_dagger | 0.05 | 60 m |

Unchanged. DAgger bought nothing.

### The claim that was wrong

I said C2 was the right teacher because "it has no memory, so its action is a
pure function of the current frame". That is false. C2 has no memory *plugin*,
but the architecture is stateful in two ways that matter more:

* it decides at 2 Hz and controls at 20 Hz, so 9 of every 10 recorded labels
  come from the planner tracking a waypoint chosen up to half a second earlier;
* `explore_target` advances on a sim-time clock, and 76% of frames are
  exploration.

So the label was never a function of the student's observation. C2 is less
privileged than C0, not unprivileged.

That also explains why DAgger could not help. DAgger corrects the *state
distribution* — it does not make a label deterministic given the observation.
The failure here was never distribution shift alone; two frames that look
identical to the student carry different labels because C2 was flying toward
different committed waypoints. No amount of relabelling fixes that.

### What is left

Give the student memory — a frame stack or recurrent state — so it can carry the
committed direction the teacher is carrying. This was one of the two options
identified before the teacher swap, and eliminating the other one is what the
last three runs bought.

Nobody should read c7t/c8t numbers as an architecture result yet.

## Frame stack: fixed stopping, did not fix navigation

`PolicyConfig.frame_offsets = (0, 5, 15, 40)` — a *dilated* history spanning 0,
0.5, 1.5 and 4.0 seconds, not four consecutive frames. Four consecutive stored
samples span 0.3 s, which is long enough to see motion and far too short to
remember where a target was last seen.

This required something the datasets did not have. Samples from different
flights sit back to back in `frames.npy`, so an unclamped history window reads
the end of the previous flight as the start of this one. `collect()` and
`dagger.aggregate()` now write `episodes.npy`, `train()` clamps every offset to
the first sample of its own episode, and it raises rather than guessing if the
index is absent. `FrameHistory` in `policy_net.py` is the inference-time
counterpart, shared by the plugin and the DAgger rollout driver so the two
cannot drift.

Trained on the same 53,543 C2 samples as the single-frame policy:

| | single frame | frame stack |
|---|---|---|
| bin accuracy | 0.328 | 0.345 |
| velocity error | 1.500 | 1.334 m/s |
| **stop precision** | **0.44** | **0.95** |

### What it fixed

Stopping, decisively. `agent_stopped` terminations on 40 held-out seeds went
from 24/40 to 1/40. Whether the vehicle is arriving is a question about motion
over time, and a single frame genuinely cannot answer it — this is the one place
where history was obviously the right tool and it worked.

### What it did not fix

Navigation. Success 0.03. c8t now times out 39/40 at 31 m from a goal that
started 35 m away; c7t collides in 57% of episodes.

### Where that leaves the learned policy

Three interventions, each targeting a measured failure, each verified:

| | reached_goal |
|---|---|
| C0 teacher, single frame | 0.00 |
| C2 teacher, single frame | 0.03 |
| + DAgger | 0.05 |
| + frame stack | 0.03 |

Navigation has not moved. Each intervention fixed the specific defect it was
aimed at — the velocity shortcut, the non-turning yaw channel, the false stops —
and none of them was the binding constraint on reaching the goal.

C7-C14 already run with the scripted `mock_vla` in the direct-action slot, so
none of the architecture comparisons are blocked on this. The honest status is
that `c7t`/`c8t` are a working *pipeline* (collect -> train -> DAgger -> fly, all
reproducible) carrying a policy that does not yet navigate, and their numbers
must not be read as an architecture result.

## Verification of all architectures

`uavlab verify` over the full set (22 configs: C0-C14 plus the `g` and `t`
variants), three seeds each, on `grid_nav` — vision architectures routed to
`grid_nav_vision`.

**21 of 22 passed. The one failure was c2g**, on the determinism check:
final distance 28.462555 vs 28.461193 for the same seed. 1.4 mm, but the check
is right to fail it — paired-by-seed comparison is the whole method.

Chased rather than assumed. Capturing every Gemma response across two runs in
one process: 23 calls each, byte-identical. Across three separate processes:
identical to nine decimal places. So it is intermittent, and it is not the
harness — the residual variation is inside the server's GPU kernels, where
batching and memory pressure change reduction order. No client-side option
reaches it.

`sampling_seed` is now pinned and sent with every call. That is the one lever
that is ours, and it is honest about not being sufficient — the docstring says
so rather than implying the problem is solved. c2g and c3g both verify clean
after it, but "clean on a re-run" is not proof for an intermittent fault.

Why c2g specifically and not c3g-c6g: C2 maps the emitted pixel straight to a
waypoint, so nothing downstream absorbs a one-pixel difference. The verifier and
monitor in C3-C6 do absorb it.

### Reading the table

Success rates in the verify output are reported for information only — the
checks test that an architecture *functions*, not that it performs. Two things
in that table are worth following up separately: c1 still scores 0.00, and
c3g/c4g/c5g produce identical distance, path and collision figures, which is
suspicious for three architectures that differ.

## Why C1 scores near zero

Traced rather than guessed. Over a full episode C1's belief source is `none` on
every one of 37 decisions — it never once detects the target and explores blind
until the horizon. But so does C2 for long stretches, and C2 scores 0.70 on the
same seeds, so "never sees the target" is not the answer by itself.

The answer is an interaction between two things, neither of which does the
damage alone. On 20 seeds of `grid_nav_vision`:

| | success |
|---|---|
| C1 as shipped (1 Hz, scan every 3rd decision) | 0.15 |
| without the scan skill | 0.15 |
| at 2 Hz, scan unchanged | 0.20 |
| without the scan, at 2 Hz | 0.60 |

A `scan` is a whole decision spent rotating in place. At 1 Hz, one scan in every
three means a third of the mission is not spent flying anywhere — and at 1 Hz
there are only ~60 decisions in an episode to begin with. Doubling the rate
without removing the scan just buys more scans; removing the scan without
raising the rate leaves too few decisions to search with. Only both together
recover the performance.

Cost is set by scan *frequency*, not duration, which is what confirms the
reading — decisions are the scarce resource, not seconds:

| at 1 Hz | success |
|---|---|
| scan 1.0 s every 3 (shipped) | 0.15 |
| scan 0.4 s every 3 | 0.15 |
| scan 1.0 s every 6 | 0.35 |
| scan 0.4 s every 6 | 0.20 |

### What is a result and what is a bug

The 1 Hz rate is deliberate and is part of what C1 *is* — a skill agent is
expensive per call, and raising the rate would quietly turn C1 into a different
architecture. That a low call rate handicaps a task requiring search is a
genuine finding, and precisely the falsifying result `c1_llm_skills.yaml`
anticipated.

The scan frequency is not. It was chosen without reference to the decision rate,
and it currently dominates the architecture signal: C1 reads as 0.15 when the
defensible number for its own design is 0.35.

`scan_every` and `scan_duration_s` are now parameters so this is measurable
rather than arguable. Defaults are unchanged pending a decision on whether to
set `scan_every: 6` for C1.

`scan_every: 6` is now C1's default. Verified: PASS, and 0.35 success over 40
held-out seeds (was 0.15), with zero collisions. 1 Hz is untouched. 224 tests
pass.

## Why C3G, C4G and C5G report identical numbers

Because they fly identical trajectories. On seed 1 all three end at exactly
34.1546 m with a 114.9097 m path. The scripted C3/C4/C5 differ from each other
normally (0.33 / 0.67 / 0.33), so this is specific to the Gemma variants.

The components are not missing. C4G and C5G each run 15 monitor assessments, 13
of which return LOST, and each carries a different memory plugin. The event logs
show them firing. What differs between C3G and C4G is *only* cost:
`inference_calls_total` 22 vs 37, `tokens_per_minute` 557 vs 1517,
`monitor_assessments` 0 vs 15. Not one metric of motion differs.

### The cause

`VLMPointWaypoint.decide` never calls `self.believe(ctx)`. It asks Gemma; if
Gemma reports the target is not visible it goes straight to `explore_target`.
The belief chain — live detection, then the reasoner's directive, then remembered
evidence — is where memory and supervision enter a policy's behaviour, and this
policy does not consult it. So the memory plugin and the monitor's LOST calls
have nowhere to land.

C2's `vlm_waypoint` does consult it, which is why the scripted C3/C4/C5 separate
and the Gemma ones do not.

### The verification gate missed this

`uavlab verify` checks that each architecture's distinguishing component *fires*,
and by that standard C4G and C5G pass honestly: the monitor runs, the memory
updates. Firing is not the same as influencing. A component that consumes real
compute and changes no behaviour is exactly the failure the gate exists to catch,
and the check as written cannot see it.

The check needs to compare against the same architecture with the component
removed and require the trajectory to differ. That is a stronger and more
expensive test, and it is the right one.

### Consequence for the results

Any C3G/C4G/C5G comparison currently measures token cost and nothing else. The
memory and supervision contrasts for the real model are not yet testable.

## C2G's nondeterminism was a frame leak, not GPU noise

I called it intermittent GPU nondeterminism. It was not: the full sweep
reproduced the *same two values* — 28.462555063 vs 28.461193430 — so it was
deterministic and structural.

Replicating verify's exact sequence for c2g (seeds 1, 2, 3, then seed 1 twice)
showed the pattern:

```
results seed 1        d=28.462555063
results seed 2        d=36.869823639
results seed 3        d=31.826341575
determinism run A     d=28.462555063
determinism run B     d=28.461193430   <- diverges
```

Frame URIs were `frame://{id(env)}/rgb/{seq}`. `id()` is an object address that
CPython recycles as soon as the previous environment is collected, and the frame
store is process-global and was never cleared by anything. So a new episode
could resolve a reference to the *previous* episode's pixels — and the
`max(self._seq - 1, 0)` lookups at the very start of an episode are exactly
where that lands.

Fixed with a monotonic namespace per episode, which cannot be recycled, plus
`global_store().clear()` on reset. All three seed-1 runs now agree, on
28.461193430 — the value fresh processes always produced. 28.462555063 was the
contaminated one.

`test_frames_never_leak_between_episodes` asserts on the URIs rather than on a
trajectory, so it names the cause instead of reporting a number that happens to
differ. Confirmed to fail against the pre-fix code.

Why only c2g showed it: C2 maps the emitted pixel straight to a waypoint with
nothing downstream to absorb a one-frame difference. The verifier and monitor in
C3–C6 absorb it, which is why they verified clean while carrying the same bug.

**All 22 configurations now pass every structural check.**

## The Gemma believe() gap, closed

### Proving it was the cause

Reading the code showed `VLMPointWaypoint.decide` never calls `believe()`. That
is not proof, so it was tested by removal: strip the memory plugin and see
whether the trajectory moves.

| | memory changes the trajectory |
|---|---|
| c5 (scripted) | 3 of 10 seeds |
| c5g (Gemma), before | **0 of 8 seeds** |
| c5g (Gemma), after | **3 of 3 seeds** |

A first attempt at this test used one seed and showed no change for the
*scripted* c5 either — on seed 1 the target stays visible and memory is never
consulted. A component that is inert on one episode is not an inert component.

### The trap that shaped the fix

Memory stores are fed from `perception.detections` — the simulated detector.
Wiring `believe()` in as-is would have let the Gemma policy recover the
detector's sightings through memory, and c5g's "memory result" would really be a
detector result, in a configuration whose entire premise is that a real model is
the perceiver.

So the policy now remembers only what *it* concluded. `_decision_memory` records
the policy's own committed waypoint under `kind="decision"`, and `recall_target`
takes a `kinds` filter so the Gemma policy can ask for that and nothing else.

### Two bugs found on the way, both by measurement

**Memory refreshed itself.** Steering on a recalled target produced another
labelled waypoint decision, which was written back to memory with a fresh
timestamp. The policy latched: it flew 9–17 m in a 60 s episode against 113–115 m
with no memory, orbiting a position the model could no longer confirm. Adding a
`memory_trust_s` age limit changed *nothing at all* — the timestamp was never old.
The fix is that a decision marked `from_memory` is never written back, and only
then does the age limit do anything.

**The recall branch was broken at runtime while 225 tests passed.** `provenance`
is `dict[str, str]` and the marker was a bool, so every c5g episode ended in
`runtime_error` — and no test noticed, because none exercised recall. Three tests
now do, including one asserting the detector is *not* reachable through memory.

### Where it leaves c5g

| seed | with memory | without |
|---|---|---|
| 1 | 30.6 m out, 79 m flown | 34.1 m out, 115 m flown |
| 2 | 36.0 m out, 91 m flown | 22.7 m out, 113 m flown |
| 3 | 24.0 m out, 13 m flown | 24.7 m out, 55 m flown |

Mixed — better on seed 1, worse on seed 2. That is the honest outcome and it is
the point: the objective was to make the C4→C5 memory contrast *measurable* for
the real model, not to make c5g win. It is now measurable. 228 tests pass.

## Videos: judging a run by eye

`uavlab video [ARCH...] --seed N` renders one episode per architecture to mp4
(`analysis/replay_video.py`). Two panels: a plan view with obstacles, target,
distractors and the path so far, and the camera frame the policy actually saw.

Both panels are needed. The plan view shows whether the vehicle went anywhere
sensible; the camera panel separates "flew past a target that was never in
frame" (a perception result) from "flew past a target filling the frame" (a
policy result), which the plan view alone cannot distinguish.

Two deliberate choices. The scale is fixed for the whole episode rather than
fitted per frame — a rescaling view makes a straight line look curved and a
stall look like progress. And the verdict is withheld until the last few frames,
so a run can be judged on what it did rather than read in the light of its label.

Not importable from anything that scores a run. This module is for looking at.

Seed 3, all 22 configurations:

| | outcome |
|---|---|
| C0, C7–C14 | success, stopped 0.9–1.6 m from the target |
| C1 | timeout, 30 m out after a 267 m path |
| C2–C6 | timeout, 33 m out after ~366 m |
| C2G–C6G | fail; C3G collides, C4G/C5G stall at 13 m of path |
| C7T | out of bounds, 68 m from goal |
| C8T | timeout, 52 m out |

Worth noting from the table: C2–C6 are identical on this seed, as are C4G/C5G.
That is not the inert-component bug — those separate on other seeds — but it is a
reminder that a single seed cannot distinguish architectures, which is why the
scoring paths are paired across many.

## What the end maps showed: C1-C6 orbit and never acquire the target

Rendering every architecture's final plan view side by side made a pattern
visible that no summary metric had surfaced: **C1-C6 fly a large closed loop and
never approach the target**, while C0 and C7-C14 go more or less straight to it.

Measured on seed 3, same scene for both:

| | belief queries | target detected |
|---|---|---|
| c2 | 104 | **0** |
| c7 | 132 | 70 (53%) |

c2 never sees the target at all. Its verifier, monitor and memory therefore have
nothing to act on, which is the same root cause as the identical C2-C6 numbers
seen earlier — not a wiring fault, an acquisition fault.

### Why

Neither policy detects the target at t=0, so `grid_nav`'s claim that "the target
is within sensor range from the start" is true of range and false of field of
view. The two families then diverge in how they look for it:

* **C7** yaws continuously while translating — 21 deg/s in the first second —
  sweeping the 90 deg FOV across the horizon, and acquires the target early.
* **C1-C6** fly waypoint to waypoint with the nose pointed along travel. The
  exploration spiral is anchored at launch with the heading advancing on a
  clock, so the vehicle circles at roughly constant radius with the camera
  pointing tangentially — past the target rather than at it.

A 35 m target inside a 45 m sensor range is never acquired in 90 seconds. That
is a search-pattern defect, not a semantics defect, and it currently sets the
ceiling for the entire waypoint and skill family.

### Also fixed here

Every architecture now renders a camera panel. The panel was blank for the
non-vision configurations only because `grid_nav` does not pay to render frames
no policy reads — the vehicle always had a camera. Verified on c0/c4/c9/c13 that
turning rendering on leaves the trajectory bit-identical, so the video shows the
same episode that was scored. `--no-render` restores the old behaviour.

The legend moved out of the plan panel into the header, where it was covering
the target whenever the target sat in the bottom-left, and the view padding grew
from 1.15x to 1.35x so a target at the edge of the travelled area is not clipped.

## Ported drone_control's sweep. It did not fix acquisition, and the measurement says why

`plugins/reasoning/coverage.py` is a boustrophedon sweep ported from
`drone_control/src/agent/boustrophedon.py`, available as
`search_pattern: sweep`. The argument for it was already settled there by
measurement: frontier and spiral searches exist for *unknown* extent, and when
the extent is known — a stated geofence — coverage planning applies and is
provably complete where frontier is complete only in unbounded time.

Lane pitch is derived rather than chosen, and the derivation differs from the
original. drone_control treats the sensor as a disc, giving a swath of
2·R·sin(fov/2) either side of track. Here the camera is body-fixed and looks
*along* the lane, so a pass covers a forward wedge; the pitch is the wedge width
at half range, which is the conservative reading of the same geometry.

### It changed nothing that matters

| c2, grid_nav seed 3 | target acquired | final distance | path |
|---|---|---|---|
| spiral | 0 / 104 | 33.2 m | 368 m |
| sweep, 3 lanes @ 25.5 m | 0 / 104 | 36.4 m | 312 m |
| sweep, 8 lanes @ 11.1 m | 0 / 104 | 36.4 m | 307 m |
| sweep, 18 lanes @ 4.8 m | 0 / 104 | 35.4 m | 306 m |

`spiral` therefore stays the default. Flipping it to an unproven pattern would
have quietly changed every number measured so far for nothing.

### The actual blocker is occlusion, not coverage

Instrumenting the detection gate directly — range, field of view, and line of
sight, separately:

| | in range | in FOV | of those, occluded |
|---|---|---|---|
| c2 | 100% | 43% | **100%** |
| c7 | 100% | 61% | 13% |

The target is *always* within c2's sensor range and often within its field of
view. It is blocked by an obstacle every single time. c7 succeeds because it
flies toward the target and so reaches viewpoints with clear line of sight;
c2 searches from positions that never have any.

No lane pattern fixes line of sight, which is why every spacing gives the same
answer. drone_control had already framed this correctly from the other side:
the objective is **observed**, not **flown over**, which turns the problem from
coverage into the Watchman Route / TSP-with-Neighborhoods family — choose
viewpoints whose *visibility* covers the region, then tour them. That was
ranked there as option 4, "the principled optimum; needs a visibility
computation per candidate viewpoint".

That is the next thing to build, and this time the measurement above says
plainly what it has to achieve: a viewpoint set with unoccluded sight lines,
not more kilometres flown.

### Correction

I previously wrote that C1–C6's failure was a search-pattern defect and that the
camera pointed "past the target rather than at it". The field-of-view half of
that is real — 43% versus 61% — but it is not what decides the outcome.
Occlusion is, and I had not measured it before naming a cause.

## Altitude was the occlusion mechanism — and seed 3 was not representative

You were right about the mechanism. Obstacles on `grid_nav` top out at 11.1 m,
the mission permits 25 m, and the vehicle searched at **3.0 m** — below every
obstacle in the scene. It was threading between towers with the target at
z=2.9 m, so every sight line crossed one.

Adding `search_altitude_m` and flying the sweep above the obstacles, seed 3:

| | target acquired | final distance |
|---|---|---|
| sweep at 3 m (cruise) | 0 / 104 | 33.2 m |
| sweep at 14 m | 6 / 47 | 11.1 m |
| sweep at 20 m | 8 / 23 | 12.7 m |

Acquisition goes from never to a third of queries. The occlusion diagnosis and
the altitude explanation are both confirmed.

### But the conclusion I drew from it was wrong

Scored over seeds 1–8 rather than the one seed the video happened to use:

| | success | distance | collisions |
|---|---|---|---|
| c2 spiral at cruise (baseline) | **0.62** | 12.6 m | 0.00 |
| c2 sweep at 18 m | 0.00 | 30.5 m | 0.38 |
| c3 sweep at 18 m | 0.00 | 30.6 m | 0.38 |

**The baseline was never broken.** c2 succeeds on 5 of 8 seeds. Seed 3 is simply
a hard seed, and I generalised "C1–C6 orbit and never acquire the target" from
the single episode I had rendered as a video. That claim was false as stated;
it is true of seed 3 and not of the regime.

High-altitude search is also worse overall, not better: acquiring the target
from 18 m means descending onto it through the obstacle field, and c2 has no
shield, so 3 of 8 seeds end in a collision.

### What actually stands

* `search_altitude_m` and `search_pattern: sweep` exist and are measured. Both
  stay non-default because neither has earned it.
* Altitude is a genuine architectural lever — sight lines traded against
  approach time — and it now has a knob and a number attached.
* The lesson is procedural: a video is one seed. It is excellent for seeing
  *how* a run fails and worthless for deciding *how often*. I used it for the
  second and should not have.

## Seven families as structure, not prose

The design space is now data. `ArchitectureConfig` carries `family` and
`ablation_of`, every shipped config declares both, and `validate_family_set`
enforces the rule: **seven families, exactly one base each, every other member
naming what it modifies.**

```
classical_baseline       BASE c0
llm_tool_planner         BASE c1
vlm_semantic_waypointer  BASE c2   ablations: c2g
hybrid_stack             BASE c3   ablations: c3g c4 c4g c5 c5g
selective_recovery       BASE c6   ablations: c6g
direct_vla               BASE c8   ablations: c7 c7t c8t c9
fast_slow_hierarchy      BASE c12  ablations: c10 c11 c13 c14
```

Two base choices worth stating. **C8, not C7, is the direct-VLA base**: shipping
a learned policy with no safety shield is the ablation, not the default, so C7
is "remove the shield". **C12, not C10, is the hierarchy base**: a concurrent
reasoner over chunked actions is the shape CognitiveDrone and LiteVLA-H actually
describe, and C10 is "make it blocking and single-step".

`uavlab families` prints the structure and exits non-zero if it is violated.

### What the rule caught immediately

`ablation_of` inherits through `_base_`, and C8 inherits from C7. Declaring C7
an ablation of C8 therefore made C8 an ablation of *itself*, and the same for
C12 through the C10→C11→C12 chain. The bases now set `ablation_of: null`
explicitly, with a comment saying why, because a future reader would otherwise
delete it as redundant.

### Where the field is required

`family` is optional on the model and mandatory on the shipped set. Unit tests
build throwaway configs to exercise the router and scheduler; those are not
points in the design space and forcing them to name a family would be
bookkeeping with no reader. The requirement is enforced where the claim needs to
hold — over `configs/` — by `validate_family_set` and a smoke test.

`test_every_ablation_differs_from_its_base` also fails an ablation that changes
nothing, since that is a duplicate rather than an experiment. 230 tests pass.

## Baseline: the seven family bases over 20 seeds

`grid_nav`, seeds 1-20, scripted policies only. Per-episode records in
`reports/baseline_7families.json`, table in `reports/baseline_7families.md`.

| base | family | success | 95% CI | collisions | median distance when it fails | failure modes |
|---|---|---|---|---|---|---|
| c0 | classical_baseline | **0.80** | 0.60 - 0.95 | 0.15 | 21.5 m | collision 3, timeout 1 |
| c1 | llm_tool_planner | **0.45** | 0.25 - 0.65 | 0.00 | 30.2 m | timeout 11 |
| c2 | vlm_semantic_waypointer | **0.70** | 0.50 - 0.90 | 0.05 | 32.1 m | timeout 5, collision 1 |
| c3 | hybrid_stack | **0.60** | 0.40 - 0.80 | 0.05 | 29.7 m | timeout 7, collision 1 |
| c6 | selective_recovery | **0.60** | 0.40 - 0.80 | 0.05 | 29.7 m | timeout 7, collision 1 |
| c8 | direct_vla | **0.55** | 0.35 - 0.75 | 0.00 | 29.3 m | timeout 9 |
| c12 | fast_slow_hierarchy | **0.55** | 0.35 - 0.75 | 0.00 | 29.8 m | timeout 9 |

### What this does and does not say

**Nothing separates.** Every interval except c0-versus-c1 overlaps every other.
Twenty seeds cannot rank seven architectures whose true rates sit between 0.45
and 0.70, and no ablation should be read against a base until the base has more
seeds behind it. This table is a floor check, not a result.

**The ceiling is 0.80, not 1.00.** C0 reads ground truth and still collides on 3
of 20. Some of what every other architecture loses is inherited from the flight
stack rather than from its semantics, and that share is now quantified.

**Every failure is an acquisition failure.** Not one failed episode across all
140 ended within 5 m of the goal — the closest was 9.7 m, and the medians sit
near 30 m. Nothing arrives and forgets to stop. Whatever is wrong is upstream of
stopping, in finding the target at all.

I had read the opposite from an earlier column: c8's median final distance over
*all* episodes was 1.7 m, which looked like arrive-and-hover. That median mixed
successes with failures. The table now reports distance among failures only,
which is the number that carries information.

### C3 and C6 are the same architecture in practice

They produce **identical results on 18 of 20 seeds**. C6 is C3 plus a geometric
progress watcher and an event-triggered recovery reasoner, and on these seeds
that machinery almost never changes the outcome. Either the trigger rarely fires
or its detour is what the planner would have done anyway — worth separating, but
as it stands the `selective_recovery` family has no measured behaviour of its
own on `grid_nav`.

### Not changed

Nothing in the runtime, the configs or the defaults. This entry is measurement.

## The search leg was three seconds when it needed nine

Debugging from the end-map grid rather than the metrics found the largest defect
in the whole testbed. Seven bases against four seeds
(`reports/videos/base_grid.png`) showed C1–C6 tracing a *closed loop* rather
than an outward spiral, on every seed, whatever the target's position.

Instrumenting the spiral against its own commanded target, c2 on seed 3:

```
   t   commanded radius   achieved radius
 0.0                8.0               0.0
20.9               34.4              18.5
41.8               54.0              20.2
62.7               54.0              18.4
83.5               54.0              20.2
```

The search commanded points up to **54 m** from launch while the vehicle never
exceeded **21.5 m** and oscillated between 6 and 21 m for the whole episode.

### The arithmetic

`explore_turn_rad` is 50 deg and `explore_dwell_s` was a fixed 3.0 s. Consecutive
search points are a chord apart, and at the geofence radius that chord is 45.6 m
— **9.1 s of flight at the mission's 5 m/s.** Given 3 s the vehicle covered a
third of it, the heading moved on, and the next leg pulled it back. It was not
searching, it was chasing a point that outran it.

`explore_dwell_s` now defaults to 0, meaning *derive it*: chord length over
permitted speed, both taken from the mission's own constraints. It stays purely
time-based, so the fairness property holds — search coverage still cannot become
a function of decision rate — and it is identical across architectures because
it depends on nothing an architecture chooses.

### Effect, on 40 seeds never looked at during the diagnosis (101–140)

| base | family | before (seeds 1–20) | after (seeds 101–140) |
|---|---|---|---|
| c0 | classical_baseline | 0.80 | 0.88 |
| c1 | llm_tool_planner | 0.45 | 0.70 |
| c2 | vlm_semantic_waypointer | 0.70 | 0.95 |
| c3 | hybrid_stack | 0.60 | 0.97 |
| c6 | selective_recovery | 0.60 | 0.95 |
| c8 | direct_vla | 0.55 | 0.93 |
| c12 | fast_slow_hierarchy | 0.55 | 0.62 |

C0 is the control: it reads ground truth and never explores, so the fix must not
move it, and on the same seeds it does not.

### What this changes about earlier entries

Almost every earlier conclusion about C1–C6 was measured on a broken search and
should be re-read. Specifically:

* "C1–C6 orbit and never acquire the target" — the mechanism is now named. It
  was not the pattern, the field of view, or occlusion. It was a leg too short
  to fly.
* The occlusion measurement (target in range 100%, blocked 100%) was real but
  downstream: the vehicle was pinned near launch behind the obstacle cluster
  because it could not travel, not because coverage was wrong.
* The boustrophedon port failed for the same reason and would now be worth
  re-testing, since its lane ends are 42 m away and were equally unreachable.
* `search_altitude_m` was measured against a search that could not travel.

### Two things the new baseline says

**C0 is no longer a ceiling.** At 0.88 it sits below C2, C3 and C6, and its
failures are collisions rather than timeouts. It bounds the *semantics*, not the
flight stack, and calling it a control ceiling now overstates it.

**C12 is the outlier at 0.62**, with 15 timeouts, against C8's 0.93 — the
hierarchy is markedly worse than the plain shielded VLA it is built on. That is
now the largest unexplained gap in the set.

230 tests pass. `reports/baseline_7families.{json,md}` regenerated on seeds
101–140.

## A decision register, and where things belong

`docs/RESEARCH_LOG.md` is new: every design decision with a stable identifier,
its rationale, the evidence behind it, what was rejected, and a status. Thirty
entries covering experiment structure, runtime fairness, search, perception,
memory, the learned policy and tooling. `docs/README.md` states which of the four
documents a given thing belongs in.

The split that matters: **CHANGES.md is chronological, RESEARCH_LOG.md is
organised.** This file answers "what happened and when"; the register answers
"why is it like this, and what would change my mind". A reader coming to the
results needs the second and cannot navigate the first.

Three conventions worth keeping:

* `Evidence: none` is a legitimate value. It marks a decision `provisional` and
  tells a later reader exactly what to go and measure. D-03 and D-17 carry it.
* Corrections never delete. The status becomes `superseded by D-nn`, and
  withdrawn claims go in a table at the bottom — six of them so far — because a
  reader who meets an old claim elsewhere needs to find out it was withdrawn.
* Open questions are ranked, with a first step each. C12 at 0.62 against C8's
  0.93 is currently first.

## Frame-to-pose binding, pinned

Raised as a concern: the vehicle flies while a slow model thinks, so are the
image and the pose out of sync? Checked rather than assumed — they are not. The
frame and the pose come from the same observation packet, and the unprojection
produces a point in **world** coordinates from the capture pose, so a waypoint
stays valid however far the vehicle has moved by the time it executes.

`test_the_waypoint_is_unprojected_from_the_pose_that_took_the_frame` pins it,
because the failure would be silent: the same pixel read against the current pose
still yields a plausible waypoint, just the wrong one, with the error growing
with model latency and looking like a model-quality problem.

What *is* wrong in that path is depth: the waypoint is placed at a fixed hop
distance along the ray because a monocular pixel carries no range. Recorded as
D-17, status `open`, unquantified — and it sits under every waypoint-family
result.

231 tests pass.

## Timestamps on the decision register

Every entry in `docs/RESEARCH_LOG.md` now carries a **When** field, plus a
chronological index at the bottom so the register reads as a diary as well as a
reference.

The times are taken from git commit dates, not written by hand. That makes them
the moment a decision entered the repository rather than the moment it was
thought of — usually minutes apart — and it means they cannot quietly drift away
from the record they describe.

Fifteen of the thirty entries predate `git init` on 2026-08-18 15:03. They say
"on or before" and point at the initial commit rather than carrying an invented
time. A fabricated timestamp in a research log is worse than an absent one: it
looks like evidence.

## Chasing the C12 gap: localised, not solved

The hierarchy chain is an ablation chain, so scoring it isolates the step that
costs the performance. Seeds 101–140:

| | | success |
|---|---|---|
| c8 | base: shielded VLA | 0.93 |
| c10 | + blocking reasoner, semantic state | 0.82 |
| **c11** | **+ action chunks** | **0.57** |
| c12 | reasoner made async | 0.62 |

The reasoner costs 0.11. The c10→c11 step costs 0.25 — more than twice as much —
and that is where the gap lives.

### Why the number is not yet trustworthy

C10 runs `mock_vla`; C11 runs `chunk_vla`. Those are two implementations, not one
policy under two horizons, so C11 changes the action horizon *and* the policy at
once. Splitting it as far as the code allows: `chunk_vla` at its shortest horizon
scores 0.68 against `mock_vla`'s 0.82, so roughly 0.15 is the swap and 0.11 the
horizon. Recorded as **D-31**, open. It is the same one-change-at-a-time
principle the family structure exists to enforce, violated inside a family.

### Rejected on measurement

* **The memory swap.** C10 also changed `short_context` to
  `compact_semantic_state`. Putting C8's memory back into C11: 0.57, unchanged.
* **The in-chunk velocity decay.** Removing it: 0.62.
* **Cruise speed.** 3.0 → 4.0 m/s: 0.62.
* **Chunk length.** Every value from 1 to 8 stays between 0.53 and 0.68.
* **Stopping.** Not the problem. Across all four configurations, **zero**
  episodes arrived at the goal and failed to declare done. C11 simply reaches
  the goal on 23 of 40 where C8 reaches it on 37.

### A fix that made it far worse

`chunk_vla` emits `yaw_rate_rps=0.0` for every action while `mock_vla` computes
one from the same belief, which looks like a plain oversight. Giving it the
identical yaw law took C11 from 0.57 to **0.00** and C12 from 0.62 to 0.00.
Reverted.

A yaw rate is a *rate*: `mock_vla` applies it for one 0.2 s step and re-decides at
10 Hz, whereas a chunk commits it open-loop for 0.8 s, so the vehicle rotates
straight past its target heading with nothing to stop it. A correct version has
to integrate heading error across the chunk rather than hold a rate. **D-32**.

Also measured, and against the obvious story: on seed 103 C11 turns **0 degrees**
all episode and still has the target in view 100% of ticks. Whatever it loses, it
is not primarily perception.

The mechanism is still unidentified. Three decisions recorded (D-31, D-32, D-33)
so the rejected explanations are not re-tried. No code changed.

## Post-D-14 learned and real-model gates

The two central TODO items were resumed on the local deterministic simulator.
The rerun first found two harness defects: training tools still looked up the
pre-D-19 frame URI and therefore recorded zero samples, and experiment seeds
were multiplied by 1000 while manifests recorded the unmapped values. Both are
fixed and pinned by tests (D-37, D-38).

The learned-policy rerun completed on training seeds 1000–1249: 22,025 samples,
20 GPU epochs, 1.439 m/s validation velocity error. It did not navigate on held-
out seeds 1–40: C7T and C8T both 0/40 success; C8T reached the goal once and its
shield removed all collisions. D-14 was not the binding constraint (D-39).

The corrected Gemma screen on seeds 1–3 scored C2 2/3, C2G 0/3 and C3G 0/3.
A standalone C2G seed-2 run reached the goal radius but never stopped. Clean-
frame and in-mission probes rejected target-scale prompting, Qwen3-VL 2B,
Moondream and SmolVLM as drop-in fixes. The open problem is terminal range, not
whether Gemma sees the target (D-40).

## Taxonomy corrected to the paper's top-level comparison

The design space is now represented as one classical baseline plus five
autonomy families. The former seventh family, `fast_slow_hierarchy`, is an
explicit subfamily of `hybrid_stack`; C3 is the primary hybrid representative
and C12 remains the fast/slow subgroup reference. The validator, CLI, smoke
test, family documentation and C10–C14 configs now encode that nesting.

Added `core_families_local.yaml` as the frozen first local-simulator screen:
C0, C1, C2, C3, C6 and C8 on identical seeds. Its comments state that scripted
slots validate wiring only and are not foundation-model results. A one-seed
end-to-end smoke completed all six cells; the output is diagnostic only (D-41).

## Real-VLM RGB-D terminal gate

Added a calibrated local depth-camera channel and synchronized it with the RGB
frame before slow inference. The VLM still supplies the semantic pixel; depth
is sampled only at that pixel. A world-point consistency check and a second
cropped VLM call are required before stop. The shared
`gemma3_4b_waypoint.yaml` fragment now prevents C2G–C6G from drifting apart.

Rejected three unsafe variants on measurement: triangulated steering, active
parallax steering, and depth-only stop. The last produced premature stops 24.77
m and 27.72 m from the goal. The semantic crop gate removed the false stops but
did not create capability: C2G, C3G and C6G remained 0/3 while scripted C2 was
2/3. The vision task now inherits the same 90 s horizon as the non-vision task;
C2G seed 2 reached the goal at 62.65 s but crossed it and never stopped. The
declared 20-seed screen was therefore not run (D-42).

## Why no drone dataset matches our action space (2026-09-04)

Short answer: there is no drone equivalent of Open X-Embodiment, and the reason
is physical rather than sociological. A 7-DoF arm's joint angles mean the same
thing on every 7-DoF arm, so RT-X could pool 60 manipulation datasets into one
action space. A quadrotor's `vx = 2.0 m/s` does not mean the same thing on two
airframes with different mass, thrust-to-weight and controller gains. So no
pooled aerial corpus exists, and every paper generates its own data in its own
simulator against its own dynamics. That *is* the consensus. We already followed
it without knowing it.

### Correction to D-56

D-56 called Exp2VLA's `+-1` action range a defect that would corrupt training if
mixed with our m/s data. The dead channels (`vy`, `pitch`, `roll` identically
zero) are a real defect and that part stands. The `+-1` range is not — per-channel
normalisation to the unit interval is the field's standard action representation,
used by OpenVLA and RT-X precisely so that datasets with incompatible physical
units can be pooled. I had it backwards: normalisation is the mechanism that
makes combination possible, not the thing that breaks it.

### What this implies for us

Our `[vx, vy, vz, yaw_rate]` in m/s is the unusual choice, not the datasets'.
The fix is to train on normalised actions and de-normalise per platform at
deployment:

    a_norm = clip(a_mps / constraints.max_speed_mps, -1, 1)

This makes UAV-Flow directly poolable with our own data: derive velocity from
its 5 Hz pose logs, divide by its own observed speed limit, and both corpora
land in the same representation. It also means the AirSim transfer we care about
becomes a rescaling problem rather than a retraining problem.

### Recommendation

Train on UAV-Flow (30k real trajectories) plus our 4,765 samples, both
normalised, with a per-dataset de-normalisation constant recorded in the
manifest. Do not chase a dataset that ships m/s -- none will, and none should.

### Superseded (2026-09-04)

The section above claims our `[vx, vy, vz, yaw_rate]` in m/s is the unusual
choice and that drone datasets cannot share an action space. Both are wrong; see
D-58 in docs/RESEARCH_LOG.md. `[vx, vy, vz, yaw_rate]` is the ArduPilot/MAVLink
velocity setpoint and is the field's convention, which CognitiveDrone adopts
explicitly for hardware consistency. The wider stored vectors in Exp2VLA and
CognitiveDrone are OpenVLA's 7-D manipulator action slot with the unused
channels zeroed - padding, not extra degrees of freedom.

Normalisation is still worth doing, but for the mundane reason that airframes
have different top speeds, not because the action spaces disagree.

## C5 retained benchmark is not a search task (2026-09-04)

Target is dead ahead at 35 m on all five retained seeds; the seed varies the
obstacle layout, not the bearing. Path budget is 54 m (0.6 m/s x 90 s) against a
35 m straight line, leaving 19 m of slack for all detours. Measured paths were
45-46 m, so the vehicle is speed-saturated for 86% of the episode.

Outcome tracks occluders on the direct ray: 1061 has one and succeeds, 1064 has
none and is the only seed that sees the target, 1060 and 1063 have two and 1062
has three and none of them ever acquire.

Consequence: the "go where you cannot yet see" framing (D-55, D-60) answers a
question these seeds do not ask. Full evidence in docs/RESEARCH_LOG.md D-62 and
D-64; the SPF step ablation is implemented, defaulted off, and should not be run
against this benchmark.

## C5 capability probes — the failure is the model (2026-09-04)

Four causes were tested and excluded, each with its own run:

- **Path budget.** Raising the horizon from 90 s to 240 s changed nothing:
  1/5 either way. Failures used 78-90 m of a 144 m budget (D-64).
- **Getting stuck at the fence.** All four failures freeze 55-56 m from home
  with 100% of verifier calls refused for the geofence; the one success has
  zero such refusals (D-65).
- **Not knowing the route.** Given `c0`'s winning path in words, C5 scores
  0/5 — worse than the 1/5 it gets knowing nothing (D-66).
- **The output contract.** Swapping the pixel for a five-word steering
  vocabulary also scores 0/5, and the model just repeats one word instead of
  one pixel: 99% `left` on seed 1062, 99% `right` on 1063, mean entropy 0.21
  of a possible 1.0, and `hard_left`/`hard_right` chosen zero times in 925
  decisions (D-67).

Classical reference `c0` solves all five seeds in 63-84 s. Where C5 does work
(seed 1061, no hint) it reaches the target in 85 s, 1.27x `c0`.

Two side findings. The direction contract's acceptance criterion was unsound —
it tested "not centre", which a model emitting one fixed word still passes. And
the monitor declared arrival at 32.9 m and 8.5 m from a 2 m goal radius, which
is the acquisition latch and unrelated to steering.

Full detail: reports/paper_implementation/C5_CAPABILITY_PROBES_20260904.md and
C5_LONG_HORIZON_RESULTS_20260904.md.


## 2026-09-12 - D-104 bounded capability-screen setup
- Added a sequential single-seed runner that refuses overwrite/retry and captures original model calls.
- Added a named existing-OnFly profile calibrated to the capability camera (-0.10 rad), generic monitor without task-color guard.
- C0 remains unchanged; C1 input-contract decision pending. No new flight result claimed yet.

- Screen run IDs use capability_screen_ to avoid the earlier D-103 C0 fixture integration run; detected before execution.

- Added opt-in C1 Gemma profile retaining its text-only inputs, skill protocol, 512-token output and inherited 8.5 s simulated latency. No visual grounding adapter added. This tests current compatibility, not visual reasoning; actual wall latency is separately recorded. Eight C0 flights completed: 6 successes, ordered_visit and follow_target fail by agent stop. C5 batch in progress.

- Added inference-free replay exporter with separate C0/C1/C5 dashboard pages and complete per-run metrics/provenance.

- Added headless Edge checks of real screen flights, task status, camera rendering and playback, with saved screenshots.

- Added a linked capability matrix and generated report with prominent privileged-input, C1 text-interface, C5 profile and unmatched-latency limitations.

- Visual review of C5 visible_target shows closest approach about 0.33 m followed by departure, without stop. Added timeline inspection evidence; task failure must not be equated with inability to reach the goal. No repair or extra flight.

## 2026-09-12 - D-104 first capability screen completed
- Ran all 24 cells once on seed 1061: C0 6/8, C1 0/8, C5 0/8, no runtime errors or collisions. C5 records 14 constraint violations across six runs.
- Preserved exact model input/output and all failures. Only shared local Gemma: 745 completed requests plus 15 boundary cancellations; no cloud or repeat trials.
- C1 retains text-only inputs; its coordinate task reaches the destination but rejects done without labeled evidence, followed by a stale stop. C5 approaches visible target to 0.335 m but fails to stop. Do not equate timeouts with planning inability.
- Exported linked matrix and all 24 flight replays. All replay checks pass; Edge verifies 72 snapshots and 24 playbacks with no errors. Added findings, call audit and selected original protocol evidence.
- No runtime policy change, extra flight, scheduled continuation or C1 visual integration. Next diagnostic steps documented in FINDINGS.md.

## 2026-09-13 - D-105 AerialClaw coordinate completion repair
- Both policy done validation and shared stop runtime now accept live odometry at the explicit public ENU coordinate for known_goal_nav only, within mission radius and speed <=0.75 m/s.
- The coordinate is read from the unambiguous public instruction, never scoring truth or a model-proposed goal. No action is authored by this parser; the LLM still selects goto and done.
- Legacy semantic tasks remain unchanged. Added near/far/speed, ambiguous-input and search-isolation regression checks. Validation/rerun pending.

- Coordinate validation: 24 unit tests pass, including original saved D-104 done response with no retry. Initial combined test command named a nonexistent test_skills.py; corrected immediately. Legacy UP038 lint warnings remain; new formatting issues corrected. One matched Gemma flight succeeds at 26.0 sim s (16.32 wall s), two completed calls, zero protocol rejections/collisions/constraint violations. Original failed run preserved.

- Added opt-in aerialclaw_visual_agent: LLM requests detect_object, tool captures the next fresh RGB-D observation, returns a measured object location, and the LLM independently selects goto/done. No image-to-motion loop, automatic waypoint dispatch, semantic-hit input or scoring truth. Positive evidence retains original timestamp; missing/invalid depth never fabricates range.
- New single-object profile declares red pillar from public mission, existing 8.5 s policy charge and explicit 1.2 s perception charge. Added tool events and matching capability vocabulary in an otherwise identical visible-target environment. Offline validation/flight pending.

- Visual-tool offline checks caught a pitch-sign error in RGB-D lifting before any inference flight; aligned the transform with the sensor Camera convention. Tool request/result events now appear as separate, source-aligned debugger entries, including the exact detection image.

- Registry-contract test required configuration validation at reset rather than construction; moved it without changing run behavior. Corrected the test-directory command from tests/contracts to tests/contract.

- Preflight verification: 403 unit/contract tests pass (one pre-existing dateutil deprecation warning); new visual-tool/coordinate files pass lint. No real visual-model call used for these checks. Starting exactly one visible-target tool flight.

- First visual flight timed out without translation: model saw the red pillar but selected (499,533), about five image pixels below its valid-depth silhouette. Seven completed model calls; original failed flight preserved. One saved-image bbox probe also missed the object and was not adopted.
- Added a separately named, opt-in 3%-image pixel refinement: only for invalid selected depth, finds a single connected range-consistent observed surface in the local window, moves the pixel to that surface, and unprojects its measured depth. Multiple surfaces, no depth, and distant objects remain rejected. No hidden geometry, color-coded simulator answers or new model call in refinement. Offline saved-frame validation pending before one changed-profile flight.

- Saved-frame check confirms reconstructed RGB exactly matches the failed tool input; strict point has no range, bounded refinement yields measured depth 11.940 m and ENU (11.859, 0.107, 1.596), without a model call. Preparing one separately named refined-profile flight after regression checks.

- Refined visible-target flight succeeds at 35.7 sim s (9.50 wall s), final 1.415 m, 3 text planning calls + 1 image detection, no collisions/violations/protocol rejections. One failed point variant and one failed bbox saved-frame probe remain preserved. Per the authorized progression, extend the same profile to one turn-search run with identical 60 s horizon and no tuning.

- First search flight times out with zero detection-tool calls: original passive-detector search strategy led to scan/coverage without inspection. Added a named visual_search_strategy profile replacing that advice with explicit model-requested inspection after viewpoint changes; no automatic detector invocation or navigation authoring. One final changed-profile search check planned; all failures retained.

- Implementation/process error: the search-strategy string replacement failed to match formatted code. Its focused test correctly failed, but the PowerShell command chain continued into commit/run. c1_visual_search_strategy_20260913_s1061 therefore repeated the old behavior (timeout, 4 completed calls) and is an INVALID configuration-change trial, not evidence about the intended repair. Preserved it in full. Corrected the insertion with an asserted match and added explicit exit-code gating to subsequent verification commands. No additional flight will run this turn; corrected search advice is offline-validated only.

## 2026-09-13 - D-105 results and handoff
- Five new local flights preserved, including one invalid setup trial: coordinate and refined visible target pass; strict visual and search fail; corrected search advice has offline validation only. 21 completed flight calls +5 cancelled boundary calls, plus one failed saved-frame bbox probe; only Gemma.
- Saved all per-flight manifests/results, compressed events and exact calls/images. Published before/after debugger with explicit invalid-trial note and perception-tool evidence.
- Final 406 unit/contract tests pass; seven trajectories replay-match, 21 browser timeline checks and seven playback checks pass. New tool and coordinate files pass lint; legacy UP038 warnings were not mass-edited.
- No further flights or scheduled work. Next bounded step is corrected-strategy search validation. See REPORT.md and TODO.md; no general visual-planning success claimed.

## 2026-09-13 — D-106: freeze 24-cell comparison before inference

User authorized one corrected search validation followed by comparison of C0/C1/C5.
The search flight counts once in the 24-cell matrix. Resolved configurations and
source hashes freeze before launch; no tuning/retries. Five C1 text-only cells
are explicitly integration-limited. See reports/frozen_capability_20260913/PLAN.md.

## 2026-09-13 — D-106: corrected search inspected, integration conflict retained

First matrix cell times out. Camera shows target during scan at 10 s; exact sole
perception image at 21.95 s has no target. Further scan requested by the model is
rejected by inherited full-turn coverage gate. 5 completed calls, 1 cancellation;
1,200 replay poses match. No fix mid-comparison; see SEARCH_INSPECTED.md.

## 2026-09-13 — D-106: frozen comparison dashboard and arrival evidence

Added separate replay/report and browser-check scripts; preserved old dashboards.
Initial tooling lint reported formatting and a loop-callback capture warning;
formatted scripts and bound callback state, then checks pass (long HTML strings
excluded from line-length rule). No flight source/config changed. Resolved visual
scenes match other families except environment ID and allowed skill vocabulary.

OnFly visible-target flight reaches 0.335 m but no stop: last identified target
sample is 2.092 m (above 2 m threshold); next image lacks target and monitor reports
LOST. Camera/map and exact monitor evidence are preserved in ONFLY_ARRIVAL.md.
This observed arrival/stop boundary is not yet a validated causal repair.

## 2026-09-13 — D-106: complete and preserve frozen 24-flight comparison

All 24 cells finished with no runtime error, tuning or retries. C0 6/8 privileged;
C1 2/8 raw (two passes among three supported contracts, five missing visual/task
integration); C5 0/8, with goal arrival and partial branch/order/tracking progress.
No policy/config change during the batch. Added failure map and per-case next checks;
updated AGENTS/TODO/research log to supersede offline-only corrected search status.
Retained exact calls/images/source snapshots, compressed events, manifests/results.

743 completed Gemma calls (31 C1/712 C5), 16 cancelled at boundary; no cloud or keys.
Zero collisions; 14 C5 constraint violations across six cells. All 19,414 poses and
24 resolved manifests match; no missing source frames. 72 browser seeks/24 playbacks
plus 24 closest-approach inspections pass. Confirmed exact C1 tool image/source links.
Dashboard matrix labels every failure explicitly. No further run is active/scheduled.

## 2026-09-13 — D-106: retain exact evidence bytes in git

Git warned about Windows newline conversion in captured source snapshots. Added a
scoped -text attribute for this evidence directory and renormalized its index so
future checkouts retain original bytes. All 82 snapshot filenames match SHA-256.
No simulation, source behavior or configuration changed.

## 2026-09-13 — D-107: isolate inspected-view search contract

Added opt-in observed coverage and short scan contract. Legacy angular coverage
remains the default. Requested detections alone update conservative angular bins;
rotation alone cannot exhaust search or reject a retry. Model selects direction,
scan and detection; no automatic perception or semantic route planner.

## 2026-09-13 — D-107: bounded confirmed-target arrival variant

Saved-control/response probe reproduces the current-frame arrival gap without new
inference. Opt-in monitor retains a world target confirmed in two distinct RGB-D
observations for at most 3 seconds, with original timestamps; arrival uses odometry
and the unchanged 2 m bound. A live recheck after inference rejects stale/departed
stops. No navigation or RGB change; no ground truth. Restricted to stationary
single-object task families. Visual confirmation is separated from physical arrival.

D-107 search flight outcome: timeout, no movement; six requested detections of the
same empty view, zero scan proposals/rejections. 12 completed calls +1 boundary
cancellation. Old gate defect is offline-repaired; search success is not established.
No adaptive rerun. Saved-arrival probe initially had a test-helper import error;
replaced it with direct runtime services, no model calls occurred in failed launches.

Saved-input causal check: exact RGB/controls replayed through both monitors. Legacy
never stops; bounded-confirmed target stops at source 11.95 s on the same answers.
No new inference. Negative tests cover expiry, departure, one/repeated frame,
world-point jumps and invalid range. One fixture used integer depth and rejected
infinity assignment; changed fixture to floating depth before flight validation.

## 2026-09-13 — D-107: requested visual tools for ordered visits

New opt-in two-object policy preserves red/blue identities and original source
positions. Model selects detection queries, motion and order; shared SUPER executes.
Public instruction supplies the ordered contract. Onboard odometry observes first
visit dwell at control frequency; missing sample intervals reset dwell. Policy and
runtime require first dwell then final arrival before stop. Stationary locations
expire at 30 s. No simulator scoring state or scripted route is exposed.

C5 single flight still times out: candidate at 11.95 s is recognized, but response
arrives at 13.2 s and 3 s evidence TTL has expired. Live guard correctly refuses it.
Saved-input probe omitted availability-time validation and was insufficient as an
end-to-end predictor. Preserve this failure; no window tuning or extra flight.

D-107 preflight: all 417 unit/contract tests pass (one existing dateutil warning).
New ordered-contract tests reject blue-first stopping, missing dwell, observation
gaps, expired locations and forged/unstated sequence; two queries preserve identity.
Formatting/import lint corrections applied to test/tool code before launch.

## 2026-09-13 — D-107: correct final-audit implementation mistakes

Exact ordered prompt still contained inherited passive-detector/full-turn advice;
removed that conflicting strategy and added regression assertions. Initial ordered
flight is evidence of an integration-confounded prompt, not a clean tool-choice test.
Arrival candidate was valid at capture but its 3 s TTL expired at 3.25 s availability;
new named profile uses 4 s (two monitor periods), with unchanged 2 m radius and live
check. Availability replay tests both windows, including expiry/departure negatives.
Explicitly amended the assistant-imposed cap to five flights, communicated before
launch: one final flight per correction, no other adaptive retries. Preserved failures.

## 2026-09-13 — D-107: final targeted outcomes and complete evidence

Final C5 arrival-window flight passes at 13.2 s, 0.370503 m, no collisions or violations.
Final ordered requested-perception flight times out but detects/reaches red and completes
first dwell at onboard 24.3 s; later calls carry first-complete=true but repeat red goto.
No blue query. Search remains unsuccessful. Five new flights total; initial failed
3 s arrival and conflicting ordered prompt are preserved, not silently replaced.

Exported eight-run before/after dashboard with exact requests/images/source snapshots.
Fixed browser diagnostic selector to use decision.t, asserted the exact monitor
source time and live-recheck rejection. All replay trajectories and browser checks pass.
Added honest fidelity/handoff/TODO notes, including remaining per-label prompt-context
ambiguity; no global planning-capability conclusion. No further inference scheduled.

Final verification: 418 unit/contract tests pass (one third-party deprecation warning).
Eight exact trajectory replays / 8,665 poses; 24 browser seeks and eight playbacks pass.
Final success and ordered red-only views directly inspected. Captured source SHA-256
filenames verified. Five new flights used 131 completed local Gemma calls and five
boundary cancellations; no cloud. Focused Ruff and diff whitespace checks pass.
Evidence: reports/targeted_contracts_20260913/VERIFICATION.json.

## 2026-09-13 — D-108: approach-side hover task

User authorized autonomous run/debug/fix. Added named task with 2 s visible slow hover,
front-side range/alignment and latched swept no-contact scoring. D-107 unchanged.
Added wrong-side, view-loss, dwell, motion and contact negative controls.

D-108 baseline: false terminal stop at 9.2 s, final 0.743 m, hover=0. Exact replay
185 poses matches; dashboard camera at end has no pillar and drone is still moving.
Old 2 m completion gate ignores new hover semantics. Named adaptation uses existing
1 m endpoint standoff and new monitor checks of approach side/range, low speed,
continuous odometry dwell, and projected VLM target with live depth visibility.
Model still selects pixels; no target truth or automatic route/search is supplied.

Added live hover duration, speed, view and contact fields to the debugger.
Preflight caught an incorrect Camera import and missing constructor dependencies in
the new unit fixture; corrected before inference. 66 focused tests passed before trial 2.

Trial 2 reached stable hover: evaluator 48.9 s dwell, no contact, timeout because
monitor lost identity in close-up (solid red/cropped image). Exact RGB-matched audit
also found policy reprojecting old ground points at 7–8 s: missing depth defaulted to
7 m, placing endpoints past the pillar. Next named condition uses existing grounded
waypoint contract instead of old pixel-history steering, plus explicit earlier/current
images in hover grounding. Current image must still support identity; live RGB-D,
age, range, side and dwell checks unchanged. General contract test now provides this
specialized monitor's required public mission instead of an unrelated generic mission.

Before trial 3: 101 focused/contract checks passed; prior generic contract failure
was a mismatched fixture mission, not a flight crash. No model calls from failed
preflight commands. Added explicit earlier/current ordering check for temporal input.

Trial 3: stable 1.114 m stop at 11.2 s but evaluator rejects it: vehicle z=2.597
instead of initial z=3, exceeding 0.35 m line tolerance. The inferred target's
arbitrary body pixel shifted monitor geometry down too. New opt-in flight-level
adapter preserves initial onboard altitude while respecting camera-forward depth
ceiling; hover monitor measures vertical deviation from initial odometry, not VLM
pixel height. No evaluator threshold changed. Added exact failure negative control.

D-108 final flight passes at 11.2 s / 1.0027 m / 2.1 s hover, no contact/collision.
One speed violation is solely 2.0000000000000004 > 2.0; saved counter retained with
exact audit. Four complete development flights, 137 Gemma calls + 4 cancellations.
433 offline tests pass; all 1,835 poses match; 12 seeks/four playbacks and direct
visual inspection pass. Full report, exact requests/images/sources and failed trials
preserved. No additional run active; broader search/ordered planning remains open.

## 2026-09-14 — D-109: two unchanged hover repetitions and departure diagnosis

Exactly two authorized flights: 1060 PASS (11.2 s, 1.003 m, 2.1 s hover), 1062 timeout
(60 s, 32.94 m final). 231 source/config hashes unchanged; no runtime fixes or third
flight. Repeat failure invalidates any broad reliability inference from D-108.
Correction: failure did physically hover >8 s; final zero hover counter masked prior
successful dwell. Monitor missed initial 2 s gate (1.95 reported); later arbitrary
body-pixel reference moved cross-track to 0.397 m while actual position stayed aligned.
Controller yaw reacts to tiny residual translation errors, rotates target out of view.
Exact obs380 at18.95 s contains only sky/ground; exploration action executes at20 s
and starts departure. Saved controls/images prove the sequence; scheduler race not proven.
106 new completed Gemma calls +2 boundary cancellations; no cloud. Three replays/1,650
poses, nine seeks/three playbacks, five departure screenshots and exact policy input
checked. Every reported speed violation is float roundoff. Export originally blocked
by auto-review capacity; completed after user approval. Reports and evidence retained.


## 2026-09-14 - D-110 hover reference/heading repair (validation pending)

Added opt-in residual-heading hold, initial-frame approach line, two-valid-endpoint
dwell counting and current-state monitor completion. Preserved old profiles and task
thresholds. Saved failure checks and two bounded local Gemma flights are next.

Validation: 442 unit/contract tests pass; saved failure replay matches 1,200 poses,
geometry and yaw component counterchecks pass (SAVED_PROBE.json). No new model calls
yet. New profile preserves old defaults; named development adaptation only.

D-110 launch preflight rejected a 17-level config chain before inference. New profile
now inherits the context profile directly and explicitly retains initial altitude;
runtime/scoring unchanged. Freeze updated before the first actual flight.


### D-110 flight and dashboard verification complete

Two new unchanged flights pass: c5_hover_stable_20260914_s1062 at15.2 s/1.00198 m,
6.1 s hover; seed1060 at13.2 s/1.00179 m,4.1 s hover. No collisions/contact;
one raw speed roundoff violation each (4.44e-16 m/s).43 completed Gemma calls+2
cancellations,zero cloud.263 frozen hashes unchanged;1,770 exact replay poses;
15 exact source monitor images;9 browser seeks/3 playbacks,terminal images checked.
REPORT.md records conservative completion and same-scene limits. New comparison at
http://127.0.0.1:8766/hover_stable.html; first browser404 traced to Valley owning8765,
left untouched. Evidence/scripts/docs preserved; no third new flight scheduled.


## 2026-09-14 - D-111 navigation diagnostic profile

Prepared navigation-compatible corrected C5 for original clutter seed1061. Preserved
D-98 environment,SUPER/verifier/scheduler/inference; excludes hover-only contract,
retains grounded points,1 m standoff,arrival memory and heading hold. Frozen before
one diagnostic flight. No runtime edits or inference yet. See D-111.

D-111 first flight: timeout90 s,closest22.583 m/final37.906 m,zero collisions,
328 raw violations pending audit.134 completed Gemma+1 cancelled. Exact source
images confirm gray/green objects labeled target despite red mission in prompt.
Two replays/3,600 poses and10 browser seeks/2 playbacks verified. Baseline retained
before saved-frame attribute-contract probe; no runtime fix or rerun yet.

D-111: three saved-frame local Gemma probes reject wrong target bindings using
existing VLM-reported color check. Alternative passage quality remains uncertain.
Enabled only policy.semantic_color_guard in named matched variant, frozen before
one rerun. No runtime code edits or geometry/safety/model changes.


D-111 complete: attribute rerun also timeout,closest33.343 m/final67.845 m; not
promoted.89 exploration outputs; label correction does not establish passage/search
quality. Two new flights and3 probes,271 completed local Gemma+2 cancellations.
No cloud/runtime edits/third flight.5,400 replay poses exact,178 new policy images
exact,15 seeks/3 playbacks. Raw328/465 speed violations only roundoff<=2.22e-16 m/s.
User RGB/BGR concern checked with actual client request construction offline:RGB PNG,
224x224,Base64,exact bytes preserved,known red remains(205,46,46). Images shown.
See clutter_stable_20260914 report and localhost8766/clutter_stable.html.


## 2026-09-14 - D-112 six-call saved-image probe prepared

Three exact saved RGB-D frames and expectations frozen: visible red through gap,
hidden target with openings,close wall. Paired baseline/explicit passage-check with
hold option; no flight runtime edits. Saved replay/image identity checks pass.
Six local calls planned, zero cloud; probe-only hold has no executable flight adapter.


D-112 completed:6 local saved-frame calls,all six points on gray faces. Visible
red correctly named but pixel(499,499) selects neighboring gray block. Candidate
changes one label but no useful point,never holds. Conversion preserves selected
ray<=3.18e-14 px. No runtime promotion/new flight. Three source RGBs/1,040 replay
poses verified; six-panel report/browser overlay+prompt checks pass. Results and
raw replies preserved; dashboard localhost8766/passage_choice.html. Next isolate
coordinate grounding with another output representation, not control tuning.


## 2026-09-14 - D-113 localization representation probe prepared

Frozen three sources,4x4 labeled grid and original-image bbox prompts,expected
cell/absence and tight-box criteria before6 local calls. Grid visually checked.
No runtime changes or flights; original RGB preserved separately from annotations.


D-113 complete:6 local calls. Grid gets B2 but falsely claims red targets in both
absent frames. Box correctly rejects absences but visible box misses (IoU0.05024,
center outside). Neither promoted; no flight/runtime changes. Original RGB hashes,
modified grid inputs,raw replies,scoring and screenshots saved. Scripts lint and
six-panel browser QA pass. Dashboard localhost8766/localization_formats.html.


## 2026-09-14 - D-114 local VLM comparison frozen
User requested all seven installed alternatives from the preceding model table. Prepared an isolated CPU-only Ollama probe: same D-113 three scenes, grid and bbox prompts, 192 output tokens, 8192 context, temperature/seed zero, at most 42 attempts. Reuses six saved Gemma answers. Preserves raw requests/replies, model digests, errors, CPU residency; no inference retries or flights. CPU execution protects shared GPU server; latency is not comparable to flight runtime. Scorer reproduces all six historical Gemma verdicts and positive IoU.

## 2026-09-14 - D-114 dashboard and offline verification
Added interactive local_vlm_comparison.html generation: eight model views, exact inputs,
optional reference/model overlays, raw prompts and both reply channels, separate positive
localization/negative rejection/runtime errors. Reports verify base64 identity, prompt/schema,
model digest, reply identity and zero VRAM residency. Offline checks reproduce six historical
Gemma scores, reject invalid/off-target boxes, exercise thinking-channel extraction and
48 browser panels. Qwen2B positive overlay visually inspected; no navigation claim.

## 2026-09-14 - D-114 all local alternatives complete
Finished42 attempts across seven frozen installed models:36 replies and6 unsupported
SmolVLM2 image requests. Qwen3-VL4B/8B pass grid3/3+box3/3;2B grid2/3+box3/3.
Qwen3.5 2B grid2/3+box2/3;4B grid3/3+box2/3, both positive boxes wrong.
Moondream grid0/3 and allboxesinvalid. SavedGemma grid1/3+box2/3 retained unchanged.
Dashboard/report show exactinput overlays and rawanswers;42 request identities,
36 CPU residencies and48 UIpanels verified. No flight/runtime promotion. Recommend
Qwen3-VL4B for new independent imagegate;one positive scene is not generalization.
CPU-only server stopped afterunload;Valley/sharedserver not changed. No cloudcost.


## 2026-09-14 - User-requested local model cleanup
Removed exactly five Ollama models: qwen3-vl:8b, qwen3-vl:2b, qwen3.5:4b, qwen3.5:2b, moondream:latest.
Verified all five absent from the local inventory afterward. Qwen3-VL4B, Gemma
and other unlisted models remain. D-114 raw evidence, dashboard and historical
configs remain available; removed models require reinstalling before fresh inference.
No inference calls, flight changes or historical result changes.


## 2026-09-15 - D-115 six-frame Qwen4 validation frozen
User approved six new saved-frame bbox checks followed by one conditional clutter flight.
Frozen unchanged D-114 bbox prompt/schema/options on three positives (far-left,medium,
close clipped) and three absent views. Six distinct hashes excluded from previous probes;
source bytes/observation IDs verified, offline red-body reference boxes visually checked.
Required all6:positive IoU>=.5 and center inside;negative false/zero box. No retries.
No inference yet. Raw selection/freeze preserved in reports/qwen4_validation_20260915.

D-115 preparation correction: repaired a syntax error introduced while wrapping long
freeze-description strings. It prevented the runner from starting; zero model requests
were made. Frozen image files, prompt, criteria and options are unchanged.

D-115 image gate complete:6/6 pass; positive IoUs .7704/.9383/.9767 and3 correct
absences,all JSON in thinking. Six exactrequest identities andCPU residencies checked.
Dashboard8766 was stopped; restarted and verified6panels/overlay/rawreply controls.
New opt-in c5_clutter_qwen4_validated_dev changes only ID/name,policy+monitor+backend
model,digest,host andresponse channel. All navigation mechanisms andfixed simcharge
remain identical toD-111.48 existing inference/OnFly tests pass. One90s clutter
seed1061 flight frozen;GPU server separate from sharedGemma server.

## 2026-09-15 - D-115 one Qwen clutter flight and visual recovery audit

retain Qwen4 as a named diagnostic profile; do not promote a general
planning result. Six image checks pass, but the one authorized clutter flight
still times out at 90 s (closest13.75 m versus savedGemma22.58 m), zero collisions.
134 completed flight calls, one final cancellation, no inference errors.
Recovery triggers correctly at37.2 s but expires10.314 degrees short; exploration
resumes while loss remains active. Crucially, a saved-pose offline render at the
complete saved heading still contains no target. Extending the timer alone is
not supported as a sufficient fix. Next isolate reacquisition/expiry semantics
and viewpoint/position recovery; any new search behavior must be named as an
architecture extension rather than silently attributed to the original paper.
Evidence: reports/qwen4_validation_20260915/FLIGHT_REPORT.md, FLIGHT_AUDIT.json,
RECOVERY_COUNTERFACTUAL.json and archived flight/. 1800 poses/89 source images
match; both dashboards replay exactly and pass Edge playback/seeks. 48 existing
adapter/OnFly tests pass. Shared11434 untouched, dedicated11435 unloaded/stopped.
Status: bounded gate + one flight complete; recovery repair remains open.

## 2026-09-15 - D-116 cycle 1: fresh observation after lost recovery

User authorizes autonomous cycles for the next hours. Budget: at most four local
flights until 16:55 UTC, state in reports/recovery_cycle_20260915/STATE.json.
Saved D-115 evidence: at39.25 s movement resumes from obs760 captured37.95 s,
during the37.2-39.2 s recovery. New opt-in monitor parameter clears pending
source at expiry and rejects delayed pre-expiry images; unchanged default keeps
legacy profiles reproducible. Fresh proposals resume normally. Policy feedback
distinguishes this temporal rejection from obstacle evidence and clears obsolete
point-rejection history. Timer, target search and waypoint generation unchanged.
117 focused router,OnFly,fence,hover,target-stop,inference tests pass; lint passes.
Initial test fixtures needed valid supervision/schema fields; no inference was
spent on those corrections. Named profile c5_recovery_fresh_qwen4_dev.

### D-116 cycle 1 outcome: handoff isolated, target still lost

New run c5_recovery_fresh_20260915_s1061 matches D-115 controls until39.25s.
Fresh-view handoff works: holds,rejects delayed pre-expiry observation at40s,
resumes41s from39.95s image. Timeout90s,closest13.401m vs13.746m,final29.939m
vs29.295m,zero collisions. No navigation improvement or promotion. 134 calls plus
one cancellation. 1800 poses/89 source images exact;20 browser seeks/2 playbacks
pass; actual source strip and41s dashboard visually inspected. Tooling fix excludes
rejection events with no source ID from source-frame lookup. Next offline policy
input/memory diagnosis, not another unchanged flight. One of four slots used.
Evidence: reports/recovery_cycle_20260915/REPORT.md, CYCLE1_HANDOFF.json, cycle1/.
Dedicated11435 unloaded/stopped. Follow-ups active until16:55UTC.

### D-116 continuation: freeze six-call input/action-space diagnosis

Local implementation lock confirms memory belongs to monitoring; policy is current
image plus previous-goal reprojection. Grounded diagnostic prompt omits the latter.
Adding last-seen images or non-point actions is therefore a named extension, not
a repair to the published OnFly mechanism. Freeze two current images (obs800/920)
with last policy-confirmed target obs680, three conditions each: unchanged point
interface, history plus same point interface, history plus diagnostic action choice.
Only onboard odometry, existing model claims and exact saved pixels are supplied.
Six local calls maximum,no retries,no executed movement. Score current visibility
and obstacle-face pointing; inspect action changes, do not claim navigation success
or promote a flight from this probe. See context_probe/FREEZE.json.

### D-116 saved-view probe outcome: context is insufficient with point-only output

Six replies complete without errors. Both current frames absent; all labels agree.
All four point-only answers (with/without history) select gray obstacle faces;
history-point evidence incorrectly names historical red target. Both action-choice
answers distinguish historical/current frames and request backtrack. No action
executed and no general planning claim. Local mechanism lock makes position return
an architecture extension, not an OnFly repair. Next bounded component tests for
VLM-selected return to observed pose+heading before another flight. Reacquisition
is not mission completion; repeated approach-loop risk must remain visible.
Evidence: reports/recovery_cycle_20260915/context_probe/REPORT.md, six frozen
requests/replies, validated current-pixel overlays and browser capture. Dedicated
11435 unloaded/stopped. Flight count remains1/4.

## D-117 - VLM-selected observed-view return extension (2026-09-15)

Decision: introduce a named experimental policy and bound option verifier, not a
silent OnFly modification. Model chooses backtrack/continue/hold; backtrack binds
to its stored observed pose+heading,one request/episode,30s anchor age,20s deadline.
Normal waypoint provenance remains checked; option goals cannot substitute model
coordinates and go through common geometric verification,SUPER,controller.
Optional waypoint camera-heading contract supports pose restoration; stationary
observation holds now have a braking-clearance-checked planner path.
Evidence: saved784-pose prefix followed by stub-selected return restores view in9s,
2.31cm position error,3.13deg yaw error,zero collisions,all10 plans accepted.
Actual RGB shows target reappearing. Return component and unit negative controls
are execution evidence,not a VLM flight result. See return_component/REPORT.md.
Status: component validated; single model flight pending frozen test/commit gate.

D-117 implementation gate:393 unit tests pass (one existing dependency warning),
new tooling/runtime lint passes. CYCLE2_FREEZE.json freezes one Qwen4/1061 flight.
Source-image auditing recognizes historical+current recovery input ordering.

### D-117 cycle 2 outcome: actual return succeeds, repeated occlusion remains

One live Qwen request selects backtrack39s; verified pose+heading return completes
48.5s; actual current RGB target reappears. Decisions50/51s correctly point at red
source pixels. After movement it disappears again and monitor reports LOST53.2s.
Timeout90s,closest14.930m (baseline13.746m),final17.007m (baseline29.295m),zero
collisions,min obstacle distance1.106m. Mixed metrics,not navigation improvement.
124 completed calls+1 cancellation,zero errors.1800 new poses/79 current images/1
historical image exact;32 browser seeks/2 playbacks pass. Actual49s dashboard
and camera sequence inspected. Reports/recovery_cycle_20260915/cycle2/REPORT.md.
Next offline isolate current_grounding's deterministic absence->LOST mapping and
CONTINUE+absence normalization. These conflate occlusion with progress failure;
causal impact needs testing before another flight. Retain strict STOP grounding
and arrival checks. Two of four flights used; dedicated11435 stopped.


## D-118: opt-in semantic progress monitor probe (2026-09-15, provisional)

Code diagnosis: current_grounding discards history, asks only current visibility,
then maps visible to STOP candidate and absence to LOST. A later normalization
also converts CONTINUE+absence to LOST. This prevents temporal progress judgment.
Add semantic_progress=false by default; opted-in monitor receives chronological
history sheet plus separate current RGB and owns its CONTINUE/LOST judgment.
Current target identity, depth, distinct confirmations and arrival-memory checks
remain. Absence+CONTINUE never refreshes last normal recovery anchor.
This is a NAMED semantics ablation, not a claim of native paper fidelity: the
existing paper prompt itself associates disappearance with LOST. No promotion.
Evidence: full unit suite400 passed before additional layout validation; final
test record accompanies commit. Frozen six-call paired probe at obs680/720/1340
from D-115:1340 replay poses,3 actual policy RGB matches, actual monitor request
construction and reconstructed hybrid memory. Independent monitor cases begin
acquired, with no confirmed arrival memory; not a replay of all monitor hidden
state. Freeze contains criteria, exact requests, input hashes, depth and poses.
No cloud, retries or extra flight.


### D-118 outcome: joint semantic/current monitor fails identity gate

Six local calls,all validJSON,zero errors/retries. Legacy current-only passes
current identity3/3 selected scenes; candidate history+current only1/3. At33.95s
its point hits ground;35.95s it transfers HISTORY4/5 target to current gray wall
and asks STOP. Runtime depth/confirmation guards block every STOP in this probe;
false identity still forms a wrong geometric candidate,so do not promote.
401 unit tests pass;1340 replay poses/3 sourceRGB/9 encoded inputs match;6 browser
cards/details and actual point/history images inspected. No new flight;2/4 used.
Read reports/recovery_cycle_20260915/semantic_probe/REPORT.md. Next offline split
current-only grounding from status-only temporal reasoning; the latter must not
redefine visibility/coordinates or authorize STOP. Reuse frozen grounding for
diagnosis only; future live design must charge both calls/latencies. No oracle.
Code/freeze02b3deb; candidate remains disabled/no enabled profile. Dedicated11435
unloaded/stopped.12 saved-frame calls total,shared11434/Valley8765 untouched.


## D-119: status-only temporal monitor probe (2026-09-15, provisional)

Rationale: D-118 joint image-history localization corrupted current identity.
Freeze3 local status-only calls on the same3 source contexts, with the unchanged
D-118 current-only grounding answers supplied as timestamped evidence. Temporal
output is limited to evidence/CONTINUE/LOST; no coordinates, visibility or STOP
authority. No runtime change yet. This is a named architecture experiment, not
paper-profile repair. Gate: valid schema and evidence consistent with current
grounding, CONTINUE visible/first-occlusion and LOST sustained-loss to support a
flight hypothesis. This criterion does not label the route traversable. No repeat
prompt tuning on these cases if it fails. All3 attempts retained, no retries.
Evidence pending in reports/recovery_cycle_20260915/status_probe/FREEZE.json.
Use CPU-only dedicated11435 while Valley runs; do not compare latency to flights.
Frozen grounding reuse is diagnostic; live integration must charge both calls.


### D-119 outcome: current identity respected, first occlusion still LOST

Three status-only CPU calls:CONTINUE/LOST/LOST at33.95/35.95/66.95s; validJSON
and evidence respects frozen current grounding. No experiment-entry gate pass
because first occlusion stillLOST. Six input hashes and CPU residencies verified;
3 dashboard cards/6 details pass. CPU+prompt both differ from D-118,not causal
performance comparison. Keyframe history at35.95 ends27.85,omitting33.95lastvisible;
temporal information may be insufficient. Do not tune these sameframes again.
Next offline execution probe: hold cycle2's last accepted target-bound goal51s
rather than replacing it with52s exploratory wall point; ask if common SUPER
can complete it from saved state. No oracle steering/model call; intermediate
waypoint completion is not mission success. Read status_probe/REPORT.md.
15 saved-frame calls total,2/4 flights; dedicated11435 stopped,Valley untouched.


## D-120: memory-cadence correction and bounded goal-hold fixture (2026-09-15)

Correction: D-118/D-119 prepared history by updating hybrid memory each control
tick; live runtime updates it on decision/perception cycles. Current RGB and raw
responses remain exact,but history is constructed,not exact runtime replay.
Event-ordered audit matches1340 poses and68 memory item counts. Actual history
latest times26.95/34.95/52.95 forcurrent33.95/35.95/66.95: gaps7/1/14s. Thus
the D-119 claim of8.1s live-history gap at35.95 is withdrawn. Preserve raw frozen
inputs/results; no model reruns. Reports/dashboards prominently correct scope.
Evidence: reports/recovery_cycle_20260915/memory_cadence/RESULT.json.

Freeze a separate20s execution component at cycle2 time51s, retaining its already
accepted target-bound intermediate goal. Replay every planner invocation and
control in recorded event order; require prefix pose,plan points/feasibility and
first branch command matches. Repeat common planner1Hz/controller20Hz; no VLM,
monitor or semantic goal replacement. This deliberately renews execution of a
saved goal beyond semantic freshness as a bounded component,not live architecture.
Stop at unchanged1m tolerance,collision or20s. No oracle steering. It tests common
executor capability,not mission success or beneficial commitment policy.
Fixture frozen in goal_hold_component/FREEZE.json; outcome pending.


### D-120 goal-hold outcome: useful detour, intermediate endpoint not reached

Exact1,020 prefix poses/61 planner outputs/first branch command match. Holding
accepted51s target goal for20s produces a collision-free right-side detour; red
reappears by64s in sampled RGB,visible through71s. Evaluation-only true target
distance16.885→10.143m. Frozen waypoint endpoint fails:closest4.928m,final6.150m
(start5.282m),tolerance1m. All20 newplans feasible with known-free backup and
reaches_goal=false.21 UI seeks and actual camera/map inspected. No model calls.
This supports an execution-persistence hypothesis,not mission success or proof
SUPER cannot reach the goal. Intervention removes both replacements and monitor
yaw,so next live extension must make arbitration explicit. Stored goal center
clearance0.423m is below0.6m, but1m tolerance prevents infeasibility conclusion.
Next named bounded target-goal commitment with explicit original-source lease,
fresh-target supersession, expiry, common planning and STOP guards; unit-test
ownership/expiry before one model flight. Do not label as native paper repair.
Evidence: goal_hold_component/REPORT.md,RESULT.json,VISUAL_EVALUATION.json.
Flightcount2/4; saved-framecalls15; shared11434/Valley untouched.


## D-121: bounded accepted-target execution variant (2026-09-15)

Rationale: D-120 held-goal component restores the target after a useful detour,
while live exploration/LOST recovery interrupts the same accepted intention.
Add target_commitment_s=20 only in c5_target_commitment_qwen4_dev. Baselines
default0. An already verified/planned model-target goal arms a candidate. Fresh
exploration or monitorLOST can activate it while original source age<=4s; deadline
is activation+20s and exploration cannot extend it. Replans use fresh onboard
geometry but commands preserve ORIGINAL decision/image timestamp and sourceID.
Deferred exploration is logged rejected,with retained-goal plan metadata. Age
remains measurable; intentional lease commands have their own counter.
Fresh verified target supersedes it. Arrival at the intermediate tolerance ends
the lease without missionSTOP; expiry, STOP or planner failure ends execution.
LOST label is retained andlogged; only its yaw action is deferred while the lease
owns motion. Expiry restores ordinary recovery. Existing STOP guards unchanged.
This is a named architecture extension,not nativeOnFly or D117return-to-view.

Validation: full suite420 passed and20 focused commitment tests passed including
new orchestrator LOST/arbitration integration. Final lint/checks before flight.
Tests cover original-source preservation,nonrenewal,expiry,staleness,reset,
verified supersession,rejected-target retention,planning failure,recovery ownership
and defaultoff behavior. Policy feedback says deferred,not obstacle-rejected.
One flight frozen in CYCLE3_FREEZE.json. CPU-only dedicated11435 while Valley runs;
hardware placement differs from priorGPUflights, so inspect pre-lease equality and
do not treat outcomes as a clean architecture-only comparison if prefixes differ.
No cloud/newmodelcalls/reinstalls; fixed simulated latencies unchanged. Third of
four flight slots reserved,2 completed; deadline16:55UTC.


### D-121 debugger provenance support

Retained-goal replans are logged under rejected incoming exploration but command
source remains the original accepted target. The debugger now chooses the latest
feasible plan atcursor time by its explicit execution owner,not the original
decision's first plan. This prevents displaying a stale path during a commitment.
Five browser behavior checks cover old/new/infeasible/future/unowned plans.
Runtime flight3 remains unchanged andrunning; this is offline viewer support.


### D-121 flight audit preparation

Dedicated11435 residency confirms Qwen3-VL4B entirely onCPU(size_vram0); shared
ValleyGPU untouched. Added completed-flight audit for original target sourceID/age,
nonrenewing20s deadlines, deferred exploration versus executed commands, LOST
label/action arbitration and realized control-prefix comparison against D115/D116.
Browser review will seek each actual lease activation,midpoint anddeadline.
No flight restart or runtime changes; cycle3 continues.


### D-121 interim evidence, flight still running

First13-18s commitment preserves a genuine model-identified red target despite
exploration proposals on gray walls; later actual current target is visible.
Second lease activates41s, monitorLOST41.2 is logged but yaw deferred. Partial
source/deadline audit has zero violations; these are interim observations only.
Source images/point overlays retained in cycle3/INTERIM_SOURCE_POINTS.*.
Realized control differs from D115/D116 already1s, before firstlease13s. Initial
prompt/schema/image bytes match, but model response differs with CPU/GPU placement
different. Therefore final outcome alone is NOT clean architecture-only evidence.
No attempt to change or restart the running flight. Await completion then full
replay,leaseaudit and visual review. Dedicated11435 runningCPU,not stopped.


## 2026-09-15 — D-121 final flight audit and autonomous batch completion

Thirdflight timeout90s,closest/final4.647m,zero collisions. Camera shows detour and
red reacquisition74s; all15 finalpolicy points are onred and75–90s approach monotonic.
Fullleaseaudit zero violations; actualsourceages retained,599 leasecommands/13LOSTyaw
deferrals.1800poses/89images exact;66UIseeks/2playbacks and7finalcaptures reviewed.
Added reproducible finalapproach review script and cycle3/overall reports. Explicitly
retain CPU/GPU prefixconfound, floatingpoint speedcounters and failedmission outcome.
Rawcapture archived; earlier changes separatelycommitted. No runtimechange thisstage.
Three of maximumfour flights used,392completedflightcalls+3cancellations,15savedprobes.
Dedicated11435 unloaded/stopped; debugger8766 stays. No fullfourth43minuteCPUflight
beforedeadline. Next exactcheckpointreplay then separatelyfrozen arrival/STOPextension
in time; do not claim a90sbenchmarksuccess or validatedgeneralplanning.


## 2026-09-16 — D-122: exact replay and bounded continuation frozen

User authorized continuation after the completed autonomous batch. New diagnostic
harness reconstructs unchanged runtime using134 original responses, with135 exact
request/schema/image/time checks including the cancelled boundary request. All1800
controls,89 plans,90 memory updates,45 monitor events and58 verifier events match;
final distance matches4.6466100018947385m exactly. No modelcalls for this dry replay.
Eight harness tests pass, including changed prompt/image/model/time rejection.
One CPU-only local continuation is frozen to120s (30s extra), max47 fresh requests.
The original cancelled89s request is reissued and first becomes available90s;
subsequent requests use fresh current observations. Original90s failure preserved.
Only horizon and matching evaluation time limit change; policy/planner/arrival/STOP
rules unchanged. Cache timing is not model latency; no causal architectureclaim.
Evidence: reports/continuation_20260916/DRY_REPLAY.json and FREEZE.json.


### D-122 outcome: exact continuation completes arrival and terminal STOP

With no navigation changes, source90s trajectory continues into2m radius94.5s and
monitor STOP97.2s. Final environment97.25s distance0.936299m, speed0.051758m/s,
zero collisions. Declared arrival+terminalSTOP passes; sustained settled hover is
not tested. VLM supplies current target identity/point; metric monitor gates STOP.
Both dry/live prefixes match1800 controls/89plans/90memory/45monitor/58verifier events
and135 request identities. Full replay1945poses/97policyimages;49monitorimages match.
10UIseeks/2playbacks+terminaldecision reviewed with actual camera/map/source images.
13 fresh local attempts:12complete(8policy/4monitor)+1cancelled;134cached replies.
CPU-only retainedQwen4, freshmedian25.633s, fixedsim1s/1.2s; no real-time claim.
Original90s timeout unchanged. This is a longer-budget singletrajectory success,
not causal architecture comparison or reliability evidence. No runtimefix required.
Evidence: reports/continuation_20260916/REPORT.md and raw/audit artifacts.
Next matched commitment on/off under identical placement/budget/seeds. Dedicated
11435 unloaded/stopped, debugger8766 retained, shared11434/Valley untouched.


## 2026-09-16 - VLA/AWS plan recovery and resource inventory (D-123)

Created isolated worktree/branch codex/vla-aws-pilot-20260916 from 6be9a55.
Recovered old Qwen SFT/DAgger plan and read current nine-condition/eight-regime
paper design. Saved public model/dataset revisions and Stockholm pricing.
Recommend one 24 GB GPU; no GPU instance, credentials or cloud resources used.
AWS inventory is blocked by missing SSH/SSM connection and browser sandbox
startup failure. User wants machine approval before launch and again before
training. Added credential-free host inventory script; local inventory is
explicitly the laptop, not the AWS instance. Pilot/transfer plan and limitations
are in docs/research/VLA_AWS_PILOT_20260916.md. Existing baselines and splits intact.


## 2026-09-16 - VLA data preflight and portable export (D-124)

Added strict separate qwen_vla_preflight module: image decoding/hashes, 1:1
annotation coverage, prompt agreement, exact target types, manifest counts,
seed separation and explicit portable image root. New export refuses overwrite
and copies only audited dataset files. Preserved all 4,765 original images,
labels and the 80/20 seed split; no forbidden development/evaluation seeds used.
Measured missing terminal labels in 35/100 successful episodes and documented
analytical teacher-codec mismatches. Corrected initial prompt-drift claim:
Windows-default decoding caused the false alarm; UTF-8 prompts match exactly.
97 focused unit/contract tests pass; all new Python files pass Ruff. No model
training, model prediction, simulation flight, cloud job or spend occurred.


## 2026-09-16 - Correct VLA storage sizing (D-125)

User challenged the 100 GB recommendation. Measured published repository file
sizes without downloads: approximately 861.4 GB across five relevant corpora/
simulator repositories, before extraction/caches. Revised plan separates root
and data disks: 512 GiB staged pilot data, provisional 2 TiB broader working set
subject to expansion measurement and cost approval. Recorded recurring storage
costs and corrected the old 5 USD proposal's applicability. Verified current
AWS documentation for the screenshot's PyTorch 2.13/Ubuntu 26.04 image family;
training dependency compatibility remains untested. Metadata/docs only; no
infrastructure changes, secrets, training or evaluation seeds used.

## 2026-09-16 - Original VLA dataset playback and provenance clarification (D-126)

Added scripts/build_vla_dataset_viewer.py and a standalone camera/label viewer.
The generated viewer embeds all 4,765 original JPEGs (byte identity verified),
supports 100 episodes, split filtering, timestamped playback and exact prompts.
The saved dataset has no original full pose/control logs; viewer labels identify
recorded supervision rather than predictions, live feed or reconstructed flight.
Documented single-instruction/simulator coverage, simulator-derived bearing prior,
absent real/external-simulator data and provisional QLoRA rationale.
Fresh Edge checks pass 12 source/label/time checks, split filters, playback and
responsive layout; visual preview inspected. Build/check scripts pass Ruff.
No trained model, new collection, cloud operation or evaluation-seed use.
Existing unfinished direct-action contract draft remains separate and unused.

## 2026-09-16 - Required broader VLA training data (D-127)

Added an explicit staged plan for diverse paper tasks, additional photorealistic
simulation and real-flight recordings, source/action/calibration audits, protected
group splits and mixed-domain learning curves. User's requirement is mandatory
beyond the tiny local pilot. Existing corpus coverage is not assigned an invented
percentage. Updated pilot, TODO and handoff; no source imported or training run.

## 2026-09-16 - Additive VLA velocity-contract execution gate (D-128)

Validated direct_velocity_yaw_level_v1 without editing native AeroVLA or paper
profiles. Exact zero/explicit STOP, strict finite/frame/range checks, no silent
teacher clipping, source-yaw rotation and integral control-tick horizons.
52 focused tests pass;4096 command samples and128 matched physics segments
bound quantization/controller error (maxpositiondrift7.35mm over0.2s).
Recorded controller speed projections and verified router expiry/hold behavior.
No trained checkpoint, new training dataset or real-world claim.

## 2026-09-16 - D-129: synchronized observable VLA fixture

Added independent public-coordinate teacher collection and strict replay audit.
Eight seeds1400-1407,272 samples,204/68 frozen split; full RGB/state/raw teacher/
decoded action/executed control/terminal traces on D drive. All integrity gates
pass, including1194 exact physics steps and816 saved image comparisons.
Debugger shows teacher actions and flights; no trained predictions or semantic
navigation claims.29 focused tests pass; no baseline or original dataset edits.

## 2026-09-16 - D-130: actual local Qwen QLoRA overfit and reload

Implemented bounded assistant-only NF4 LoRA training in an isolated D-drive
Python environment.200 updates/269s,4.47GB peak PyTorch allocation on local
RTX4060.16/16 well-formed predictions,9/16 exact,0/4 terminal STOP correct:
overfit acceptance fails despite loss reduction. Save/reload predictions match
16/16. Kept both startup failures and all results. No AWS/global package changes.

## 2026-09-16 - D-127 follow-up: concrete wider-data admission gaps

Inspected small public schema/log previews from UAV-Flow real/sim and Exp2VLA.
Recorded differing native formats and next five-flight audits; no source treated
as action-compatible merely because images/pose logs exist. Expansion plan now
states measured coverage and zero admitted real/external-simulator episodes.

## 2026-09-16 - D-130: model-driven failure replay and pilot report

Completed three capped offline model flights;all timeout at2.95m,1.75m,8.00m.
Simulation pauses during measured inference; no real-time capability claim.
Saved exact inputs/prompts/raw predictions and controls. Independent audit
passes150 original-image/prompt checks and600 prediction-to-control steps;
modified-image/control negative tests fail as intended. Existing debugger shows
actual model flights separately from teacher flights;9 browser source/response
checks and3 terminal outcomes pass.61 unit/regression tests pass. Report and
next blocked training/data/cadence gates recorded; no AWS or baseline changes.

## 2026-09-16 - D-130 loss-curve review

Added reproducible PNG/SVG plots of all200 recorded training losses, trailing
16-update average, and STOP/HOLD/motion means per complete16-example pass.
Explicitly labels absent validation-loss measurements and failed exact-action
criteria. No new training, smoothing of source records or extrapolated metrics.

## 2026-09-16 - D-131: versioned heading-level FRD contract

Added separate forward/right/down, clockwise-yaw codec with distinct JSON keys.
Preserved legacy contracts and checkpoints.41 focused tests pass, including4096
physical-equivalence cases;new converted dataset keeps272labels,204/68 split,
816 exact camera hashes and exact decoded actions. Source files unchanged.

## 2026-09-16 - D-132: action-value-weighted FRD retry

Training-only diagnosis found near-zero formatting loss hiding value errors.
Added strict field-span weighting and shuffled frozen16-example subset.
200updates:13/16exact versus4/16matched zero-shot;STOP/HOLD4/4 each;gate still
fails on numerical actions. Identical reload16/16;4.617GB peakPyTorch allocation.
Preserved suffix-preflight failure and raw metrics. No expanded training yet.

## 2026-09-16 � FRD tiny-overfit gate passes (D134)

Final authorized lower-LR continuation used the same16 TRAIN examples, fresh
AdamW and200 updates (262.625s).16/16exact,16/16valid,allSTOP/HOLD correct,
reload identical;4.617GB peakPyTorch. TotalFRD400updates across two attempts.
Preserved13/16failure. Weighted and ordinary-token loss plots distinguish
objectives;this is memorization, not flight/vision generalization. NoAWS.

## 2026-09-16 � Observable visual pairs and external-source audit (D133/D127)

Collected64local visible-pillar yaw segments with instruction/color swap pairs;
independent replay passes320states/192frames/256controls and64paired checks.
20focused tests pass. Retained two failed collection startups;no hidden-target
label fallback. Added native-source playback with158browser byte/log checks.
Audited5complete real+5external-simulator preview sequences,531frames/~10MB.
No external action labels admitted:license/calibration/control/split semantics
remain unresolved. No model visual-dependence or real-world readiness claimed.

## 2026-09-16 � Matched FRD flights and debugger (D133)

Frozen two-scene comparison completes:zero-shot0/2,adapter1/2;trained final
distances3.630m(timeout) and0.113m(validSTOP).186actual model calls,741controls
pass source and replay audit;image/control mutations rejected.12browser checks
pass,including successful-outcome display.77focused tests pass. New debugger
frd_comparison.html preserves older pages. Added per-scene curves,latency limits,
checkpoint hashes,coverage report and updated handoff. Original fixture bytes
unchanged;protected seeds excluded. This is not real-world readiness.

## 2026-09-17 � Cached SmolVLM256 correctness and local expansion (D135/D136)

User corrected initial500M choice;its download failed with a Windows symlink
error and no500Mtraining occurred. Located complete cached image-only256M
weights. Native template/prefix/value mask preflight passes;first200updates
6/16exact,11valid;second lower-LR200 reaches16/16exact/allSTOP+HOLD with
identical reload. BF16+LoRA peak1.061GB;preserve failure. Froze252localTRAIN/
84VAL mixed-data protocol and reproduced identical index/schedule bytes.
No external data added. Expanded Smol training now running;Qwen follows.

## 2026-09-17 � Smol256 mixed local result (D136)

400fresh-adapter updates on252training rows complete in140.359s;1.050GB
peakPyTorch. All28validation probes return validJSON,4/28exact. Visual outputs
are constant clockwise yaw42:8/16directions,0/8instruction pairs,0/8color-swap
pairs;blank images change0/16outputs. Both terminal probes remainHOLD. Useful
pilot gate fails. All84validation CE1.4910/0.1489/0.1528 at0/200/400;no
checkpoint selection. Four reload probes identical. Source/prediction viewer
passes88exact checks.400executed sampleIDs match frozen schedule;val disjoint.
Qwen comparison remains running;noexternaldata or paid compute.

## 2026-09-17 - D136: matched local Smol256/Qwen training and visual execution

Used the cached Smol256 image-only model as requested. Fresh adapters completed
same400 updates on252 existing TRAIN rows;84 VAL rows remain isolated. Qwen
visual direction16/16 versus Smol8/16;both fail the STOP criterion. Exact-source
saved-action execution and independent control audits confirm16/16 versus8/16
bearing improvements. Both models' source images, prompts, raw outputs, decoded
physical actions and resulting images appear in the prediction debugger;176
browser assertions pass. Generated training/validation loss plots and recorded
schedule audits. No external data, AWS, physical flights or baseline changes.

D136 review polish:embedded the exact loss plot in an expandable viewer section;
176 prediction checks and an exact plot-byte browser check pass. Normalized
Matplotlib SVG trailing whitespace; Ruff and git diff whitespace checks pass.

## 2026-09-17 - D136: finish matched model-flight evaluation

Eight bounded offline flights complete. Both mixed adapters0/2success;Qwen
approaches then holds4.4108m/2.0395m away,Smol never translates. Prior tiny Qwen
1/2success is not preserved.302calls/1202controls pass exact replay;20browser
checks and all8outcomes pass. Repeated Qwen baseline100/100calls unchanged.
Flight pages and full limitations recorded; no cloud/physical/external-data work.

## 2026-09-17 - D137: freeze Smol size/duration comparison

User requests500M and longer training. Downloaded/pinned image-only500M on D:;
added model-path override to existing tiny gate without changing256 defaults.
Prepared matched400/1200 comparison,continuing preserved256step400 adapter,
unchanged data/splits/sampling/LoRA. Full-split eval-mode weighted action loss
and ordinary CE now measured on both TRAIN and VAL,with task breakdowns.
Masked shifted weighted-loss and original-schedule preservation tests pass;
336-row256CPU preflight and source/model hashes recorded. New viewer/plots
are separate from prior results. No mixed duration job has started yet.

D137500M correctness gate completes:16/16 exact at400total tiny updates,
allSTOP/HOLD and all16reloads identical;1.628GB peak. First200attempt retained
(9/16exact). Added exact prediction/plot browser checks and schedule summaries.
256M duration job started from preserved400adapter;no changes to data balance.

## 2026-09-17 - D137: complete256M duration arm and expose comparable losses

Continuation to1200passes exact800-ID schedule audit,28resume predictions and
4reloadspots. Weighted TRAIN0.496->0.334,VAL0.518->0.732:overfitting under this
recipe. CoordinatevelocityMAE improves0.334->0.221m/s,butvisualdirections8/16,
pairs0/8,STOP0/2.88browser checks and16visual execution audits pass. New viewer
contains full/focused loss histories and task breakdowns;prior viewer unchanged.
500M mixed arm is running. No validation-selected checkpoint or new data.

D137 saved-action debugger:handle a valid model STOP as stationary diagnostic
hold rather than dereferencing a missing kinematic action. A labelled synthetic
STOP regression passes;excluded from model metrics. No training or router change.

## 2026-09-17 - D137: finish500M and capacity-duration comparison

Both sizes400->1200stay8/16visualdirection and0/2STOP;both finalpairtests0/8.
500M has lower validationloss than256M,butits validationloss also worsens from
400to1200 whileTRAINimproves. Coordinateerrors show mixed improvement.
All schedules/reloads checked;32actual savedvisual segments/128controls pass
independent audit,176browser checks and3exact plot-image checks pass. No new
closed-loop flights,AWS,externaldata orprotectedseeds. Separate viewer preserves
priorpages;full evidence andnextlocaldiagnostics recorded inD137 report.


## 2026-09-17 - D138 local data expansion and balanced batches
Added60 new source scene groups;admitted TRAIN252->1156 and VAL84->300 while
preserving every original row. Independent source/control audits reject14
conflicting images and15 unobservable geometry proposals. Added four-task
effective batching and actual two-update Smol256 GPU smoke test.53 unit tests
pass;data/teacher-flight debugger verified. No full new model experiment yet.
Evidence:reports/vla_local_expanded_20260917_v4/REPORT.md.


## 2026-09-17 - D139 matched local comparison started
Frozen same400updates/1600exposures on balanced original versus expanded data.
Control complete/reload verified;expanded condition running sequentially.
Control fails visual/STOP gates despite lower losses. Separate original/new
validation and equal-task loss plots,raw-output scorer audit and debugger
comparison prepared. No cloud spend or architecture baseline changes.


## 2026-09-17 - D139 comparison and simulation evaluation complete
Two matched Smol256 runs complete;expanded data improves loss/STOPrecall but
not pairedvision,and adds premature stops. Both fail2/2flights. Published
loss/task plots,134probes/condition,visualafter-images and8flightreplays at
localhost8771/balanced_comparison.html. Rawsource/replay/reload/browser audits
pass. Goal comparisoncomplete;fulltraining/deploymentgates remain unmet.
No AWS spending. See reports/vla_balanced_comparison_20260917/REPORT.md.


## 2026-09-17 - D140 condition labels and OpenFly checkpoint

Fixed Original/Expanded flight labels and added execution/action counts; checked
source playback and stationary timeline. Downloaded and SHA-verified published
OpenFly checkpoint on D:; isolated inference compatibility probe underway.

D140 complete:localOpenFly4-bit inference verified and initial16-casecomparison
published with both official prompt formats.8/16direction withtrainingtemplate;
0/16withmodelcardprompt. Native flight interface still requires audit.


## 2026-09-17 - D141 expanded model jobs and OpenFly evaluation data

Generalized balanced runner toSmol500/Qwen;bothsmokes pass. Sequentiallocal
400update runs started. Prepared51officialheld-outOpenFlyframes with source
checks and explicit exclusions;fixed transfer/scoring protocol before inference.

D141:added combined progress/loss/official-source viewer and sequential
posttraining evaluation coordinator;no premature comparison scores displayed.


D141 final execution complete: both expanded-data training jobs, all four official
OpenFly offline evaluations and audited Smol500/Qwen local flights finished.
Results and limits: reports/vla_expanded_models_20260917/REPORT.md.
No external training rows, AWS spending or native OpenFly flight-success claim.


## 2026-09-17 - D141 evaluation recovery and transparent failure counts

Fixed the flight audit to accept explicit trained-only modes while preserving
the default four-run paired check. Resumed completed artifacts without repeating
GPU inference. Both expanded runs and their four local flights are now audited
and finalized in reports/vla_expanded_models_20260917/REPORT.md (abd4ed0).
The dashboard now separates invalid outputs and mixed commands; unchanged scores.
Two existing native-action scoring tests and 204 browser source/output checks pass.


## 2026-09-17 - D142 native OpenFly data and bounded pilot

Prepared and audited22official TRAIN routes (258train/171dev), native action-ID
training interface and recorded-flight viewer. Started local Smol500 gated
memorization/pilot, separate from FRD baselines. Protocol and source data audit
are frozen;429browser source rows verified. No AWS spend. Outcomes pending.


D142 normalization follow-up: a CPU-only re-decode reproduces all saved original
actions to1e-12. Holding generated tokens fixed and using released-evaluator
vlnv1 changes coarse category accuracy12/51 ->29/51 and mixed32 ->0; macro
recall .1346 ->.3269; turn accuracy remains0/12. The alternate normalization
zeros unsupported dimensions, so this is decoder sensitivity, not new inference
or proof of corrected native benchmark performance. Original table retained.
Evidence: normalization_audit.json and scripts/audit_openfly_normalization.py.


D142 motion audit:910/911 consecutive raw parquet transitions match expected
atomic motion (forward3, yawleft+30deg/right-30deg, up+3/down-3 in source axes).
One train turn-right frame has zero yaw change; retained and flagged, not
retrospectively removed. Compressed annotation intervals include subsequent
movement and do not uniformly match macro magnitudes:22/22 ID8 intervals show
3sourceunits although released dictionary is forward6. Pilot learns released
IDs as a categorical imitation diagnostic, not verified continuous control.
Before control training, reconcile atomic/macro sequence alignment and exclude
or correct source anomalies under a new versioned protocol, preserving splits.
Evidence: motion_alignment_audit.json and audit_openfly_motion_alignment.py.


D142 completion: Smol5008/8overfit, then fresh160update native-IDpilot completes
in858.718s total;peak allocated1.401GiB. Train/dev eval-modeCE5.778/5.767 ->
0.488/0.521, but dev exact18/171, macro.1493, below majority113/171/macro.1667.
All171outputs become valid; base171/171invalid makes improvement over base
primarily a formatting result. Blank-image dev11/171 (allSTOP), macro.1667.
26falseSTOP/160nonterminal. Fourreloadspots exact;all960exposures TRAIN only
and everyeffectivebatchfourdistinctactions. Pipelinepasses;learninggateFAILS.
No moretraining launched. No comparison of171exact-IDdev against51coarseofficial
examples as if matched. Widerdata andnativeinference/temporalalignment remain
required before fulltraining orflightclaims;noAWSspending. Evidence:training_report,
training_audit,losses,loss_curves,REPORT.md underreports/vla_openfly_train_20260917.


D142 playback follow-up: user requested a few OpenFly clips. Created three
H.264 videos from all consecutive cached TRAIN frames: AirSim16 (63frames),
GS-ECUST (38), UE-bigcity (60). Fixed4fps inspection playback, explicitly not
physical timing, model rollouts or real drone footage. No generated/interpolated
frames. Source hashes and video metadata in clips_manifest.json; all three
videos browser-verified to decode and advance. Viewer:localhost8771/openfly_clips.html.


## D143 - OpenFly representation rationale and CognitiveDrone admission research

User requested these two sources specifically. OpenFly explicitly motivates discrete
VLN actions and3/6/9m forward granularities to reduce imbalance; no evidence found
that the released eight-entry encoding beats4Dvelocity control. CognitiveDrone
official public release is linked and invites training, but explicit license is
missing and only30of128named train shards are present. Community conversion has
1766episodes and7Daction container; mapping to paper4Dcontrol is unverified.
Add as candidate for symbol/reasoning/recognition tasks, pending small-shard
action/timing/coverage audit, split isolation and license clarification. No
training or model/baseline changes. Evidence and pinned inventories:
docs/research/openfly_cognitive_action_audit_20260917/REPORT.md.


## 2026-09-17 - D144 joint OpenFly/local training prepared

User requested all three local models: SmolVLM256M, SmolVLM500M, Qwen3-VL4B.
Added deterministic 110-route OpenFly expansion with raw consecutive-pose action
validation; 2929 TRAIN/815 dev, eight inconsistent targets quarantined. Preserved
local1156/300 and all protected splits. Added dual-contract source-balanced
8-sample trainer, fresh400-update protocol, bounded sequential queue and live
loss/prediction/flight review. All three two-update training/reload gates passed.
Full-run results pending; no AWS or deployment claim. Evidence: D144 protocol
and reports/vla_joint_openfly_20260917/data_audit.json.

D144 execution: all three smoke/reload gates pass (peak allocated GPU memory
0.862/1.388/4.839 GiB). Sequential queue launched; Smol256 baseline evaluation
first, then fresh400updates and audited local flights, followed by500 andQwen.
Live dashboard browser checks pass:100held-out cases (28local/72native), three
models, three causal native images, responsive layout and no JavaScript errors.
Full results pending; see joint_openfly.html and queue_status.json.

D144 follow-through: added independent all-model completion audit, raw prediction
re-parsing, exact schedule checks, six-flight source/control/replay verification,
and static loss-plot/report generation. Fixed live review handling of infinite
obstacle distances from simulator summaries while preserving raw answer strings;
browser regression test passes. Training remains active; no results claimed yet.

D144 viewer now decodes local target/predicted bins into forward/right/down m/s
and clockwise yaw rad/s, with explicit HOLD versus mission STOP. OpenFly keeps
3m/30degree primitive units. Browser scale/sign/extrema checks pass. Raw answers
remain available. Additional exact-input audit finds0label contradictions and
0cross-split identical-input groups across5200examples. Training remains active.

D144 recovery: a Windows sharing violation during dashboard replacement killed
the queue child after16Smol256 flight calls. Completed400-update adapter and
100held-out predictions are intact. Preserved partial flight/logs; added retrying
atomic writes, nonfatal publication errors, exclusive queue lock and explicit
reuse of verified completed runs. Simulated-lock/child-survival tests pass.
Resuming evaluation, then the unchanged500/Qwen training schedule.

D144 Smol256 complete:400updates, exact adapter reload,100held-out outputs.
Native18/72 (25%macro; always-forward12/72),72/72valid,9/60falseSTOP. Local
2/28exact,28/28valid, visualdirection8/16. Both10sflights timeout atinitial
distance8.541/8.000m: all100actual predictions are HOLD.400controls and both
replays/browser playback audited. Completed adapter SHA unchanged through
recovery. Smol500 baseline evaluation has started; Qwen remains queued.


D144 follow-up: Qwen CPU-only long-input preflight checked the twenty longest prompt-token OpenFly sequences among the 664 scheduled/evaluation native rows. Actual multimodal encoding and exact assistant-prefix masking passed; maximum checked length was 495 tokens against the frozen 2048 limit. This is a bounded input check, not an exhaustive VRAM test. Evidence: reports/vla_joint_openfly_20260917/qwen_long_input_preflight.json. No optimization settings changed.


D144 Smol500 complete: fresh mixed400-update adapter in2048.08s;100 held-out predictions and four reload checks pass. Native16/72 exact, macro0.2222 versus always-forward12/72, five false STOPs; local26/28 valid and2/28 exact. Final local validation loss0.3564; native2.2617, worse than step100(1.9127). Both local flights timeout: final distances6.4529m and0.6704m, goal radius0.35m.100 actual calls/400 decoded controls and replay poses audited, zero replay position error/missing images; six browser source-time checks, playback and responsive checks pass. Results do not establish deployment readiness or real-time control. Qwen is now the sole active model job. Evidence: reports/vla_joint_openfly_20260917/smol500_results.json, smol500_training_report.json, smol500_flight_audit.json and smol500_flight_browser/model_ui_check.json.


D144 dashboard audit: added scripts/check_joint_openfly_dashboard.py. Interim browser verification checks all100 held-out cases and image/provenance associations,200 raw Smol predictions against saved reports, both source loss series/four fixed-probe series, completed flight links, mobile overflow and JavaScript errors. Passed for Smol256/500; final invocation deliberately requires all three completed reports and remains pending Qwen. Evidence: reports/vla_joint_openfly_20260917/dashboard_interim_check.json.


D144 COMPLETE: allthree fresh local adapters finished400updates each, verified save/reload and100 held-out predictions/model. Qwen completed in4211.265s; local12/28exact,28/28valid; native17/72exact,macro0.2361,8/60falseSTOP versus base16/72. Both Qwen flights falseSTOP, final2.097m/0.432m outside0.35m goal radius. Allsixmodel flights fail. Independent audit validates1200updates,9600exposures,600raw before/after answers,12reloadspots,protected splits and baseline fingerprints, six actual flight/control/replay/browser audits. Final dashboard audit passes100cases/300savedanswers,images/provenance,plots/flightlinks/mobile; staticPNG/PDF and livepage visually reviewed. AllnativeVAL losses worsen after measuredstep100; larger/longer training is not justified by loss alone. No cloud spending and no active training job. Evidence: reports/vla_joint_openfly_20260917/REPORT.md,summary.json,completion_audit.json,dashboard_final_check.json,loss_curves.png/PDF and permodelreports/audits. Nextgate:training-only visual/history and mission-phase checks plus broader unique-route coverage; nativeclosedloop,real-time andphysicalflightqualification remainopen.


## D145 - Released openfly_vla matched-panel comparison (2026-09-18)

Rationale: user requested dataset scale and the released model alongside our three adapters. Evaluated the exact 72 D144 native cases, same route instructions and causal image hashes, with local NF4, raw released evaluator prompt and vlnv1 normalization. No new training. openfly_vla: 18/72 direction agreement, 8/72 exact primitive, 59/72 valid codebook actions, 2/60 false STOP. Other models remain 18/72, 16/72, 17/72 exact/direction. Longer forward macros explain ten direction-only matches; unknown vectors stay invalid. Official TRAIN overlap with released checkpoint is possible, so this is not equal-unseen evaluation or the official flight benchmark. Pinned manifests contain 103,226 routes / 1,655,355 annotated decisions; HF displays 2.97 TB of repository files. Added explicit model/dataset labels and side-by-side source/output viewer. Browser audit: 72 cases / 288 raw outputs; independent 72-token-vector re-decode passes. Prior dashboard passes 300 final-answer checks. Baselines and splits preserved; no AWS. Evidence: reports/vla_openfly_same_panel_20260918/REPORT.md, PROTOCOL.md, dataset_size.json, probe.json, decoder_audit.json, predictions.json and browser_audit.json.


## D146 - OpenFly comparison decoder and source-interface investigation (2026-09-18)

Status: investigated; D145 scores preserved, model-ranking interpretation withdrawn pending a verified interface. vlnv1 forces both vertical dimensions to zero, so24/72 targets were unreachable. Source identity72/72, next-motion60/60 and terminal annotation12/12 pass. All64 overlapping compressed annotations agree in direction. Prompt-only17/72 and history-pooling-only18/72 do not rescue baseline18/72. Vertical-capable normalization is unverified and also does not rescue it. Restricted representable48-case counts: OpenFly18, Smol25615, Smol50014, Qwen14; not a replacement benchmark.

Rationale: establish checkpoint normalization/history and native macro-action evaluation before further training or model ranking. Source example builder has future-history hazards, but its actual checkpoint use is unknown. Quantization contribution and instruction semantics remain unresolved. No AWS, training, split or protected-seed changes.

Evidence: reports/vla_openfly_forensics_20260918/REPORT.md, results.json, label_audit.json, source_evidence.json and browser_audit.json; scripts/audit_openfly_forensics.py, investigate_openfly_prompt.py and summarize_openfly_forensics.py. Dashboard: localhost8771/openfly_forensics.html.


## D147 - Repair OpenFly decoder coverage and data/evaluation contracts (2026-09-18)

Status: bounded repair and matched rerun complete; released-checkpoint calibration remains provisional. Added strict codec coverage/length/codebook checks and explicit annotation phase/XYZ-yaw parsing. vlnv11 can represent every evaluated primitive; original vlnv1/vln_norm fail coverage. Nine regression tests pass.

Data: audited all110 pilot routes/3,752 frames.3,634 moving transitions pass; eight remain quarantined (six identical image pairs, one nearly identical, one changing image with static yaw). All1,106 compressed forward blocks reference their last raw frame;284 cannot describe future motion from that index. Built separate1,639-row motion-verified macro manifest, same88 train/22 dev routes. Twelve preregistered alignment pairs improve OpenFly direction7/12 to11/12 and exact macro6/12 to9/12.

Broader audit: all100,226 TRAIN schemas validate after explicit handling.9,728 routes contain initial-climb(-1) and post-STOP-descent(-2) phases; pilot excluded them.8,160 recorded STOPs are over20m from the final position, exposing a mission/landing goal-contract discrepancy if last position is used.23,717 positions include redundant yaw, matching the separate yaw field. No full-image audit of all100K routes is claimed.

Fresh matched72 corrected-frame direction counts: OpenFly20, Smol25620, Smol50021, Qwen24. OpenFly valid48/72; others72/72. These remain weak results, not flight success. Six-case BF16 CPU-offload reference matches NF4 token vectors/actions6/6 in218s. All three adapter reloads reproduce24/24 old predictions. Gray controls do not establish reliable visual grounding.

Validation: nine tests, ruff, exact input/source audits, preserved original dataset hash, no overlap with all3,000 official evaluation route IDs, all72 debugger cases/288 raw outputs and desktop/mobile checks. No training, AWS, baseline/split edits or protected seeds. All GPU jobs finished.

Evidence: reports/vla_openfly_repair_20260918/REPORT.md, summary.json, full_data_audit.json, aligned_macro_audit.json, all_annotation_audit.json, stop_phase_conflict.json, precision_audit.json and browser_audit.json. UI: localhost8771/openfly_repair.html. Next: use explicit phase/action contracts for data expansion; establish original checkpoint calibration and shared closed-loop semantics before interpreting model ranking.


## 2026-09-19 - D148: investigate original OpenFly training records and complete routes

user challenged weak released-model results and requested paper comparison plus visual routes. Downloaded two bounded original RLDS TRAIN records, verified CRC32C and source/checkpoint statistics, and evaluated native stored inputs. D147 action-coverage repair does not validate a universal decoder: constant horizontal vertical dimensions encode normalized zero; applying vlnv11 yields spurious up=1/down=1. Same campus tokens: source-matched vlnv1 gives12/15 directions,15/15 valid; vlnv11 gives0/15 valid. Added source-statistics guard and regression. Do not silently project invalid vectors or choose calibration by score.

Native packed altitude record:7/19 directions with released raw prompt,10/19 with training prompt/pooling; all valid. Actual future history is hash-confirmed in4/34 steps, but causal replacement changes zero generated tokens. Packed records differ from current annotations in6m-versus3m labels, phase encoding, duplicated STOPs and one instruction. Both versions preserved. Three frozen full dev routes105rawframes/43macrodecisions;274OpenFly and43unchanged Qwen predictions completed. Qwen10/43; horizontal versus vertical decoding radically changes OpenFly validity. Exact profile assignments for those raw routes remain unverified. Paper flight SR is not next-action agreement.

Added recorded-route debugger with exact image triplets, raw tokens, two explicit decoder views, action timelines and one-step pose arrows. Camera is recorded, not model-controlled. Source-profile guard and causal-history tests added; existing baselines, data/splits and all saved adapters preserved. Evidence and final verification: reports/vla_openfly_routes_20260919.

D148 final validation:13 tests,317 actual model outputs,139 debugger frames/360 displayed entries, deep links/playback/mobile and visual review pass. All GPU jobs ended. No baseline, adapter or dataset edits.


## 2026-09-19 - D149: drone-only VLA results and reproduction audit

User corrected the review scope to drone VLAs. Inspected15 aerial learned-action architecture papers,3 supporting aerial benchmarks and1 assisted-navigation boundary case; screened31 candidates. Saved primary-source versions/hashes, result/action/protocol matrix, official resource metadata, exclusions and a bounded reproduction plan. No manipulation-only architecture is counted.

Corrected the current OpenFly literature reference: v7 reports34.3% seen/22.6% unseen flight SR, versus historical v6 citations33.2%/10.7%. Published real-flight SR remains26.09%. Public model repository last update2025-08-29 precedes v7 dated2026-03-01; exact checkpoint-paper correspondence remains unverified. Neither paper result has been reproduced here. Historical D146-D148 records preserved.

Findings: action agreement cannot rank flight capability; action contracts range from primitives/velocity to waypoints and body rates. Some strong scores include planner/sensor assistance or narrow tasks. Source quality/denominator issues and missing releases are explicit. Next: source calibration and expert playback, then source-faithful closed-loop development flights before further training.

Evidence: docs/research/vla_results_audit_20260919/REPORT.md, evidence.json, candidates.json, RESOURCES.md, resource_checks.json and source_manifest.json. Review page: localhost8771/drone_vla_research.html. No GPU inference/training, AWS spend, baseline/weight/split changes or protected-seed use.


## 2026-09-19 - D150: native OpenFly execution and source calibration audit

Implemented a strict codebook-ID-to-pose adapter, AirSim axis conversion and
explicit-termination navigation metrics. Forty upstream transition parity cases
pass. All three frozen dev routes reconstruct correctly after macro start-frame
alignment; original annotation observations deviate by up to6source units. Flagged
Shanghai's unknown donw/0 label without admitting a relabel into training.
Completed20subset/3185entry RLDS inventory and bounded first-record metadata audit;
87,157packed TRAIN episodes,460.44GBreported. Verified vlnv8 quantile clipping makes
UP/DOWN unrecoverable. Prepared original vlnv20/env18 control (40packed steps,
75raw frames), outside our110pilot routes and official eval, with CRC/source-stat
proof and exact raw reconstruction. No new model inference or training.
Six-route recorded reconstruction debugger added at localhost8771/openfly_execution.html;
33tests and452browser checks pass. WSL graphics runtime prepared; user granted HF
scene access and authenticated download is now allowed. Native renderer test is
next, not yet a flight claim. No AWS, protected seed, baseline or split changes.
Evidence: reports/vla_openfly_execution_20260919/REPORT.md and associated JSONs.


## 2026-09-19 - D151: official OpenFly scene downloaded; native renderer gate fails locally

HF grant now works; verified scene installed. Six bounded WSL probes covered
offscreen, virtual display, official SDK/source initialization, requested OpenGL
and alternate clock. Pose stays at spawn (1904.148 m mismatch), camera request
times out; no new model inference/training or valid flight ranking. Vulkan is
software llvmpipe, but exact root cause remains unresolved. Owned processes ended,
original scene settings restored, logs retained. Added launch/probe scripts and
updated viewer status. Ruff/compile/help and targeted browser check pass.
Concrete 2-hour one-L4 Virginia proposal: $0.9776/h official Linux compute,
about $2-3 total expected, $5 proposed cap; approval/connection/AMI preflight pending.
No AWS spend, architecture/split/index/weight changes. See
reports/vla_openfly_renderer_20260919/REPORT.md and status.json.


## 2026-09-20 - D152: blind control on the full aligned 72 panel

User questioned why the released openfly_vla scored no better than our small
adapters. Ran the same72 decisions twice per model, real frames versus every frame
replaced by flat gray, unchanged prompts/checkpoints/greedy decoding. Verified the
harness first: smol256 and openfly_vla reproduced stored D147 predictions exactly,
and all216 frames passed SHA256 checks against the frozen panel.

Real versus gray /72: openfly_vla20->10 (p=0.0213), smol256 20->15 (p=0.4869),
smol500 21->14 (p=0.2478), qwen 24->20 (p=0.5966); always-forward is12/72. Only
openfly_vla depends on the image (right from vision on13 cases versus3). Our
adapters change55-64 of72 answers when blinded with no separable accuracy gain.
The D147 ranking is inverted with respect to grounding, and openfly_vla is further
penalised by24 unparsed outputs (20/48 sighted versus10/38 blind).

Corrected the record: D147's gray control ran on24 openfly: cases sharing only13
(route,frame) pairs with the aligned72, so it was never a same-panel control.
Next-direction agreement must not be used to rank these models. Next: repair the
vlnv11 parse failure, then decide grounding before more training or renderer work.

Viewer: localhost8771/blind_control.html. Evidence:
reports/vla_blind_control_20260920/REPORT.md and summary.json. No training, AWS
spend, or weight/adapter/split/seed changes.


## 2026-09-21 - D153: UAV-Flow endpoint pilot; first model here that uses its camera

D152 left the OpenFly panel unable to rank anything, and the user objected that the
task shape was wrong - the prompt enumerated the answer set, which is not how these
models are used, and D149's own audit shows most drone VLAs emit velocities or
waypoints. Chose UAV-Flow because three papers report on it (WorldVLN 79.12%,
ImagineUAV 70.9%, FLIGHTVLA 59.0%), instructions are single free-form goals and
actions are continuous real-flight trajectories. Downloaded one 4.7GB shard of54.
The dataset declares NO LICENSE; unresolved, and blocking for publication.

Froze 500 episodes,412 train /88 val by episode-id hash, and computed baselines
BEFORE training: predicting a validation endpoint with no image at all gives
5.786m from the global mean and 2.264m from the same-instruction mean. Median
validation trajectory is 7.342m.

SmolVLM-256M + LoRA,400 updates, first frame + instruction -> final displacement:
3.205m with real frames versus 6.466m blinded, and 56 versus 6 distinct answers.
Paired sign tests: better than blinded on 62/83 episodes, p=7.5e-06 - the first
model in this project whose score demonstrably depends on the camera. But it loses
to the trivial text lookup, better on only 30/88, p=0.0037. Not a success.

Three harness defects found and fixed, all in the scorer rather than the model: a
loose parser scraped digits from echoed prompt text and scored a 1049m prediction
instead of a failure; its strict replacement discarded all 88 predictions because
no EOS token was trained and the model emits a fourth number; the manifest builder
pulled a 4.6GB shard into memory to hash a prefix. Reported numbers come from
score_uav_flow_pilot.py re-running the saved adapter, not the training counters.

Next is D154: rebuild as next-step 6-DoF over all ~34k frames, which is both the
faithful shape and the fix for 412 training examples. Plan and the standing
blind-control-plus-baseline rule are in AGENTS.md. Evidence:
reports/uav_flow_pilot_20260921/. No AWS, no OpenFly weight/split/seed changes.


## 2026-09-21 - D155: the model memorises instructions and never lets the image decide

Rebuilt UAV-Flow as 8-step 6-DoF action chunks with a split that shares no episode,
no instruction wording and no site with training (308 train /62 val /130 dropped,
21,665 train steps). Adopted the official OpenVLA-UAV representation: 256 bins per
channel on the vocabulary tail, one token per dimension, q01/q99 normalisation,
LoRA rank32, lr 5e-4.

Text-only baselines recomputed for the new split, since the D153 exact-match
baseline is impossible when no wording repeats: no-text 6.868m, TF-IDF
nearest-neighbour 4.496m, median validation trajectory 10.146m.

Two runs, identical but for LoRA targeting. Run b (text layers only) and run c
(all-linear, which also trains vision_model.encoder and connector, 5.72M extra
parameters). Held-out loss 5.30 versus 5.28; rollout held-out 12.09m versus
13.21m. Unlocking the visual path changed nothing. That hypothesis was wrong.

Rollout endpoints, median, floor first: representation floor 0.06-0.08m, so the
format costs almost nothing. Train episodes 2.86m; held out 12.09-13.21m, worse
than the 6.868m no-text baseline and far worse than 4.496m. The model memorises
instruction-to-trajectory and collapses on unseen wording.

Plumbing checked directly rather than inferred: real and gray images give
different pixel_values and different logits every time (median max difference
0.39), but the argmax action token is identical in 12 of 12 cases. The image
enters the computation and never changes a decision. This is an incentive
problem, not an architecture one - instruction-to-trajectory is a complete
solution on 308 episodes, so nothing pressures the model to see.

Harness work that held up: representation floor as a fourth reference, held-out
loss curve, train-subset rollout as a memorisation check, sign tests keyed by
episode id rather than zip. Three of my own errors were caught by controls, not
by loss curves: free-text actions instead of action tokens, BPE re-merging when
action ids pass through text (177 of 200 chunks corrupted), and the frozen visual
path. Evidence in reports/uav_flow_chunks_20260921/.

Next candidate: run the authors' own OpenVLA-UAV (14.05GB, ungated) on this exact
held-out split with the same rollout and blind control. It answers whether a
properly trained drone VLA clears this bar or hits the same wall. User has
decided the dataset licence question is closed; it is research use.


## 2026-09-21 - D156: the authors' OpenVLA-UAV uses its camera; our fine-tunes do not

Image-swap control, scale-free: same instruction, a different real frame from
another held-out episode. OpenVLA-UAV (D:/drone_vla_pilot/models/openvla-uav,
4-bit, 5.15 GiB, prompt per vla-scripts/openvla_act.py with proprio held fixed)
left its action unchanged on 8/30 cases (gray: 7/30), 21 distinct actions. Our
SmolVLM fine-tune: 48 action tokens unchanged on 23/40 (gray 28/40), median 0
tokens changed. So the camera-blindness is our training, not the papers and not
a gray-image artefact. Needed the D147 predict_action mask fix (token 29871).
Their action space is 4-D (x, y, z, yaw rad), unnorm_key sim, so endpoint scores
are not comparable to ours - only the swap result is. Evidence:
reports/openvla_uav_swap_20260921/summary.json.

## 2026-09-21 - D157: one Qwen3-VL base serves VLM and VLA in llama.cpp; fidelity open

User's real requirement: a VLA co-resident with the testbed VLM (Ollama
qwen3-vl:4b, Q4_K_M, ~4.2 GB) on one 8 GB GPU. Ollama no longer supports LoRA
adapters, so the chosen route is llama.cpp llama-server with a per-request LoRA
scale. Downloaded llama.cpp b11081 CUDA 12.4 Windows binaries and the official
Qwen3VL-4B-Instruct Q4_K_M GGUF + F16 mmproj.

Chain test on a 60-update Qwen3-VL-4B action adapter: PEFT -> GGUF conversion
works (504 tensors, 132 MB); llama-server loads base + mmproj + adapter at 5.5 GB;
the per-request toggle works (scale 1: 100% action tokens, 20/20 full chunks;
scale 0: normal VLM text, 0% action tokens). Numerical fidelity against PyTorch
is not established: token agreement median 50%, chunk gap median 0.116 m versus
0.037 m between-frame spread. Cause not yet isolated between NF4-vs-Q4_K_M and
image preprocessing; next step is a higher-precision llama.cpp base. Evidence:
reports/vla_llamacpp_chain_20260921/. Current state written to AGENTS.md.


## D158 - 2026-09-22 - official UAV-Flow format ported; action-range clipping found

- scripts/prepare_uav_flow_official.py: official OpenVLA-UAV data format (4-D
  drone-frame actions, state in prompt, every frame, first/last x5). 0/500
  mismatches vs the official loop; xy re-integration matches to 5 mm; raw vs
  preprocessed altitude differ (median 0.19 m, max 6.8 m) - inherited by the
  official code. Official trains on `instruction`, D155 used `instruction_unified`.
- train_uav_flow_vla.py: --format official, --instruction, --chunk K (1/8/16).
  scripts/score_uav_flow_official.py: open-loop rollout, floor/real/gray/swap,
  seconds+tokens per call, text baselines recomputed on the same endpoints.
- FINDING: the official q01/q99 action range clips fast motion. Floor endpoint
  error (perfect predictions through clip+256 bins), 62 held-out flights:
  median 0.10 m, p90 4.0 m, max 8.4 m; clipping alone explains all of it.
  24.5% of steps have a clipped channel. Caps: yaw 0.105 rad/step (30 deg/s),
  forward 0.46 m/step (2.3 m/s); max yaw step 3.1 rad. Plausible cause of
  OpenVLA-UAV Rotate 20% SR.
- Planned single-GPU tests (g5, same update budget each): 1) action range
  q01/q99 vs q0.1/q99.9 or max at K=1; 2) horizon K=1/8/16; 3) instruction
  wording official vs both; 4) data 1/5/10 shards.

- D157/D155 shard run SCORED (adapter_s1000, Qwen3-VL-4B bf16, D155 format,
  8-step chunks, no state): held-out median endpoint error 6.474 m on real
  frames - IDENTICAL on gray and on swapped frames (57/55/58 distinct endpoints,
  sign tests p=0.75 / p=1.0). Text-only bar is 4.496 m, no-text 6.868 m, so the
  model is worse than the text baseline and still ignores the camera. Train
  subset 3.199 m, also identical across conditions. Representation floor 0.081 m.
  Conclusion: a 30x longer run on a 16x larger model in full precision did not
  fix camera-blindness -> the cause is the setup (format/prompt/data), which is
  what the official-recipe port (D158) changes. Instance stopped after scoring.
  Known defect: the floor condition failed to parse 52/62 flights (its last
  partial chunk decodes to None); the floor numbers come from the flights whose
  length is a multiple of the chunk. Fix before E0 scoring.

- D159 (2026-09-23): official-format K=1 run on shard 1 (Qwen3-VL-4B bf16, 800
  updates x 32 = 25.6k examples = 1 epoch, lr 5e-4 cosine, loss 16.72 -> 2.96;
  wandb asael/vla training/official_k1_shard1). Mirror probe (20 val flights x 3
  frames = 60 comparisons) per checkpoint: s200 -, s400 3/60 (5%), s600 0/60,
  s800 10/60 (16.7%); sideways sign flipped 1/60; yaw never. Reference: released
  OpenVLA-UAV changed in 16/20 first frames, 6/20 sideways sign flipped.
  Also D159: base Qwen3-VL scores 24/24 on a pasted red rectangle (left/right) at
  512 px, so the probe and the VLM's perception are sound; but it answers the
  "which side is the instruction's target" question the same under mirroring at
  256/512/896 px (flip 2/12 at every size) - resolution is NOT the bottleneck.
  83% of flights name a visual target, so instruction filtering is pointless.

- D160 (2026-09-23): 10-shard run official_k8_10shard (K=8, both wordings,
  mirror, cap 0.1/99.9, 2,500 updates x 32, held-out loss 11.02 -> 2.566) scored
  on 150 unseen-site flights, batched (0.35 s/call vs ~1 s sequential):
  floor 0.072 m | real 3.067 m | gray 3.115 m | swap 3.121 m | text-only NN 4.533 m
  | no-text mean 4.208 m. FIRST adapter to beat both text baselines, by ~1.1 m.
  Camera contribution is ~0.05 m and not significant (gray sign test 70/127
  p=0.29; swap 71/122 p=0.085). Mirror probe: 42/180 changed (23%), sideways
  sign flipped 1/180. So the gain comes from state + instruction, not the image.
  Batched generation verified: left padding correct; batch-vs-single logit noise
  ~0.56 (same with zero padding), flips only near ties. Scorer and preparation
  now batched/threaded. Instance stopped after scoring.

- D161 (2026-09-23): mirror-probe trend across checkpoints of official_k8_10shard
  (60 held-out flights x 3 frames = 180 comparisons, batched): s250 0%, s500 11%,
  s1000 19%, s1500 14%, s2000 12%, s2500 26%. Rising overall but noisy, no sign
  of saturation - weak support for more data/training. (Earlier sequential
  s2500 run gave 23%; batched 26% - the gap is batch-shape noise near ties.)
  probe_mirror_vla.py now takes several --adapter paths, loads the base once and
  batches generation. Instance stopped afterwards.

- D162 (2026-09-24): UAV-Flow-Eval closed loop running LOCALLY on the 4060.
  Simulator: UnrealZoo Collection_WinNoEditor_0424_25.zip (51,216,498,779 bytes,
  ModelScope UnrealZoo/UnrealZoo-UE4, user-approved) downloaded with a
  24-connection resumable range downloader (~23 MB/s; single connection ~1 MB/s),
  extracted to D:/drone_vla_pilot/simulators/Collection_WinNoEditor_0424_25 (49 GB).
  Eval code: D:/drone_vla_pilot/simulators/uav_flow_repo (git clone of
  buaa-colalab/UAV-Flow), venv D:/drone_vla_pilot/venv_uaveval (Python 3.11,
  gym 0.10.9, numpy pinned <2 because their track.py breaks on numpy 2).
  Local changes: DowntownWest.json env_bin_win -> our path; batch_run_act_all.py
  sends `vrun t.MaxFPS $UE_MAX_FPS` (default 10, used 5) after reset, since at
  full frame rate Unreal saturates the GPU and each policy call took 13-40 s
  (now ~1.3 s). Original kept as batch_run_act_all.orig.py.
  Protocol facts: POST /predict {image 224px PNG, proprio [x,y,z cm, yaw deg] in
  the START frame, instr} -> {action: [[x,y,z cm, yaw rad], ...]} poses in the
  start frame; the simulator is in CENTIMETRES (OpenVLA-UAV "sim" action q99 is
  48.7 forward per step), our model is in metres -> x100 / /100 in the server.
  273 test tasks, 10 classes; official metric = nDTW per class (success rate is
  human-judged in the paper). The evaluator ends a task after 100 steps or 10
  near-still steps.
  scripts/uav_flow_eval_server.py serves openvla-uav (NF4, eager, D156 mask fix;
  official server is bf16 + flash-attn) or our qwen adapter (K steps -> K poses).
  scripts/score_uav_flow_sim.py = official nDTW functions + end distance/yaw.
  Smoke: "Turn to the direction of the person" -25.6 vs ref -29.7 deg (good);
  "Rotate 105 degrees to the right" turned the wrong way for 100 steps.
  FULL RUN of OpenVLA-UAV started 10:00 local: flights in
  D:/drone_vla_pilot/runs/sim_eval/openvla_uav/flights, log eval.log.
  OUR MODEL IS BLOCKED: adapter_s2500 exists only on the stopped AWS instance and
  the AWS connector is disconnected; needs the user to reconnect, then start the
  instance just long enough to scp runs/official_k8_10shard/adapter_s2500 and
  the reports/uav_flow_official_10shard manifest (action stats) to D:.

- D162 update (2026-09-24): the local closed-loop run was STOPPED at the user's
  request (it froze the laptop: simulator + 6 GB model on one 8 GB GPU). The
  simulator had also crashed once at task 70 (unrealcv image request timeout).
  69/273 OpenVLA-UAV flights completed, scored in
  D:/drone_vla_pilot/runs/sim_eval/openvla_uav/score_69.json: mean nDTW 0.537 over
  Turn 0.18 (8/15), Move 0.11 (10/15), Shift 0.70 (28/49), Rotate 0.40 (8/15),
  Surround 0.76 (6/12), Ascend/Descend 0.78 (9/19); Approach/Retreat/Pass/Land
  not reached (the task order is alphabetical by timestamp, not by class).
  Partial and class-biased - not a result. The evaluator resumes where it left
  off (skips tasks with plots); scripts in D:/drone_vla_pilot/runs/sim_eval/.
  UnrealZoo also ships a Linux build (Collection_v4_LinuxNoEditor.zip, 45 GB),
  so the evaluation can move to the g5.

- D162 AWS run INVALID (2026-09-24): OpenVLA-UAV 177/273 flights on the Linux
  v4 build (mean nDTW 0.278; Land 0.04, Approach 0.07) and our adapter's first
  12 flights are NOT usable. The first camera frame of every task is the SAME
  image regardless of start pose (contact sheet
  D:/drone_vla_pilot/runs/sim_eval_aws/first_frames_sheet.png): the camera does
  not follow the drone on Collection_v4_LinuxNoEditor, probably tied to the
  camera-count behaviour that forced the base_env.py remove_agent timeout patch.
  Colours are also swapped (orange sky): unrealcv returns BGR and the official
  evaluator passes it straight to PIL.Image.fromarray - check whether the
  Windows build does the same before calling it our bug. Both evaluations were
  stopped; the instance was left running per the user. Next: make the camera
  follow the drone (compare camera ids/poses on Linux vs the Windows build), or
  evaluate on the Windows build on a Windows GPU instance.

- D163 (2026-09-24): closed-loop eval on an AWS WINDOWS GPU box (the supported
  build; Linux v4 camera was frozen). Instance i-03a3c8632314bf5fc, launched
  g5.2xlarge but started as g6.xlarge (no g5 capacity in us-east-1d), Windows
  Server 2022, 250 GB gp3, sg-025131379aa7665f0 (no inbound), IAM role/instance
  profile vla-eval-windows-role (SSM core + read ec2-windows-nvidia-drivers +
  RW s3://vla-eval-artifacts-512068640697, private bucket). Controlled only via
  SSM RunCommand (no RDP/password). NVIDIA GRID 596.86 from the AWS bucket.
  Gotchas: fresh Windows needs UE4PrereqSetup_x64.exe (VC++/DirectX) or
  Collection.exe exits silently; SSM runs in session 0 so the evaluator must
  pass offscreen=True (UAV_EVAL_OFFSCREEN=1 patch); never Start-Process with
  -RedirectStandardOutput from an SSM command (the agent blocks until the child
  exits); ModelScope CDN needs SSL_CERT_FILE=certifi on fresh Windows; the
  qwen venv also needs pydantic+pyyaml (uavlab imports). Driver:
  scripts/win_eval/run_eval.ps1 (stratified 100 tasks = first 10 per class).
  Camera verified: first frames differ per task and show the targets. Colours
  are BGR-as-RGB in the OFFICIAL evaluator too (orange sky) - left as-is.
  RESULT OpenVLA-UAV (bf16, 100 tasks, 5,463 calls): mean nDTW 0.395; Turn 0.18,
  Move 0.12, Shift 0.67, Rotate 0.35, Surround 0.75, Ascend/Descend 0.78,
  Approach 0.39, Retreat 0.29, Pass 0.25, Land 0.17; median end dist 0.61 m.
  Files D:/drone_vla_pilot/runs/sim_eval_win/openvla/{flights,score.json}.
  OUR adapter (qwen k8 10-shard s2500): first attempt INVALID (server died on
  missing pydantic, 0 calls). Rerun launched ~17:10 UTC via C:unsinish.ps1:
  runs qwen, zips both results to s3://vla-eval-artifacts-512068640697/results/
  {openvla,qwen}.zip + run_eval.log, then Stop-Computer (instance STOPS itself).

- D163 update: user asked to shut down before our adapter's rerun finished.
  Windows instance STOPPED ~17:15 UTC mid-run (qwen had 0 completed tasks). Both
  instances stopped. To finish later: start i-03a3c8632314bf5fc (g6.xlarge or
  g5.2xlarge), then via SSM run C:unsinish.ps1 again (it reinstalls deps,
  reruns qwen from scratch, uploads results, and stops the instance itself).

- D163 update 2: user changed their mind ("if it will run and shut down, never
  mind"). Instance restarted 17:45 UTC as g6.xlarge and C:unsinish.ps1
  relaunched: qwen rerun -> results/{openvla,qwen}.zip + run_eval.log to S3 ->
  Stop-Computer. Expected done ~19:30 UTC. Next session: confirm the instance is
  STOPPED, then download and score results/qwen.zip.

- D164 (2026-09-25): OUR adapter (Qwen3-VL-4B bf16, official format K=8, 10
  shards + mirror, s2500) on the same 100 Windows closed-loop tasks: mean nDTW
  0.129 vs OpenVLA-UAV 0.395; theirs better on 77/100 paired flights. Per class
  ours/theirs: Turn .154/.176, Move .044/.121, Shift .106/.675, Rotate .110/.349,
  Surround .001/.753, Ascend/Descend .057/.775, Approach .320/.389,
  Retreat .355/.293, Pass .134/.252, Land .004/.167. Ours ends much earlier
  (median 26 vs 50 steps) and further from the reference end (2.62 vs 0.61 m).
  Only Retreat is better. 404 model calls, run valid. Caveats: ours was trained
  on REAL flights only and tested in SIM (their checkpoint's action stats are the
  "sim" key); our outputs are scaled m->cm by assumption; the evaluator's
  10-near-still-steps rule may end our slower flights early. Results:
  D:/drone_vla_pilot/runs/sim_eval_win/{openvla,qwen}/score.json. Both
  instances confirmed STOPPED.

- D165 (2026-09-25): real + SIMULATOR training run launched (user approved).
  Overlap check first (logs of all 21 UAV-Flow-Sim shards read via HF range
  requests, index D:/drone_vla_pilot/data/uav_flow_sim_index.json): 10,109 sim
  flights; only 1 of 273 test tasks has a sim flight with the same start (<0.5 m)
  AND the same instruction; 54 test tasks have a sim flight starting <0.5 m away;
  238/273 test instructions occur verbatim (templated wording). Excluded every
  sim flight starting <0.5 m from any test start: 168 flights, list
  D:/drone_vla_pilot/data/uav_flow_sim_excluded.json -> 9,941 sim flights kept
  (312k frames, median 25 frames / 5 m). Sim data shares the DowntownWest town
  with the test tasks: report as same-environment, disjoint-trajectory.
  scripts/prepare_uav_flow_sim.py: official maths after cm -> m (x,y,z of raw and
  preprocessed logs /100), all sim to train, appended to the 10-shard store
  (original kept as episodes.real_only.jsonl), action stats NOT recomputed.
  Trainer: --init-adapter (fresh optimiser). Run: from adapter_s2500, K=8, both
  wordings, mirror, bf16, batch 32, lr 2e-4 cosine, 2,000 updates, ckpt every
  500, wandb asael/vla training/official_k8_realsim, out
  ~/runs/official_k8_realsim.
  The user's home IP changed (147.235.193.80 -> 147.236.104.250), so SSH to the
  Linux box is blocked by its SG; instead vla-eval-windows-role was attached to
  it and it is driven by SSM + S3 (no SG change). Pipeline
  scripts/aws/sim_pipeline_d165.sh: hard auto-stop +6 h (04:36 UTC), downloads
  sim, prepares, trains, uploads s3://vla-eval-artifacts-512068640697/d165/
  realsim_adapter.tgz + sim_pipeline.log, then shuts down. NEXT: when the tarball
  is in S3, start the Windows box and run run_eval.ps1 -Models qwen with the new
  adapter (the driver needs its adapter path parameterised), compare with D164.

- D165 training DONE 2026-09-25 02:12 UTC (instance stopped itself): 2,000
  updates from adapter_s2500 on real+sim (1,121,502 train examples incl. mirror),
  lr 2e-4 cosine; train loss 2.23 -> 1.19; held-out (REAL unseen split) 2.565 ->
  2.666 (250) -> 2.582 (2000), i.e. real performance roughly unchanged. Adapter
  s3://vla-eval-artifacts-512068640697/d165/realsim_adapter.tgz, local
  D:/drone_vla_pilot/runs/d165/adapter_s2000. Windows closed-loop eval of it
  launched 07:56 UTC (C:unsealsim.ps1, same 100 tasks, output
  C:uns\qwen_realsim), uploads results/qwen_realsim.zip and stops itself.
