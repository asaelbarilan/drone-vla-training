# D-99: two additional corrected-depth Gemma flights

Both requested flights timed out after 90 simulated seconds without collision.
Together with D-98, the corrected-depth setup has 0/3 successes on development
seeds 1060, 1061 and 1062. No architecture or runtime changes were made between
these flights. This small development screen does not isolate a new cause.

## Fixed conditions

- Architecture: `c5_gemma_guarded_monitor_dev`.
- Environment: `grid_nav_onfly_depth_v2_dev`, corrected `box_ray_v2` depth.
- Actual model: local shared `gemma4:e2b`, verified in all 268 completed new
  inference events (89 policy + 45 monitor per flight).
- Temperature 0, sampling seed 0, fixed simulated model latency, 90 s horizon.
- Exact debug capture enabled: prompts, request images, returned output,
  source code references and planned paths. One horizon-cancelled request per run.
- Exactly two new launches, no cloud calls, model swaps, parameter tuning or retries.
- New architecture/environment manifests match D-98 exactly. Only scene seed changes.

## Outcomes

| Seed | Outcome | Closest (m) | At (s) | Final (m) | Path (m) | Collisions |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1060 (new) | timeout | 26.24 | 24.50 | 59.27 | 49.86 | 0 |
| 1062 (new) | timeout | 21.22 | 39.45 | 37.46 | 52.74 | 0 |
| 1061 (previous corrected) | timeout | 14.94 | 40.00 | 30.01 | 50.60 | 0 |
| 1061 (historical legacy context) | timeout | 14.32 | 40.50 | 14.62 | 32.31 | 0 |

All 89 proposals in each new flight were accepted. No inference or parse errors.
Verifier repair rates were 20.22% (1060) and 25.84% (1062). No terminal monitor
stop was issued. Collision-free does not mean mission success or zero reported
constraint-violation ticks; full metrics are preserved in the result files.

## Visible evidence and limits

The flight-map traces show approach followed by movement away from the target.
At seed 1060's 24.50 s closest approach the camera is dominated by a foreground
wall; at the endpoint it shows sky and ground. At seed 1062's 39.45 s closest
approach, walls remain at the left edge while the flight heads into open space;
its final camera also shows sky and ground. These are observations from the
saved replay, not a claim about what the model intended or a proven failure cause.

The prior geometry validation still stands. These additional layouts show that
correcting obstacle depth alone has not solved navigation in this configuration.
The old seed-1061 legacy flight is retained as context; no matched legacy flights
were run on seeds 1060/1062, so these rows do not measure the depth fix's causal
effect across seeds. Next inspect exact source-aligned decisions around departure
before proposing another change. No additional flight is scheduled.

## Replay and verification

All four exported flights reproduce 1,800 logged positions each exactly, including
final distance. Each has 89 matched policy source references and zero missing
source frames. Both new runs contain 135 captured request records each (134
completed, one cancelled). Browser checks pass for all four run selections and
closest/final distances, plus playback and visible raw model responses for both
new flights. No JavaScript errors. Closest/final screenshots visually inspected.
No runtime edits required rerunning the previous 342-test suite; the report script
passes Ruff and its actual export validates manifests and trajectories.

Watch: http://127.0.0.1:8765/depth_fix_comparison.html

Rebuild without inference from the repository:

```powershell
$env:PYTHONPATH='src'
python scripts/report_depth_fix_two_runs.py
```

Evidence: `RUN_COMPARISON.json`, `BROWSER_CHECK.json`, `1060/`, `1062/`,
`RUN_1060.log`, `RUN_1062.log`, `EXPORT.log` and four closest/final screenshots.
Complete event logs and exact model captures remain in the corresponding ignored
`runs/c5_depth_ray_v2_20260912_s1060` and `..._s1062` directories. Portable generated
HTML is in `reports/debugger/depth_fix_comparison.html` (rebuildable, not committed).

Commits before execution: preregistration `37a063a`, first-flight evidence `8118d07`.
Runtime repair remains `ebaa1bd`. No runtime code changed during D-99.
