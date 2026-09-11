# D-98 — Depth repair and one matched Gemma flight

The per-pixel depth repair is geometrically correct, but the single authorized
flight **did not improve navigation**. It timed out after 90 simulated seconds,
finishing 30.01 m from the target rather than the original 14.62 m. Neither
flight collided. No further flight or model call is scheduled.

[Watch the corrected flight](http://127.0.0.1:8765/depth_fix_comparison.html#run=c5_depth_ray_v2_20260912_s1061&t=0).
The dropdown contains the original guarded flight for comparison. Generated
local file: `reports/debugger/depth_fix_comparison.html`.

## Repair and offline verification

`box_ray_v2` computes camera-forward ray/box surface depth separately for each
pixel of the box drawn in RGB. It preserves the RGB painter's object ownership,
landmark billboards, missing-background-depth convention and 0.2 m near limit.
A drawn silhouette pixel whose ray misses its box or has a near-clipped first
surface remains invalid. It does not fabricate a range or see through a clipped
front face. This is an isolated obstacle-depth repair, not a complete redesign
of RGB clipping, occlusion or ground sensing.

`legacy_corner` remains the default for historical configurations and replay.
The new matched environment `grid_nav_onfly_depth_v2_dev` selects `box_ray_v2`.
New depth sensor reference digests include the version; old references do not
change. No policy, monitor, controller or SUPER parameter changed.

At the disputed source observation 800, the 5x5 median changes from
0.213216454 m to **1.731457114 m**. Holding the original recorded model pixel
fixed moves its lifted waypoint by 1.525347 m. That corrected point is still
on the selected foreground wall; repairing depth does not select a route.

Validation before inference:

- 342 unit and contract tests passed, including seven new depth regressions.
- Exact historical replay: all 1,800 poses and 89 RGB/legacy-depth images match.
- 1,146 corrected box patch pixels agree with independent ray geometry within
  4.75e-7 m. See `SAVED_PIXEL_CHECK.json`.
- Config comparison proves the architecture is identical to the original
  manifest and only the environment ID/depth-renderer parameter changes.
- Fix committed before launch: `ebaa1bd`.

## Single flight outcome

| Measure | Original guarded flight | Corrected depth |
|---|---:|---:|
| Success | No | No |
| Termination | Timeout | Timeout |
| Simulated duration | 90 s | 90 s |
| Final target distance | 14.61545 m | 30.01488 m |
| Closest target distance | 14.32356 m | 14.93985 m |
| Travelled distance | 32.31351 m | 50.59676 m |
| Collisions | 0 | 0 |
| Accepted policy decisions | 89 | 89 |
| Verifier repair rate | 19.10% | 2.25% |
| Completed policy / monitor calls | 89 / 45 | 89 / 45 |

Run: `c5_depth_ray_v2_20260912_s1061`.
Architecture: `c5_gemma_guarded_monitor_dev`.
Model: **gemma4:e2b**, verified on all 134 completed inference events.
Local Ollama only; no cloud quota. Full run took 102.82 wall-clock seconds.
Debug capture contains 134 completed calls and one policy call cancelled at
the episode horizon; no extra retry/continuation experiment was launched.
The shared Gemma runner was not unloaded.

The model's first 18 recorded pixel choices match the original. The changed
depth affects the point at availability 18 s; the first different model point
occurs at 19 s, when previous-goal context can already differ. The physical
trajectories first differ at 28.05 s. This is consistent with a closed-loop
response to the repaired input, rather than a changed architecture setting.
It is still only one development seed, not a general causal performance result.

The new flight gets closest at **40.00 s**, then moves away and ends outside
the obstacle cluster with a green landmark in view. The full source images and
outputs are now recorded. No claim about the reason for a selected pixel is
made from the endpoint image alone.

## Interpretation and continuation

Keep the proven sensor correction available and use the explicit corrected
sensor profile when continuing this investigation. The poorer navigation
result does not make the old depth values correct. Historical references stay
replayable, and a future architecture comparison must use the same corrected
sensor conditions across its arms.

Navigation remains unresolved. Lower verifier-repair rate is not mission
success. The next useful inspection is the captured decisions around the
40 s closest approach and the subsequent departure, with selected source pixel,
world waypoint, SUPER route and current target evidence together. No new
verifier, margin change, model swap or automatic run is authorized by this
report. The requested single flight is complete.

## Replay and artifacts

Both trajectories reproduce exactly: 1,800 poses each, zero maximum position
error, zero final-distance error, 89 policy source matches each and no missing
source frames. Edge checks verified both run selections, seeking, final metrics
and the new exact response panel, with no JavaScript errors.

- `RUN_COMPARISON.json`: metrics, first divergence and replay integrity.
- `result.json`, `manifest.json`, `RUN_OUTPUT.log`: retained completed-run data.
- `SAVED_PIXEL_CHECK.json`, `TESTS.json`: offline validation.
- `corrected_final.png`, `original_final.png`: visual endpoint comparison.
- `BROWSER_CHECK.json`: UI validation.
- Full events and exact model inputs/outputs: the corresponding ignored run
  directory under `runs/`, as required by repository artifact policy.

The manifest points to `ebaa1bd`; its dirty flag reflects pre-existing/untracked
workspace artifacts. All modified runtime code was committed before launch.

Commands (the first starts a new model flight; do not rerun for viewing):

```powershell
$env:PYTHONPATH='src'
python -m uavlab.cli run --arch c5_gemma_guarded_monitor_dev --env grid_nav_onfly_depth_v2_dev --seed 1061 --out runs/c5_depth_ray_v2_20260912_s1061 --debug-capture
# Offline export of the completed runs; zero inference:
python scripts/report_depth_fix_run.py
```
