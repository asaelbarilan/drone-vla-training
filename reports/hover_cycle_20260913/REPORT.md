# D-108 — approach and hover debugging outcome

Final development flight succeeds at 11.2 s: 1.0027 m before the red marker,
2.1 s continuous slow hover, correct approach height, target in view, no contact or
collision. Four flights total; all failures preserved. This establishes one repaired
fixture, not general planning ability or architecture ranking.

## Task and evaluation

User replaced the old "within 2 metres" rule with about 1 metre before the target,
keeping it visible, no touching and a short sustained hover. Named scenario fixes
range at 0.75–1.25 m, deviation from initial approach line <=0.35 m, speed <=0.2 m/s,
visible for 2 continuous seconds, followed by explicit completion. No threshold was
changed during debugging. Task truth remains in evaluator/dashboard only.

Geometry limitation: the inherited pillar is a rendered landmark, not solid collision
geometry. No-contact means the swept drone center never enters a 0.4 m exclusion
around its reference point. This is not a contact-physics experiment.

## Preserved trials

| Run suffix after c5_hover_ | Result | Diagnosis |
|---|---|---|
| baseline_20260913_s1061 | false stop, 9.2 s, 0.743 m | Old monitor still used 2 m arrival, ignoring hover; final image lacks pillar, speed not settled |
| contract_20260913_s1061 | timeout; actual hover 48.9 s | Current-only visual grounding loses object identity as close-up becomes a cropped red surface; old point-history steering also chooses invalid-depth ground pixels |
| context_20260913_s1061 | false stop, 11.2 s, 1.114 m | Reference/current images and grounded policy work, but arbitrary body-pixel height moves both waypoint and monitor's inferred approach line down; 0.403 m height drift violates task |
| level_20260913_s1061 | PASS, 11.2 s, 1.003 m | Initial onboard altitude retained and line deviation checked against initial odometry; 2.1 s independently scored hover |

## Changes and fidelity

- Reused 1 m endpoint standoff; model still selects the navigation pixel.
- Dedicated hover monitor validates low speed, approach side/line, range, contiguous
  control-rate dwell and projected target visibility against live depth. No evaluator
  task counters, goal coordinate or color detector is used.
- Current visual grounding receives an earlier identified reference image plus current
  frame, explicitly distinguishing their order. Current appearance must support identity.
- Existing grounded-waypoint option removes old previous-goal pixel-history steering.
- Named flight-level adaptation holds initial onboard altitude; camera-forward depth
  ceiling remains enforced. This changes paper full-ray lifting and is documented as
  an engineering variant, not a faithful reproduction or an isolated planning ablation.
- SUPER, controller and the task's evaluation thresholds were not tuned.

Historical current_grounding prompt IDs and identity_source labels remain inherited in
recordings even when the hover hook supplied two images: inspect exact request images
and prompt (both are preserved). Reference sequence is recorded in monitor evidence.
This is a remaining diagnostic naming limitation, not single-frame inference.

The final raw constraint counter is 1. SPEED_AUDIT.json shows it is exactly one command
at 2.0000000000000004 m/s: 4.44e-16 above the 2 m/s ceiling. Original results and physics
were preserved; no counter was rewritten to zero.

## Verification and reproduction

433 unit/contract tests pass, one third-party deprecation warning. Four replay
trajectories match all 1,835 poses; 12 browser seeks/four playbacks pass. All four
endpoint camera/map/observer views were directly inspected. Source snapshot hashes
match filenames. Exact inputs and response evidence are preserved alongside each run.
137 completed local Gemma calls, four boundary cancellations; no cloud/model swaps.

Rebuild without inference: `python scripts/report_hover_cycle.py` followed by the four
full run names above, then `python scripts/check_hover_cycle.py`. Exact RGB/depth audit:
`python scripts/probe_hover_grounding.py`. See VERIFICATION.json and RUNS.json.

Dashboard: http://127.0.0.1:8765/hover_cycle.html#run=c5_hover_level_20260913_s1061&t=0

No further flight is scheduled. User authorization for autonomous diagnosis continues,
but this approach-hover cycle has reached a verified endpoint. AerialClaw search/order
and broader planning comparison remain separate unresolved work.
