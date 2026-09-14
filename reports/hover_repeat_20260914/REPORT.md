# D-109 — two frozen hover repetitions, one pass and one failure

User requested exactly two more flights. Seed 1060 passes at 11.2 s, 1.00269 m,
2.1 s hover; seed 1062 times out at 60 s, final 32.9411 m. Both use unchanged
c5_hover_level_gemma_dev and capability_approach_hover. No third flight or runtime fix.
231 source/config hashes remain frozen; resolved configs match historical success.
Same geometry across seeds: this is repeatability, not independent scene coverage.
Including the prior success gives 2/3, but the repaired behavior is not reliable.

## Why the second departed

Exact controls and source RGB were replayed, with no model invocation. Initial policy
outputs and physical trajectory match the passing repeat through 11.2 s. At 11.2 s
both are approximately (10.9976,0.0179,3.0), 1.003 m from the marker, nearly stationary.
The failed monitor reports 1.95 s dwell whereas the successful one reports 2.00 s.
Small differences in earlier monitor pixel outputs change onboard dwell eligibility.
This misses the first stop opportunity; the evaluator already has 2.05 s pre-step.
Do not attribute this difference to random scene geometry or a proven scheduler race.

Physical hover continues: evaluator records 8.85 s at 18.0 s. Thus the preliminary
"did not complete hover" description is corrected: it did hover successfully but
failed to declare completion before leaving. Its final hover metric is zero because
that metric is the current continuous streak, not the maximum achieved streak.

The controller keeps yawing at +/-0.4 rad/s even while translation commands shrink
to 1e-5 m/s. mock_velocity._yaw_rate_toward uses direction of the residual waypoint
position error, with only a 1e-6 per-axis deadband; this makes near-goal direction
unstable. The waypoint is a standoff navigation point, not a persistent object-facing
camera orientation. This is directly observed in commands and the replay.

A rotating camera also changes the world point obtained by grounding the center of
the visible/cropped target body. At source 13.95 s (response 15.2 s), the inferred
point is (11.8071,-0.3740,2.9129); source-side cross-track is 0.3972 m, above the
0.35 m hover bound. The drone itself remains approximately (10.998,0.019,3), and the
evaluator correctly still counts hover. At response 15.2 s the monitor even reports
3.95 s accumulated dwell but keeps CONTINUE because its new point fails geometry.
This demonstrates a reference-point/measurement mismatch; do not weaken evaluator
thresholds to conceal it or treat changing body pixels as a fixed object anchor.

At source 18.95 s the yaw reaches -49.01 degrees. Exact policy input call-000030,
observation 380, shows only blue sky and gray/green ground. The model returns
kind=exploration, evidence="blue and gray surface", u=v=500. Available at 20.0 s,
this becomes waypoint (14.9307,-4.4755,3.0), accepted and translated into motion.
A target-point action briefly pulls back at 21 s; exploration resumes at 22 s,
followed by sustained departure. The immediate departure is caused by that accepted
exploration command after camera view loss, following the earlier completion/yaw defects.

## Evidence and boundaries

- DEPARTURE_AUDIT.json: exact source RGB matches for all 36 new monitor calls and
  1,425 new flight poses; source geometry, actual yaw/hover and saved monitor verdicts.
- Browser: three saved runs, nine standard seeks/three playbacks, five additional
  departure moments and exact input call-000030 inspected. Source 18 s contains red;
  source 18.95 s contains no pillar. All 1,650 poses across the three displayed runs match.
- 106 completed new local Gemma calls and two boundary cancellations; zero cloud calls.
- Both new runs have zero contact/collisions. Raw speed violation counts 1/8 are all
  exactly 4.44e-16 m/s floating-point overshoots, retained in VERIFICATION.json.
- Source/config freeze verified; no need to rerun the unchanged 433-test suite.
  Report/audit tooling lint and captured-source SHA-256 validation pass.
- Original D-108 report and debugger remain unchanged; this repeat report adds contrary
  evidence rather than overwriting the earlier success. Automatic approval capacity
  initially blocked export; after renewed user approval it succeeded. No extra flight.

Next bounded diagnostic work: separate camera-facing orientation from tiny translation
errors; define an observable stable target/approach reference and align source-time versus
live dwell checks. Validate saved-state negatives before any further model flight.
These repeats diagnose execution/monitoring reliability, not general VLM planning limits.

Dashboard: http://127.0.0.1:8765/hover_repeat.html#run=c5_hover_repeat_20260914_s1062&t=18.95
Rebuild: scripts/report_hover_repeat.py with historical 1061 then new 1060/1062 run
names; scripts/check_hover_repeat.py; scripts/verify_hover_repeat.py; audit script
scripts/audit_hover_repeat.py performs no inference.
