# C5 seed 1060 — discrete-direction output contract

Date: 2026-09-02. Development seed only; frozen C5 untouched. Seeds 1–40 not used.

## Hypothesis

The pixel channel is saturated at the image centre
(`C5_S1060_VISUAL_ERROR_ANALYSIS_20260902.md`). Replace the `(u,v)` goal with a
five-word steering vocabulary — `hard_left`/`left`/`ahead`/`right`/`hard_right`,
mapped to ±38°/±20°/0° through the camera's own focal length — and see whether
the model then commits to a direction.

Only the output representation changed. The word is converted to an image point
inside the decision agent, so range gating, waypoint construction, verifier and
monitor are untouched. Acceptance was declared in advance as **bearing spread
beyond ±10°**, not mission success.

## Results

| | Qwen3-VL 4B, pixels | Qwen3-VL 4B, directions | Gemma 3 4B, directions |
|---|---|---|---|
| decisions | 59 | 25 (run truncated) | 89 |
| median commanded turn | 7.8° | 0.0° | **20.1°** |
| mean absolute turn | 9.9° | 9.7° | **14.4°** |
| within ±10° of straight ahead | 59% | 52% | **29%** |
| vocabulary used | — | ahead 13, right 8, left 4 | right 46, ahead 26, left 16, hard_right 1 |
| final distance | 32.19 m | — | 27.96 m |
| collisions | 0 | 0 | 0 |

**Qwen3-VL 4B fails the criterion on both representations.** Changing the output
contract moved its mean commanded turn from 9.9° to 9.7°, and it never once
selected `hard_left` or `hard_right`. Every Qwen response also arrived on
Ollama's `thinking` channel despite `think:false`, which is a known open issue
for this backend and a confound worth stating.

**Gemma 3 4B passes the criterion.** Median commanded turn 20.1°, only 29% of
decisions near straight ahead, and it used four of the five words. So the
saturation was real and is partly a property of the model rather than of the
schema.

## But the mission still fails, and Gemma adds a new failure mode

Final distance 27.96 m against the 32.19 m baseline — closer, still a timeout,
still zero collisions.

More important: at **t=5.2 s Gemma reported the red tower visible at "large"
scale and requested a STOP while the true goal was 33.1 m away.** The
synchronized-depth gate vetoed it (7.0 m measured against the 3.0 m stop
threshold), which is the gate working exactly as intended. But `ever_acquired`
latched to true at t=7.2 s and the monitor then returned `lost` on 41 of its 45
checks for the rest of the episode — the architecture spent the flight
re-acquiring something that was never there.

So this is **not** the first acquisition on seed 1060. It is a false positive
that the harness caught. Reporting it as progress would have been wrong.

## What this establishes

1. Output-representation saturation is real, and it is model-dependent: at 4B,
   Qwen3-VL will not commit to a direction in either representation.
2. Steering was **not** the binding constraint. Removing it did not find the
   target.
3. Gemma 3 4B trades saturation for false acquisition at 33 m, which the depth
   gate rejects but the monitor's latch does not.

The remaining boundary is unchanged and is the one named in the failure
analysis: the target sits behind an obstacle wall, and nothing in OnFly's
mechanism chooses a viewpoint for what it would reveal.

## Configurations

- `configs/architectures/c5_onfly_qwen4_direction_dev.yaml`
- `configs/architectures/c5_onfly_gemma4b_direction_dev.yaml`
- runs: `runs/c5_s1060_direction_v1`, `runs/c5_s1060_gemma_direction_v1`

## Addendum — the `ever_acquired` latch is not a bug

The phantom acquisition above looked like a latch defect: a depth-vetoed STOP
still counted toward acquisition because `reject_depth_vetoed_acquisition`
defaults to `False`. Flipping that default to `True` was tried and **reverted**.

It is wrong on the premise. `stop_max_depth_m` is a *stopping* threshold, not a
validity threshold. A target genuinely visible at 7 m with a 3 m stop radius
produces exactly the same reading as the seed-1060 phantom — visible, "large",
sampled depth 7.0 m — so the comparison cannot separate them. Defaulting the veto
on would refuse every honest acquisition made before arrival.

Two independent confirmations:

* `test_monitor_accepts_current_visibility_when_previous_goal_left_the_frame`
  encodes precisely the legitimate case and fails when the default is flipped.
* Rerunning seed 1060 with the veto on ended at **55.12 m**, against 27.96 m
  with it off. The change made the failure worse.

Distinguishing a phantom from a distant true sighting needs evidence the harness
does not have without privileged truth. Recorded as open rather than papered
over, and the rationale is now a comment at the decision site so the same
apparently-obvious fix is not attempted a third time.

The depth gate itself is working: it vetoed the stop at 33.1 m, which is the
safety-critical half and the reason no premature stop occurred.
