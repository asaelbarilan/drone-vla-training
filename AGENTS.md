# AGENTS.md — start here

Entry point for an agent picking up this repository. It says where the work
stands, what to do next, and which rules must not be broken. It deliberately
does not restate the evidence: every claim below names the decision that holds
it, in [`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md).

Read [`docs/README.md`](docs/README.md) first for what belongs in which file.
A new decision goes in `RESEARCH_LOG.md` with a new `D-nn`, rationale and
evidence. Corrections never delete the old entry; they mark it superseded.

## What this testbed is

A modular testbed for searching single-UAV foundation-model autonomy
architectures. Architectures are composed from configuration (`configs/`), run
against a deterministic simulator, and charged model latency on a simulated
clock. Seven families are the base; everything else is an ablation.

## Latest: 24 capability flights completed - D-104 (2026-09-12)

Read `reports/capability_screen_20260912/FINDINGS.md` before quoting scores.
One seed 1061 per scenario/architecture: C0 6/8, C1 0/8, C5 0/8. No runtime errors.
C1 text-only Gemma profile has no visual input; known-coordinate arrival succeeds
physically but done is rejected by exact-label completion evidence, then stop is stale.
C5 reaches 0.335 m from visible target, then departs without monitor stop. It also
completes red visit and correct gate crossing. Do not call all timeouts planning failures.
Camera pitch is calibrated; C5 uses existing generic ground monitor, no color guard.
C1/C5 latency is inherited and unmatched. Zero collisions; C5 has constraint violations.
745 completed Gemma calls + 15 boundary cancellations; no cloud or further flights.
All 24 replays match; 72 browser snapshots + 24 playback checks pass.
Dashboard: `reports/debugger/capability_screen.html`. No run active or scheduled.
Next: saved-evidence diagnosis of C1 coordinate completion and C5 arrival/stop;
C1 visual integration remains unresolved. Keep this batch frozen; no automatic sweep.

## Latest: eight capability scenarios implemented — D-103 (2026-09-12)

User authorized one first scenario in each agreed category. See
`docs/CAPABILITY_SCENARIOS.md` and `reports/capability_scenarios_20260912/REPORT.md`.
Eight capability_* environments use the shared simulator with private task scoring;
normal observations have no semantic-hit answers. Ordered visits, branch choice,
closure and sustained tracking are evaluated explicitly. Legacy scoring is unchanged.
Eight scripted geometry fixtures pass with zero collisions, plus C0/SUPER known-goal
integration passes at 5.75 s. These are not real-model capability results.
Dashboard: `reports/debugger/capability_scenarios.html`; C0 has its own linked page.
No inference budget used, no training, no held-out run, no next flight scheduled.
Latest research design is ASP-UAV_Final_Research_Design.pdf (external path in task doc):
nine architecture conditions, eight capability regimes. Old concise PDF is earlier.
D-102 gate repair remains open; no policy behavior was changed in D-103.

## Latest: adaptive-plan flight visually diagnosed — D-102 (2026-09-12)

Read `reports/adaptive_plan_flights_20260912/REPORT.md`; dashboard:
`reports/debugger/adaptive_plan_comparison.html`. New seed-1061 flight timed out
at 90 s, zero collisions, closest/final 23.995 m; stops moving near 23.75 s.
Gate rejects 71/89 proposals from 19 s, only 18 reach SUPER. Model receives failure
feedback but keeps s1: 32 identical center moves, then 57 retains of a rejected point.
Copied historical SUPER finds full known-free paths to the exact rejected goals at
19 and 32 s (641 poses/32 gates/18 plans replay-match). Do not call this physical
execution success or a VLM-only failure. No runtime/config change, second full flight
or further run scheduled. Next targeted change: align acceptance criteria with SUPER,
then separately test explicit rejected/accepted goal state and retain recovery.
User authorized flying and dashboard diagnosis; that bounded work is complete.
One preflight plus 134 completed flight calls, one boundary cancellation; Gemma only.
Do not repeat an unchanged stalled run or tune clearance without a case-specific test.

## Latest: VLM-authored planner implemented; offline checks pass — D-101 (2026-09-12)

Read `reports/adaptive_visual_plan_20260912/REPORT.md` and
`docs/research/vlm_authored_planning_20260912/REPORT.md`. New policy/config:
`adaptive_visual_plan` / `vlm_adaptive_plan_gemma_dev`. VLM authors intermediate
objectives/order/points; explicit retain keeps an anchored world goal. Strict
output parsing, matched routing feedback and model plan/pose history are implemented.
Debugger shows plan, active objective, expected view, memory and original point source.
361 unit/contract tests and lint pass; 8 browser fixture checks pass. No real model
calls or flights yet. Next one bounded saved-frame Gemma/schema check before any
flight; no run scheduled. Use corrected-depth environment and development seeds.
New component-level MapGPT/SPF adaptation, not full paper reproduction or isolated
planning ablation. No supplied graph; forward-camera/backtracking limits remain.
SPF travel and endpoint verifier differ from C5; fixed simulated charge is not wall
latency. Shared SUPER/controller/monitor remain identical, tested. No GT/semantic_hits
in new policy input; no secret reads, cloud retries, model swaps or held-out runs.
D-100 next direction superseded, source audit preserved.

## Latest: drone_control graph audit and comparison specified — D-100 (2026-09-12)

Read `docs/research/drone_control_graph_comparison_20260912/REPORT.md` before the
next architecture implementation. User authorized inspecting drone_control and
defining a comparison, now complete. The older graph path chooses nodes classically;
a separate VLM region menu has optional frontiers OFF by default and unstable IDs.
Do not conflate them or claim their historical success is a matched planning result.
Proposed primary contrast: identical graph/candidates/perception/execution, classical
versus Gemma selector. C5 remains frozen end-to-end context. Next implementation unit:
typed candidate snapshots, stable IDs and a sensor-derived map adapter, displayed in
the debugger and checked offline. Shared target grounding remains an explicit open
gate. Keep SUPER and task fixed, no semantic_hits/truth shortcut, no source arena
constants or full AirSim stack transplant. Design only: no runtime changes, model
calls or flights in this audit; no new flight scheduled. Source hashes and ranges
recorded; drone_control was read-only.

## Latest: two additional corrected-depth flights completed — D-99 (2026-09-12)

User authorized exactly two more flights. Seeds 1060 and 1062 both timed out
at 90 s with zero collisions. Closest/final target distances: 1060 26.24/59.27 m;
1062 21.22/37.46 m. Same corrected-depth environment and guarded Gemma config
as D-98; all 268 completed new calls actually used local gemma4:e2b. No runtime
changes, cloud calls or adaptive tuning. Corrected-depth development total 0/3.
Read `reports/depth_renderer_two_runs_20260912/REPORT.md`; watch the updated
`reports/debugger/depth_fix_comparison.html` (two new flights, prior corrected
1061 and historical legacy 1061). All replays and browser checks pass; exact
requests/responses captured. No run remains active or scheduled. Next inspect
source-aligned decisions around approach/departure: 1060 closest at 24.50 s,
1062 at 39.45 s, prior corrected 1061 at 40 s. Keep the validated sensor repair;
do not infer a full failure cause from aggregate results or silently extend the
run budget. Rebuild comparison with `scripts/report_depth_fix_two_runs.py`.

## Latest: depth fixed; matched Gemma flight still fails — D-98 (2026-09-12)

Implemented `box_ray_v2` per-pixel box depth, validated against 1,146 saved
patch pixels. All 342 unit/contract tests pass. Historical default remains
`legacy_corner` for exact old-run replay. Use `grid_nav_onfly_depth_v2_dev`
for the corrected sensor in this investigation; architecture is unchanged.
One authorized Gemma seed-1061 flight timed out at 90 s: final 30.01 m versus
14.62 m original, closest 14.94 m versus 14.32 m, zero collisions. No navigation
improvement established; no run remains active or scheduled. All 134 completed
calls used local gemma4:e2b, with full debug capture. Read
`reports/depth_renderer_fix_20260912/REPORT.md`; watch
`reports/debugger/depth_fix_comparison.html`. Both trajectories replay exactly.
Next inspect source-aligned decisions around the new 40 s closest approach
and subsequent departure. Do not revert correct geometry merely to recover
an old score, infer model causality from one seed, or start an adaptive sweep.

## Latest: waypoint audit confirms depth defect — D-97 (2026-09-12)

Read `reports/waypoint_handoff_audit_20260912/REPORT.md`; inspect the source
pixel/depth/world-waypoint page at `reports/debugger/waypoint_handoff.html`.
At the disputed decision, box depth is 0.213 m but the selected camera ray
reaches the wall at 1.732 m. The renderer paints one off-screen corner depth
over the entire obstacle. Full replay matches 1,800 controls, 89 plans and 89
source depth images exactly. Selected pixels also lie on a foreground wall;
do not claim the VLM is exonerated. Goals during 32–41 s vary by only 0.116 m,
so large destination replacement is not supported as the cause in that phase.
Next: fix per-pixel sensor depth, preserve the historical renderer for old
replays, and verify the same saved pixels before a bounded flight comparison.
No runtime fix, model calls or new flight in this audit. Camera tests (2),
independent geometric checks, script lint and browser checks pass. No new
verifier or architecture variant is warranted by this result alone.

## Latest: fixed-destination SUPER test succeeds — D-96 (2026-09-12)

One user-authorized continuation from the exact guarded Gemma t=41.60 s state
reached a manual fixed waypoint in 38.10 s, collision-free. SUPER chose a wide
21.83 m detour around the right obstacle with unchanged settings. All 833 prior
controls/positions and all 41 historical plan records match exactly. This is
privileged local-stack evidence, not an autonomous benchmark or a VLM verdict.
Read `reports/super_passage_probe_20260912/REPORT.md` and inspect
`reports/debugger/super_passage_4160.html`. The original active waypoint was
only 0.378 m from the restored drone. Next inspect pixel/depth/world-waypoint
replacement together before choosing a fix. No new verifier, no inference,
no runtime change, no next run scheduled. The design permits named architecture
variants with frozen shared execution/observations, not silent reference changes.

## Latest: user-directed physical passage test — D-95 (2026-09-12)

User requested a manual crossing from guarded Gemma t=41.60 s / observation
833. Two probes restored exact pose, velocity and yaw. Straight at 82.05 degrees
collided after 9.85 s. Aiming 8.04 degrees right at the visible opening cleared
both obstacles in 19.50 s without collision, with 0.213 m sampled body-to-wall
gap. No VLM calls, model changes or runtime navigation fixes. These are
privileged physical diagnostics, never autonomous benchmark results.
Read `reports/passage_probe_20260912/REPORT.md` and watch
`reports/debugger/passage_4160.html` (portable source page also in the report
folder). Planner clearance is configured at 1.8 m; actual inferred occupancy and
route commitment were not reconstructed in these manual probes. Next inspect
that boundary at the user's specific state before choosing any navigation fix.
Do not reduce safety margins or claim a VLM root cause based on this probe.

## Latest: shared visual debugger ready — D-94 (2026-09-11)

User requested visibility before further navigation changes. Open
`reports/debugger/index.html`; guide: `docs/FLIGHT_DEBUGGER.md`.
Three existing seed-1061 flights are loaded: guarded Gemma failure, repaired
Gemma baseline failure and historical Qwen success. All 5,305 positions and
final distances match saved logs; all 396 decision sources match. No inference
or new navigation experiment was run. 335 unit/contract tests and browser checks pass.

Use `uavlab debugger RUN_DIR [RUN_DIR ...]` for zero-inference export; the older
`uavlab replay` command actually reruns inference. Old missing prompts/outputs
are labeled, camera/observer views are reconstructed, and code references are
current checkout unless an actual snapshot was captured. The exporter currently
supports grid3d without injected failures and rejects mismatched trajectories.

For the next separately authorized development run, append `--debug-capture`
with a fresh output directory (or `Orchestrator(..., debug_capture=True)`). It
preserves request prompts/images/schema, returned payload, failures, full paths
and actual code locations. Defaults remain unchanged. First inspect a shared
moment and agree on the observed mismatch; do not start another blind sweep.
Quota blocks, held-out restrictions and shared resident Gemma remain in force.

## Latest: bounded debugging completed — D-87–D-93 (2026-09-11)

Five adaptive Gemma flights on seed 1061 all timed out. No collisions or
premature stops; no variant promoted and active profile unchanged. Budget
exhausted; no run/model call remains scheduled. Read
`docs/research/c5_navigation_audit_20260910/AUTONOMOUS_DEBUG_20260911.md`.
Code/log/evaluation fixes and every result are committed; checkpoint 3147bd4.
D-92 corrects monitor scoring to the source image; earlier activation-frame
accuracies are superseded. Trial 4 has TP=3/FN=6/FP=0/TN=36. Saved-image
checks still miss a clear red target despite describing its rectangle.
Next: establish reliable positive/negative image grounding before another
navigation sweep. Do not promote stricter stopping as solved navigation.
323 unit/contract tests and focused lint pass. Keep Gemma resident, secrets
untouched, provider quota blocks and held-out seed restrictions in force.

## Yaw ablation outcome — D-86 (2026-09-11)

One opt-in Gemma yaw trial failed: false stop 25.20 m from target; target never
visible in replay; closest 24.74 m. Default profile unchanged; do not expand.
308 unit/contract tests pass. No cloud quota used, no run remains active.
Read `docs/research/c5_navigation_audit_20260910/YAW_RESULT_20260911.md`.
Next: inspect the saved false-stop frame and target-consistency logic offline.
Do not treat the verified yaw discrepancy as a demonstrated navigation fix.

## Research audit — D-85 (2026-09-10)

Read `docs/research/c5_navigation_audit_20260910/REPORT.md` before another
navigation change. Review retained 24 primary works from 41 candidates.
Verified discrepancy: OnFly goal-facing yaw versus local path-carrot yaw;
causal contribution remains untested. Repaired Gemma still has grounding error.
C1 receives labeled metric detections, preventing an equal-input planning
comparison. Keep the task and frozen substrate. Next: zero-call visibility,
goal and carrot trace before considering an isolated yaw ablation under a new
implementation decision. No new inference or flights during this review.
Quota blocks and held-out restrictions remain in force.

## Free-provider router — D-84 (2026-09-10)

User requested failover among Gemini, Groq, Mistral and OpenRouter. The opt-in
`c5_free_vlm_router_dev` profile is implemented and mock-tested. It stays on the
working provider, switches on 429/network/5xx, persists quota blocks and never
selects paid OpenRouter IDs. Actual provider/model are logged per call.
306 unit/contract tests pass. This is not yet a validated navigation profile.
Gemini, Groq and OpenRouter key-file paths are configured in ignored .env.
User prohibits inspecting key contents; runtime reads them for authentication only.
OpenRouter is pinned to catalog-verified zero-priced google/gemma-4-26b-a4b-it:free.
The single requested simulation made exactly two provider attempts: Gemini 429,
then OpenRouter 429. Both quota markers persisted, no retries or probes, no movement.
See FREE_ROUTER_SCREEN_20260910.json. No experiment is running.
Groq remains disabled pending free-only billing confirmation; Mistral has no key.
Do not restart quota-blocked routes without fresh authorization. Keep Gemma resident.
Guide: docs/FREE_VLM_ROUTER.md. Navigation remains unresolved.

## Active model decision — 2026-09-07 (D-73)

Use `c5_onfly_active_dev` for active C5 navigation development. Both policy
and monitor use `gemma4:e2b`, including the actual inference backend. This is
a working-model selection, not a passed navigation gate. Keep Gemma fixed
while tracing waypoint proposals through verification, replanning, monitor
interventions and actual movement. Do not infer that VLM quality is ruled out.

The user authorizes sharing the resident Gemma model with the valley experiment.
Do not load Qwen or unload Gemma for routine preparation. Shared-server measured
latency may include contention; isolated latency benchmarks require separate
conditions. Historical profiles/results remain frozen; the old Qwen sweep
stays paused. This section supersedes model-selection and GPU-exclusivity
guidance in the earlier handoff below.

## Navigation investigation — D-74–D-82

The same-weight Gemma runtime repair is installed on the shared `gemma4:e2b`
tag. All 1,411 multimodal tensors are byte-verified; original package backup:
`gemma4:e2b-before-projector-fix-20260907`. Audio remains unevaluated.
Details: `reports/paper_implementation/GEMMA_RUNTIME_REPAIR_20260907.md`.

The repaired target-bound profile finished **0/5** development flights:
three timeouts and two false stops. No collisions. Navigation remains unresolved.
See `GEMMA_RUNTIME_FIXED_TARGET_STOP_GATE_20260907.json`. No gate is running.
Historical profiles keep their original digest pins.

User authorized a free-tier Gemini comparison (D-81/D-82). Gemini passed three
matched image grounding checks, but the first C5 flight hit HTTP 429 after 4 s
and six successful calls. See `GEMINI_C5_QUOTA_SCREEN_20260907.json`.
D-83: user requested a fresh attempt on September 10; the old quota marker
was archived. That run stopped on HTTP 503 after 2 simulated seconds, with
no retry or fallback. See `GEMINI_C5_SCREEN_20260910.json`. Both runs are
interrupted and invalid for navigation conclusions. No run is active.
Gemma remains the local default; keep its shared runner available to valley.
295 unit/contract tests and focused Gemini lint checks pass.

Next: continue diagnosing target grounding and waypoint/control flow locally.
Image-level Gemini improvement does not establish solved navigation. D-79/D-80
record unsuccessful prompt and depth-candidate probes; neither is deployed.

## Latest tested state — 2026-09-07 (D-70–D-72)

- Corrected Qwen target-bound arrival profile: **0/5**, all timeouts, no false
  stops/collisions/parse errors; positive control regressed. Not accepted.
- True Gemma 4 E2B baseline profile: **0/5**, all timeouts, no false stops or
  collisions. Actual policy and monitor model IDs were verified in every log.
- Gemma uses ~1.71 GB GPU at context 8192; measured calls ~0.35 s policy,
  ~0.73 s monitor. Lighter/faster does not establish better navigation.
- Qwen fence-only 90 s screen: **1/3 completed**, no recovery triggers.
  Long-horizon boundary and combined-fix gates were paused for the Gemma
  comparison and remain unvalidated. Nothing new is accepted.
- Output budget for the new six-field monitor must exceed the old 48-token
  cap; D-70 uses 96. The first truncated run is invalid, not a capability result.
- 285 unit/contract tests pass after adding a model-ID mismatch guard.
  See `reports/paper_implementation/GEMMA4_E2B_COMPARISON_20260907.md`.

## Model identity correction — 2026-09-07

D-71 supersedes the D-68 model comparison: all five c5_gemma_dir_s1060–1064
runs actually called qwen3-vl:4b for policy and monitor. Do not cite these as
Gemma evidence or proof that defects reproduce across models. User requested
Gemma 4 E2B comparison; new c5_gemma4_e2b_*_dev profiles set the backend too.
Check actual inference_call.model_id, not just policy/config display names.

## Continuation — 2026-09-07

User approved arrival repair first, then boundary recovery, tested separately.
D-69 records the design. Three new `c5_onfly_*_dev` profiles isolate target-bound
arrival, fence recovery, and their combination; frozen profiles are unchanged.
Initial CPU regressions passed; the later real-model results are summarized
above. Do not label the new profiles accepted.
Details and commands: `reports/paper_implementation/C5_ARRIVAL_FENCE_FIXES_20260907.md`.
The earlier geofence diagnosis explains terminal deadlock in long runs, not
necessarily the original 90 s navigation failures. Steering entropy measures
variation, not steering correctness. Target-bound depth does not guarantee
semantic identity; validate false stops in exact replay.

## Earlier handoff — 2026-09-04

The harness works and catches its own defects. **C5 OnFly is the live front**,
and this week's work located its failure precisely.

Current five-seed development result on `grid_nav_onfly_native_long`
(240 s horizon, seeds 1060-1064):

| configuration | success |
| --- | ---: |
| `c0` classical planner, knows the goal | **5/5**, 63-84 s |
| C5 + Qwen3-VL 4B, pixel output | 1/5 |
| C5 + Qwen3-VL 4B, pixel output, told the winning route | 0/5 |
| C5 + Qwen3-VL 4B, five-word steering output, told the route | 0/5 |
| C5 + Gemma 3 4B, five-word steering output | 0/5 |

Five candidate causes have each been separately excluded by measurement:

- **Path budget** — raising the horizon 90 s to 240 s changed no outcome; the
  failures used 78-90 m of a 144 m budget (D-64).
- **Step source** — the vehicle realises under 10% of any commanded step before
  replanning, so waypoint distance barely reaches it (D-62).
- **Search and viewpoint choice** — the target is dead ahead at 35 m on every
  seed; there is nothing to search for (D-64).
- **Not knowing the route** — handed `c0`'s winning path in words, C5 does
  *worse*, 0/5 against 1/5 (D-66).
- **Output representation** — a five-word steering vocabulary scores 0/5 too,
  and the model simply repeats one word instead of one pixel (D-67).

What is left are **two model-independent defects**, both reproduced under two
different VLMs:

1. **Geofence deadlock.** The vehicle reaches ~55 m of the 60 m fence, every
   subsequent proposal lands outside it and is correctly refused, and nothing
   turns it around. It then holds position until the horizon expires. On the
   failing seeds 100% of verifier calls during the freeze are geofence refusals;
   the one success has zero across the whole episode (D-65, D-68).
2. **Acquisition latch false stops.** The monitor declares arrival at 8.5 m,
   14.2 m and 32.9 m from a 2 m goal radius, reporting
   `latest_scale=large, acquisition_count=2/2` — on seed 1060 while the vehicle
   had moved barely 2 m from its start (D-67, D-68).

A third finding is real but **not** currently binding: Qwen3-VL 4B does not
steer. Mean normalised entropy over the five-word vocabulary is 0.21 against
Gemma's 0.60, with no overlap between the two sets, and Qwen never selected
`hard_left` or `hard_right` in 925 decisions. Gemma steers three times better
and still scores 0/5, so fixing steering alone would not have changed a single
outcome (D-68).

## What to do next, in order

1. **Fix the geofence deadlock.** It blocks four of five seeds under both
   models. The fix is a fallback when every proposal is refused for the fence —
   an architecture decision, so record it as a `D-nn` before implementing.
   Success criterion: no episode ends frozen with 100% geofence refusals.
2. **Fix the acquisition latch.** Four false stops so far. A stop declared at
   32.9 m with `latest_scale=large` means the scale evidence is not constraining
   anything. Success criterion: no `agent_stopped` outside the goal radius.
3. **Re-run the five-seed gate** on `grid_nav_onfly_native_dynamics` (the frozen
   90 s profile) after 1 and 2, and compare against
   `reports/paper_implementation/C5_RETAINED_FIVE_SEED_RESULTS_20260901.md`.
4. **Only then** revisit steering and model choice.

Everything else open is in [`TODO.md`](TODO.md), ordered by what it blocks.

## Rules that must not be broken

- **Held-out seeds 1-40 are never trained on and never tuned against.**
  Development uses 1060-1064; training collection uses 1000+. This is enforced
  in `src/uavlab/training/splits.py` — do not work around it.
- **Do not hide the remaining search boundary** with colour detection,
  simulator truth, scripted target search, or a weaker SUPER substrate. This is
  the standing instruction that makes the negative results meaningful.
- **Privileged diagnostics are never reportable.** Configs tagged
  `privileged_diagnostic` (`c5_route_hint_s*`, `c5_route_direction_s*`) feed the
  model a route derived from `c0`'s successful trajectory, i.e. simulator truth.
  They answer "can the agent execute a route it is told?" and nothing else.
  Their numbers must not appear in any results table.
- **One seed is not a result.** Three readings this week were reversed by later
  seeds, and in each case the misleading seed was the one that ended early with
  few decisions. Check the sample size before concluding.
- **Verify a contract experiment distributionally.** The direction contract's
  original acceptance criterion asked whether bearings spread beyond +-10
  degrees, which a model emitting one fixed word passes. Use entropy or modal
  share (D-67).

## Running things

```bash
export PYTHONPATH=src
python -m uavlab.cli run --arch c5_onfly_active_dev \
  --env grid_nav_onfly_native_long --seed 1060 --out runs/probe
python -m uavlab.cli verify c5          # does the architecture function
python -m pytest tests -q               # full suite, ~10 min
```

Two tests are sensitive to machine load rather than broken —
`tests/integration/test_verify.py::[c1]` (drives real `gpt-oss:20b`) and
`tests/smoke/test_all_architectures.py::test_the_core_runtime_imports_no_heavy_dependency`.
Both pass in isolation; run the suite on an idle machine before believing a red
result (D-63).

For resource diagnostics, inspect GPU usage. D-73 permits the valley experiment
to share the same resident Gemma model; GPU exclusivity is not a prerequisite:

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

## Commit state

As of D-93, all implementation/configuration changes and session outcomes are
committed. Historical scratch scripts/logs remain untracked; credentials are
ignored and were not staged. See CHANGES.md and git log for rollback points.
