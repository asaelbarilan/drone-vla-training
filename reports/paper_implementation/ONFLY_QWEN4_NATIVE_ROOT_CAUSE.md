# OnFly Qwen3-VL 4B native-dynamics root cause

Date: 2026-08-27. Scope: deterministic local-simulator development seeds only.
Held-out seeds 1-40 were not used.

## What was tested

- Full C5 OnFly inside the shared testbed: Qwen image-point decision, previous
  goal reprojection, RGB-D lift, semantic/geometric verifier, frozen SUPER
  execution, asynchronous forced-choice monitor and hybrid visual memory.
- Compatible backend: Ollama `qwen3-vl:4b`, digest `1343d82ebee3`, Q4_K_M,
  0--999 coordinates decoded to calibrated 224-pixel imagery.
- Native dynamics: 0.6 m/s maximum speed and acceleration, 0.4 rad/s yaw,
  2 Hz decision and 0.5 Hz monitor.
- No scripted policy, detector, semantic mask, target coordinate, goal truth or
  privileged observation entered either run.

## Corrections proven before the gate

1. Native dynamics removed the normalized-profile asynchronous limit cycle:
   waypoint-behind fraction fell from 42.7% to approximately zero.
2. A lossy latest-emphasis contact sheet caused a reproducible false STOP on
   target-free frames. The same frames in chronological multi-image form
   produced LOST, while known near-target frames still produced STOP.
3. Recovery-anchor replacement and current-frame reacquisition are separate
   typed facts. A non-privileged previous-goal reprojection rejects a claimed
   continuous view after the old goal leaves the camera.
4. Monitor evidence sequence, time, position and yaw now come from the exact
   retained visual frame it inspected, not a newer live vehicle pose.
5. Once the fixed reorientation reaches the last-normal yaw, it holds until a
   later monitor verdict confirms reacquisition. It no longer resumes a stale
   waypoint between monitor ticks.

Focused OnFly/router/contract suite: 61 passed. Changed-file Ruff: passed.
Complete repository regression: 345 passed in 479.92 s. The named architecture
configuration validates through `validate-config`; the native environment
validates through the typed `load_environment` path exercised by
`test_onfly_native_profile.py` and the complete regression.

## Predetermined seed outcomes

| Seed | Run | Result | Exact cause |
|---|---|---|---|
| 1061 | `runs/onfly_c5_qwen4_native_seed1061_v7` | timeout, 15.778 m, 0 collisions | target became positionally occluded; offline replay found no target pixels even at the exact goal bearing, so paper-defined yaw-only recovery could not reacquire |
| 1060 | `runs/onfly_c5_qwen4_native_seed1060_v1` | timeout, 25.413 m, 0 collisions | 0/89 target-visible decision frames; Qwen selected near non-target surfaces and 63/89 SUPER plans correctly had no known-free stopping prefix |

The monitor-free C3 diagnostic on seed 1061 entered the 2 m goal region at
77.35 s, showing that the decision/verifier/planner path can navigate under the
paper dynamics. It did not satisfy C5 termination and is not counted as a C5
success.

Two failures make the locked 4/5 gate mathematically impossible. Development
seeds 1062-1064 were therefore not spent on this new profile.

## Backend exclusions

- Qwen3-VL 8B repeats the history/latest temporal error and its full native
  run also times out.
- Qwen3-VL 2B fails latest-frame visibility; Qwen3.5 4B has 14.75--18.9 px
  coordinate error versus approximately 2.6 px for Qwen3-VL 4B and fails
  positive/negative monitor gates.
- MiniCPM-V 4.6 does not emit terminal STOP on the known positive frames.
- Gemma 3 4B previously returned only CONTINUE in failed full episodes.
- Installed Gemma 4 e2b missed all known positive frames; measured calls ranged
  from 2.18 s to 124.34 s.
- Downloaded `cyankiwi/Qwen3-VL-4B-Instruct-AWQ-4bit` revision `b6a6f1c`,
  SHA-256 `687c0db27220e0d956a5a6c67af574c9359d7fcd1df4868426cac84650ff0831`,
  loads but one bounded response took 178.09 s and peaked at 10.56 GiB.

## Scientific conclusion

The current failure is not hidden scripted control or a broken testbed
interface. It is a measured capability/resource failure of all available
compatible backends plus one legitimate limitation of the paper's yaw-only
recovery under positional occlusion. Fixes that would make these two seeds pass
by construction—goal-truth steering, red-pixel detection, returning to a
privileged old position, or weakening SUPER—are explicitly excluded.

Reopen only when a backend passes the frozen coordinate, positive-monitor,
negative-monitor and runtime gates, or when the authors release native
code/checkpoints exposing the shared ViT features and exact monitor cache. The
official repository was checked again on 2026-08-30 and still stated
`Code coming soon`.
