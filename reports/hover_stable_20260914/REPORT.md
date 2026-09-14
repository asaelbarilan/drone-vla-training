# D-110: hover departure repaired in two bounded flights

Both new flights pass the unchanged approach-hover task. Historical failed seed
1062 remains in the comparison. This is repeatability on the same empty scene,
not a generalization result or evidence of broader VLM planning capability.

| Run | Outcome | Stop time | Final distance | Continuous physical hover |
|---|---|---:|---:|---:|
| c5_hover_repeat_20260914_s1062 (old) | timeout, departed | 60 s | 32.941 m | >8 s earlier, then lost |
| c5_hover_stable_20260914_s1062 | pass | 15.2 s | 1.00198 m | 6.1 s |
| c5_hover_stable_20260914_s1060 | pass | 13.2 s | 1.00179 m | 4.1 s |

Both new flights: zero collisions, target contact, or out-of-bounds events. Each has
one retained raw speed violation: 2.0000000000000004 m/s versus the 2 m/s limit,
a 4.44e-16 m/s floating-point excess. We do not rewrite the recorded counters.
The dashboard includes the final control step, so its last camera sample is 0.05 s
after the recorded terminal decision time.

## Repair and causal limits

New named c5_hover_stable_gemma_dev adds three opt-in mechanisms:

- Within 0.25 m of the translation goal, hold the last meaningful approach bearing.
  A tiny changing residual cannot rotate the camera away. Translation and explicit
  direct-action yaw are unchanged; a meaningful new move updates the bearing.
- Measure lateral error from initial odometry and the first RGB-D approach bearing.
  A different selected point on the visible body no longer moves the approach line.
  Range and visibility still use the current confirmed VLM-grounded RGB-D point.
- Count hover intervals only when both endpoint observations satisfy the contract;
  resolve completion against latest observed geometry and matching dwell timestamp
  after inference. Source and live observation IDs are both recorded. Stale source
  geometry cannot authorize a current stop; all original age/range/view/speed gates
  remain. Target jumps still reset or veto dwell conservatively.

Legacy profiles retain original behavior. Simulator target truth, scores and color
recognizers are not supplied to this repair. Task thresholds and environment config
are unchanged. This is our engineering adaptation, not a native-paper OnFly result.

SAVED_PROBE.json reproduces all 1,200 old poses. At source 13.95 s, old geometry
rejects the drifting body-point cross-track, while the fixed line accepts. At 18 s,
with translation speed 0.000019 m/s, old yaw continues -0.4 rad/s away; the new
controller corrects toward the retained approach bearing. These are component
checks on saved states, not an entire counterfactual flight or an isolated ablation
of each fix. Fresh flights validate the combined variant.

Stop is still conservative: seed1062 logs dwell 1.95 s at 11.2, then 1.9 s at 13.2
after evidence renewal, and stops at 15.2. We did not relax the 2 s gate or claim
immediate recognition. Neither new flight loses the target or departs afterward.
The stable approach bearing is still an estimate; accuracy in new geometry is open.

## Evidence and budget

- 442 unit/contract tests pass; 17 targeted tests rerun after the evidence-timestamp
  metadata adjustment. Saved-pose checks and negative evidence tests pass.
- FREEZE.json: all 263 source/config hashes unchanged across the two flights.
- VERIFICATION.json: all 1,770 poses in the three displayed runs match exactly,
  zero missing source frames; captured source-file hashes verified.
- SOURCE_AUDIT.json: all 15 new monitor current-image captures byte-match rendered
  source observations. Policy/monitor requests, replies and sources are preserved.
- Nine browser seeks and three playback checks pass; both terminal images and
  source-image panels inspected. Target remains centered and visible. Browser
  screenshots and CHECKS.json are retained.
- 43 completed local gemma4:e2b calls, two boundary cancellations, zero cloud calls.
  No third new flight, no model reload or model change.

The first launch was rejected before inference by the 16-level configuration
inheritance limit. Flattening one inherited level preserved resolved behavior and
was committed separately before actual flights. The initial browser check got a
404 because Valley now owns port8765; Valley was left untouched. The comparison
server uses port8766 and binds localhost only.

Runtime commits: dc869fa (repair), b1d8a0b (config depth).
Dashboard: http://127.0.0.1:8766/hover_stable.html
Reproduce report without inference using scripts/report_hover_stable.py with the
three run names above, then scripts/check_hover_stable.py and
scripts/verify_hover_stable.py. No further flight is scheduled.
