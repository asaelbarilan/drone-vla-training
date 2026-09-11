# D-86: goal-facing yaw did not rescue seed 1061

One local Gemma flight; no cloud calls, new model loads or held-out seeds. Trial: `runs/c5_gemma_goal_yaw_20260911_s1061`. Opt-in profile `c5_gemma_goal_yaw_dev`; default active profile remains unchanged.

## Result

| Metric | Historical repaired target-stop baseline | Goal-facing yaw trial |
|---|---:|---:|
| Success | No | No |
| Termination | Timeout at 90 s | False stop at 63.2 s |
| Closest distance across control frames | 13.22 m | 24.74 m |
| Final distance | 20.18 m | 25.20 m |
| Visible target time (50 ms replay frames) | 36.4 s | 0 s |
| Visible target decision frames | 36/89 | 0/63 |
| Predicted pixel inside visible red-body bbox | 0/36 | Not applicable |
| Collisions | 0 | 0 |
| Logged constraint-violation counter | 386 | 97 |
| Offline replay distance error | 0 m | 0 m |

Both logs identify policy/monitor as `gemma4:e2b`. Manifest comparison differs only in controller `face_semantic_goal: true`, profile ID and name; environment is identical. Software checks: 308 unit/contract tests pass, focused Ruff and diff checks pass. The historical comparison does not control inference nondeterminism or all intervening runtime state, so this is one diagnostic result, not a statistical causal estimate.

## Why the intervention was warranted

At 58.8 s in the baseline, the target left the horizontal view while camera/motion turned away. Motion direction differed from the planner semantic-goal bearing by 152 degrees; semantic-goal bearing differed from target truth by only 0.37 degrees. The other five visibility losses did not all share this pattern. Motion direction is a carrot proxy during ordinary tracking, not a reconstruction of private trajectory points.

The trial preserves translational command construction and speed/yaw limits, and changes heading toward planner metadata `semantic_goal_xyz`. It does not point toward privileged target truth. Recovery actions remain unchanged. Unit tests verify different heading with identical translation on an avoidance path and unchanged default handling.

## Interpretation and next step

Do not promote the yaw option or expand the sweep. It did not improve visibility or approach on this seed. The monitor declared a target-consistent stop using a 0.93 m depth despite being 25.20 m from the actual target. This directly implicates target identity/grounding and stop-evidence validation in this trial; yaw alone is insufficient. Target visibility is scored using the simulator's visible red-body pixels, not an independent semantic segmentation model.

Next useful work is an offline examination of the false-stop input and the monitor's target-consistency checks. Determine how non-target depth becomes accepted as target evidence before another live flight. Do not insert simulator truth into the policy or loosen the task threshold. No further flights were run.

Reproduce traces with `scripts/analyze_onfly_yaw.py RUN --output FILE` and `PYTHONPATH=src`. Data: `yaw_trace_1061.json`, `yaw_trial_1061.json`, `yaw_baseline_summary.json`. Simulator truth is used only offline.
