# C5 target arrival and boundary recovery — 2026-09-07

Status: arrival-only gate rejected (0/5); fence-only gate partial. See the
real-model continuation below and GEMMA4_E2B_COMPARISON_20260907.md.
Decision: D-69. No frozen architecture or environment configuration was edited.

## Separate experiments

| Profile | Target-bound arrival | Boundary recovery |
| --- | --- | --- |
| c5_onfly_qwen4_native_dynamics | original | original |
| c5_onfly_target_stop_dev | enabled | original |
| c5_onfly_fence_dev | original | enabled |
| c5_onfly_stop_fence_dev | enabled | enabled |

The new arrival monitor requests a target pixel in normalized 0-999 coordinates
in the current full-resolution RGB image. It snapshots the matching depth map
before inference, reads uncapped depth at that pixel, lifts using calibrated
intrinsics/odometry, and measures Euclidean range. It requires two STOPs on
fresh observation sequences, within both the configured 2 m limit and the
mission radius, with target world points agreeing within 1 m. Missing,
malformed, distant, or inconsistent evidence cannot confirm arrival. Distant
visibility can still acquire the target; arrival and acquisition remain separate.
Navigation waypoint depth is not used by this experiment.

The independent boundary experiment responds to three consecutive typed
geofence refusals. It cancels translation and turns toward the declared fence
interior, at 0.4 rad/s with a turn-angle-derived deadline. On completion or
timeout it requires a new observation; old/in-flight proposals cannot restore
outward motion. Visual CONTINUE does not cancel the boundary turn. Every
trigger is logged and counted in router_fence_recoveries. Other refusal kinds
reset the streak. The existing verifier, planner and shield remain in place.

## Limits

These are declared extensions, not claims about native OnFly. A consistently
misidentified object can still defeat semantic confirmation. Surface depth is
not guaranteed to equal distance to an object's scoring reference point.
Repeated fresh frames are not independent semantic witnesses. These limits
must be checked in real-model evaluation; CPU tests do not establish mission
success. The 109-151 s deadlocks in long runs do not by themselves explain all
90 s failures. Neither geofence escape nor fewer STOPs is an acceptance result.

## Validation and pending flights

Unit/contract regression: 281 passed, including 23 new arrival/fence tests.
Shared-runtime acceptance/injection integration: 31 passed in 150.70 s.
The all-architecture termination test was deselected because it loads real C1
inference. Total completed validation: 312 tests passed.
Ruff on changed files passes with existing RUF005/RUF046 findings excluded.
No new real-model development or held-out evaluation has been run. Unreal
Engine was using the GPU; its closure was requested without terminating it.

Run one profile at a time, seeds 1061, 1060, 1062, 1063, 1064 (positive control
first), with unique output directories. Example from the repository root:

```powershell
$env:PYTHONPATH = 'src'
python -m uavlab.cli run --arch c5_onfly_target_stop_dev --env grid_nav_onfly_native_dynamics --seed 1061 --out runs/c5_target_stop_20260907_s1061
```

First evaluate arrival-only on the frozen 90 s environment, then fence-only
on that environment and grid_nav_onfly_native_long. Evaluate the combined
profile after the separate results. Preserve all outcomes, including failed
positive controls; do not tune against held-out seeds 1-40. Compare success,
false stops, collisions, inference/parse errors, final distance and boundary
recovery events against the frozen baseline. Replay false-stop events to audit
whether the grounded pixel belongs to the requested object.

## Requested test rerun — 2026-09-07

Command: `python -m pytest tests -q -k 'not c1 and not an_episode_always_terminates_with_a_reason and not all_architectures_can_run and not core_runtime_imports_no_heavy_dependency'`

Result: **380 passed, 20 deselected, 1 warning**, 239.95 s. The warning is
an external dateutil utcfromtimestamp deprecation. The conservative `not c1`
filter also excludes names containing c10-c14; this is not a full-suite pass.
GPU-dependent runs were not started: preflight measured 6592/8188 MiB in use,
with UE4Editor and other model servers running. User was asked to free the GPU;
no other workload was stopped or unloaded. Five-seed VLM flights remain pending.

## Real-model continuation and model comparison

The first arrival flight was invalid: its inherited 48-token output budget
truncated the new six-field JSON. The exact request completed in 53 tokens
with a 96-token cap. D-70 records the correction and preserves the invalid run.

The corrected Qwen arrival-only gate finished **0/5**: no collisions, premature
stops or parse errors, but all episodes timed out, including the formerly
successful seed 1061. Do not accept this as an improvement. Fence-only 90 s
runs completed on 1061/1060/1062: success/timeout/timeout, with no fence recovery
triggered in any of them. This remains a partial gate. The remaining Qwen queue
was paused following the user's request to consider Gemma 4 E2B. Boundary-long
and combined gates have not been run.

D-71 also corrects a historical mislabelling: all five c5_gemma_dir_s* runs
called Qwen, despite a Gemma policy label. These are not Gemma evidence.
A genuine Gemma 4 E2B comparison is now underway with policy, monitor and backend
IDs aligned and every saved inference model ID checked. New backend validation
rejects mismatched request and backend model IDs before the HTTP call.
