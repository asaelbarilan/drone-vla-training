## What this screen actually establishes

All 24 requested episodes completed: C0 6/8, C1 0/8, C5 0/8 under the full task criteria.
All 16 model-backed episodes timed out at 60 simulated seconds. No runtime errors.
This is a compatibility screen on one development seed, not an architecture ranking.

- **C0**: reaches the privileged final goal in every scenario. The ordered-visit run
  skips red and stops at blue (0 required subgoals); the follower approaches too
  closely and stops. These expose missing task semantics in the current oracle
  policy, not failure of SUPER to execute a reachable goal.
- **C1 known coordinate**: the model dispatches goto(12,0,3), the runtime confirms
  arrival within 0.08 m, and the model requests done. The protocol rejects done
  twice because its exact-label completion evidence is absent. The next stop
  proposal is stale after the three-attempt cycle (25.55 s > 20 s). Final position
  is the instructed coordinate (numerical error < 1e-12 m), but no accepted terminal
  stop occurs. This is direct input/termination-contract evidence, not an inability
  to plan a flight to a coordinate. See copied calls and browser screenshot.
- **C1 visual tasks**: all 40 recorded requests have zero images; no semantic hits
  are supplied. Six runs have zero translational path length. A visual model-quality
  conclusion is invalid for these cells. Camera integration was queried, not implemented.
- **C5 visible target**: reaches 0.335 m at 13.05 s, then departs; final 29.68 m.
  Known coordinate reaches 0.731 m at 9.15 s. Neither produces a monitor stop.
  The precise stop/grounding cause still needs a saved-frame investigation.
- **C5 partial task progress**: correct gate crossing is recorded; the ordered task
  completes the red visit, but never finishes the blue visit/stop. Tracking satisfies
  the distance/view criterion for 5.9 of 15 s (required 13.5 s). These are partial
  successes hidden by the binary episode result, not evidence of general incapacity.
- **Safety**: zero collisions across 24 runs. C5 records 14 constraint violations
  across six runs; C0 and C1 record zero. Inspect the source events before assigning
  a specific physical mechanism to the aggregate constraint count.

## Budget and verification

745 completed real local Gemma calls: 712 C5 + 33 C1, plus 15 cancelled requests at
termination (8 C5 + 7 C1). C0's 564 captured zero-token events are simulated detector/
oracle activity, not foundation-model calls. No cloud calls, model swaps, held-out
seeds, automatic fixes, repeated episodes or additional trial flights.

All 24 flight trajectories replay-match, with no missing decision source frames.
Actual Edge browser checks pass: 72 timeline snapshots and 24 playback checks,
no page errors. Selected C0, C1 and C5 screenshots were inspected directly.

## Next diagnostic step (not yet executed)

Separate two bounded repairs before judging planning: (1) public-coordinate completion
in C1, independent of a visual label; (2) C5 stop/grounding at the saved visible-target
approach (roughly 8-13 s), checking the exact monitor image, projected depth and gating.
Decide the visual perception contract for C1 separately. Keep this batch frozen;
any repair and repeat must be explicitly labeled as a new profile and new evidence.
