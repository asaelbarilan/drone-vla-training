# D-121 cycle 3: detour and approach, still a timeout

The named target-commitment variant clears the obstacle, reacquires the red tower,
and approaches it. It does **not** complete the mission: at the unchanged 90-second
limit it is 4.647 m away, outside the 2 m arrival radius, still moving at 0.597 m/s.
No STOP was emitted. More time might help, but arrival and stopping are untested.

## Frozen run and comparison

Run: `c5_target_commitment_20260915_s1061`; profile:
`c5_target_commitment_qwen4_dev`; environment:
`grid_nav_onfly_depth_v2_dev`; development seed 1061. Runtime change commit
`3fd30c8`; captured run HEAD `c9eb68f` with dirty status. Runtime source snapshots
are archived; later viewer/audit changes do not modify the recorded flight.

| Variant | Closest distance | Final distance | Outcome | Collisions |
|---|---:|---:|---|---:|
| D-115 baseline | 13.746 m | 29.295 m | timeout | 0 |
| D-116 fresh-image handoff | 13.401 m | 29.939 m | timeout | 0 |
| D-117 observed-view return | 14.930 m | 17.007 m | timeout | 0 |
| D-121 target commitment | 4.647 m | 4.647 m | timeout | 0 |

This is **not an isolated causal comparison**. The last flight used dedicated
CPU-only inference to avoid interfering with Valley. Initial prompt, schema and
image bytes match D-115, but its first model point differs; controls diverge at
1 s, before the first commitment at 13 s. CPU/GPU placement and ordinary model
nondeterminism have not been separated. One development seed cannot establish
reliability or justify promoting this extension into the native paper baseline.

## What the mechanism actually did

The VLM still supplies target goals; common SUPER plans their local execution.
The extension retains an accepted target goal for at most 20 s through an
occlusion, while preserving the original image timestamp and allowing a fresh
verified target to supersede it. It defers exploration replacement and LOST yaw
only while that bounded execution owns motion. No target truth enters control.

Five leases activate at 13, 41, 51, 53 and 59 s. There are 31 deferred exploration
proposals, 599 lease-authorized control commands, and 13 deferred LOST yaw events.
419 commands use original evidence older than the ordinary 4-second limit;
maximum actual source age is 18 s. All retain the original source ID/sequence/time
and stay inside a nonrenewing deadline. The lease audit reports zero violations.
These are explicit authorized old-source commands, not fresh observations; the
separate lease counter must accompany the ordinary stale-action-rate metric.

The longest retained-goal replans run from 59 through 74 s, despite temporary
absence in the camera. Actual sampled RGB at 60 s has no visible red tower; at
74 s red is visible again on the left of the obstacle. At 75 s a fresh current
image target proposal takes over. All 15 policy proposals available at 75–89 s
point on red pixels in their actual saved inputs. Distance decreases on every
replay tick from 75 to 90 s: 13.367 → 10.587 → 7.611 → 4.647 m at 75/80/85/90 s.
The final camera and map show approach, not a stopped vehicle wedged at a wall.

Ordinary LOST recovery still occurs at 45.2 s outside active ownership. All
observed leases end before their deadlines: deadline expiry/failure behavior is
covered by unit tests, not demonstrated by this flight. No claim of tested
successful terminal stopping follows from a run that never enters arrival range.

## Validation and resources

All 1,800 replay poses and 89 actual policy images match. Browser review passes
66 timeline seeks and two playbacks, plus seven final-approach captures, without
JavaScript errors. Actual camera sequences and the map/observer view were inspected.
`FINISH_REVIEW.json` contains dense final distance samples and actual source pixels.
`COMMITMENT_AUDIT.json` records lease ownership, ages, deadlines and prefix mismatch.
Raw calls/images/source snapshots, manifest, result and compressed events retained.

Minimum obstacle distance 1.564 m; zero collisions or out-of-bounds events.
The raw 476 speed-limit violations are retained in the result: their maximum
excess is 2.22e-16 m/s (floating-point roundoff), as independently checked by AUDIT.

134 completed local requests (89 policy / 45 monitor), one boundary cancellation,
zero model or parse errors. Wall duration 2,596.22 s / 43.27 min. Median measured
inference latency 25.844 s. Simulation charges remain fixed at policy 1.0 s and
monitor 1.2 s, so this is not a demonstration of real-time CPU flight capability.
Qwen3-VL 4B digest and size_vram=0 are recorded at start/end. Dedicated 11435 was
unloaded and stopped after the flight; shared 11434 and Valley were not modified.
Preflight validation: 420 full-suite tests plus 20 focused commitment tests pass;
the focused set includes the subsequently added orchestrator integration test.

## Next discriminating test

First validate an exact cached replay of this 90-second execution, including
requests, memory, router ownership and controls. Then a separately frozen bounded
continuation can test whether it arrives and stops with more time, using fresh
inference only after the checkpoint. Keep this 90-second failure unchanged and
report the continuation as a time-budget diagnostic, not a benchmark success.
For causal architecture comparison, use matched inference placement and repeated
seeds, with the same frozen task budget. Do not infer causality from this table.

No fourth flight was launched: another full CPU trial takes about 43 minutes,
more than the remaining autonomous window. The checkpoint continuation needs its
own validated harness; it was not rushed or counted as an executed experiment.

Dashboard: [flight replay](http://127.0.0.1:8766/recovery_cycle3.html#run=c5_target_commitment_20260915_s1061&t=74).
