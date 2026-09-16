# D-122: the exact flight continuation succeeds

The drone enters the 2 m arrival radius at **94.5 s**, and the monitor declares
STOP at **97.2 s**. Final distance is **0.9363 m**, with **zero collisions**.
The task's declared arrival-plus-terminal-STOP criterion passes. Only **7.2 extra
simulated seconds** were needed after the original 90-second timeout.

No navigation, perception, planner, target-commitment or stopping rule changed.
The original failed run remains unchanged; this success belongs to the separately
recorded continuation with a 120-second maximum budget. It does not demonstrate
that the architecture reliably succeeds across seeds, or that target commitment
caused all improvement over the older baselines.

## Reconstructing the same flight

Source: `c5_target_commitment_20260915_s1061`.
Continuation: `c5_commitment_continued_20260916_s1061`.
Profile: `c5_target_commitment_qwen4_dev`; development seed 1061.
Harness/freeze commit: `2bff8a7`.

The unchanged runtime was re-executed from the start using 134 saved responses.
Every request's prompt, schema, model, observation sequence, timing and PNG bytes
was checked. The 135th original request had been cancelled at the old horizon;
its identical 89-second request was reissued locally and first became available
at 90 s. All subsequent requests used new observations and fresh local inference.
No vehicle pose, memory snapshot or planner state was manually substituted.

Both the offline dry replay and live continuation match all original 1,800 control
commands, 89 plans, 90 memory updates, 45 monitor events and 58 verifier events.
Comparisons exclude regenerated decision IDs and debug source locations, while
preserving source observation sequences, ages, deadlines and control values.
Dry-replay final distance matches exactly. The exported replay additionally matches
original positions, velocities, headings and distances through 90 s. Eight harness
tests pass, including rejection of changed images, prompts, models, times and schemas.

## Arrival and stopping evidence

| Event | Recorded observation |
|---|---|
| Original horizon, 90 s | 4.6466 m from target, still approaching |
| First arrival-radius entry, 94.5 s | Within the unchanged 2 m criterion |
| Monitor available at 95.2 s | Continues: its source target range is 2.3076 m |
| Monitor available at 97.2 s | STOP: source target range 1.1437 m; four visual confirmations; live arrival recheck passes |
| Final environment sample, 97.25 s | 0.9363 m from target; speed 0.05176 m/s; target visible |

The 0.05-second difference between the runtime termination timestamp and final
camera timestamp is the final physics step. It is retained in the evidence.
The vehicle is moving slowly at termination, not mathematically stationary.
The task checks terminal STOP inside the radius; it does not require a sustained
settled hover, which this experiment does not establish.

The VLM identifies and points at the red tower in the current image. The existing
monitor combines that identity evidence with its metric arrival gate and confirmations
to declare STOP. This is not evidence that the VLM independently estimated metric
arrival distance or authored a global obstacle-avoiding route.

## Validation and compute

- 1,945 replay positions and 97 actual policy images match; all 49 monitor images
  also match the corresponding audited source images byte-for-byte.
- Ten browser timeline seeks, two playback checks, and terminal-monitor selection
  pass without JavaScript errors. Actual final map, observer view, drone camera and
  the saved image supplied to the stopping monitor were inspected.
- Minimum obstacle distance 1.5641 m; no collisions or out-of-bounds events.
  Raw 503 speed-limit violations remain recorded; maximum excess is 2.22e-16 m/s,
  floating-point roundoff, independently measured by the source audit.
- 13 fresh local inference attempts: 12 completed (8 policy, 4 monitor), one cancelled
  at termination. The 134 cached prefix responses are not new model calls.
- Qwen3-VL4B retained digest, CPU-only dedicated 11435; start/end residency confirms
  zero VRAM. Median measured latency of fresh completed calls is 25.633 s.
  Whole reconstruction plus continuation took 332.72 wall seconds. Simulated charges
  remain policy 1.0 s / monitor 1.2 s, so this is not real-time CPU flight evidence.
- Aggregate inference latency in the raw result includes cached responses and is
  not a valid model-speed comparison; the dashboard banner makes this distinction.
- Dedicated inference unloaded/stopped after the run. Debugger 8766 remains available;
  shared 11434 and Valley were not modified. No cloud calls, downloads or automation restart.

Raw calls/images/source snapshots, manifest, result and compressed events are retained.
See `FREEZE.json`, `DRY_REPLAY.json`, `LIVE_REPLAY.json`, `AUDIT.json`,
`MONITOR_IMAGE_AUDIT.json` and `browser/TERMINAL_MONITOR.json`.

## What is next

This closes the question of whether this particular approach can finish with more
time. Next, compare target commitment enabled versus disabled with identical model,
hardware placement, task budget and seed schedule. Keep arrival/STOP checks unchanged
and report all outcomes; repeated trials are needed before a reliability claim.
The original 90-second result stays a failure. D-121 remains a named architecture
extension, not a repair retroactively attributed to native OnFly.

[Watch the continuation from 90 s](http://127.0.0.1:8766/commitment_continuation.html#run=c5_commitment_continued_20260916_s1061&t=90).
