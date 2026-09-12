# Eight local capability scenarios — D-103

One first scenario per category agreed with the user. These are development
fixtures in the existing simulator, not final paper benchmarks or results for
any model. All use `capability_grid3d`, shared grid dynamics and corrected
`box_ray_v2` depth. No new policy or VLA training is included.

The current research design is **ASP-UAV_Final_Research_Design.pdf**, in
`C:/Users/Asael/Documents/רחפנים סקירות/מסמכי דיזיין/`. It defines nine architecture
conditions, not nine tasks. The companion
`general_single_uav_autonomy_benchmark_design.pdf` defines the eight capability
regimes. The older concise PDF under docs is not the latest research framing.

## Runnable configurations

| Category | Environment ID | Scenario | Success beyond collision-free flight |
|---|---|---|---|
| Known-goal navigation | `capability_known_goal` | Open-world ENU target (12,0,3) m, supplied in instruction | Within 2 m and explicit stop |
| Semantic goal navigation | `capability_visible_target` | One visible red pillar | Within 2 m of the red pillar and explicit stop |
| Semantic search | `capability_turn_search` | Red pillar outside initial forward view; turn reveals it | Target observed during physical steps, approach within 2 m, explicit stop |
| State reasoning | `capability_overturned_vehicle` | Two neutral-colored box vehicles; one wheels-up | Stop within 2 m of hover point 3.2 m above the ground over the inverted vehicle |
| Conditional task | `capability_conditional_gate` | Left opening preferred; use right if left blocked | Cross the instructed opening below 7 m, then reach red pillar and stop; a wrong first crossing fails |
| Multi-stage mission | `capability_ordered_visit` | Red pillar then blue pillar | Dwell 0.5 s within 2 m of red, then reach blue and stop; blue-only is not success |
| Recovery | `capability_closing_passage` | Initially open passage closes at 3 s | Reach pillar beyond closed wall and stop, without collision; route around either wall end |
| Continuous visuomotor control | `capability_follow_target` | Red marker moves at 0.7 m/s in a straight line | Acquire by 5 s; during 5–20 s, stay 4–6 m away and within 20° horizontal bearing with target in camera for >=90% of the window, including its last 2 s |

Following ends automatically after the scoring window when successful. An early
stop fails. Its outcome is latched at the window deadline; extra time cannot
rescue a failed fixed window. The other tasks require an explicit architecture
stop. All have a 60 s outer timeout, 2 m/s command limit, 0.5–7 m altitude band,
45 m geofence, forward 224×224 RGB-D camera, 90° field of view.

Left blockage is true on odd seeds and false on even seeds. Search bearing and
inverted-car side also flip with seed parity. These are simple counterbalanced
fixtures, not a rich random scene generator. Development uses 1060–1064.

## Information boundary and evaluation

Normal observations contain RGB, depth, odometry and range measurements.
`semantic_hits` is empty; no target/state class, answer coordinate, route,
branch choice, visit progress or tracking score is supplied to a policy.
Known-goal coordinates are public in that task's instruction only. Privileged
C0 access remains explicitly flagged and must never be mixed with semantic results.

`EnvironmentStatus.task_complete` is evaluator-only. The orchestrator and
terminal/recovery metrics honor it; `None` retains legacy distance scoring.
Task diagnostics are persisted in result status and task-prefixed metrics.
Distance remains actual target distance, including for following; it is not
replaced with a fake distance to make success scoring pass.

Vehicles are compositions of identical colored boxes. Inversion moves wheels
above the body and the roof below it; no red target tag identifies the answer.
This only tests coarse visual state discrimination, not medical or emergency
reasoning. Pillars and the moving marker use the existing non-solid landmark
representation. The following marker is not a simulated pedestrian.

Shortest-path/SPL is not certified for conditional, ordered, recovery or tracking
tasks (`shortest_path_valid=0`). Use task success, route/visit/tracking diagnostics,
flight time and calls; do not interpret their zero placeholder SPL as efficiency.

## Use

Choose any compatible existing architecture and one of the environment IDs:

```powershell
$env:PYTHONPATH='src'
python -m uavlab.cli run --arch YOUR_ARCH --env capability_visible_target --seed 1061 --out runs/YOUR_NEW_RUN --debug-capture
python -m uavlab.cli debugger runs/YOUR_NEW_RUN --out reports/debugger/YOUR_RUN.html
```

This adds tasks, not unsupported skills to policies. AerialClaw's historical
acceptance used labeled detections, which these RGB-D scenarios intentionally
withhold. Existing policy performance/compatibility must be measured explicitly;
no architecture is claimed to solve the eight tasks.

## No-model validation and visual review

```powershell
python -m pytest tests/unit/test_capability_scenarios.py tests/contract -q
python scripts/validate_capability_scenarios.py --out reports/NEW_FIXTURE_RECORDINGS
python scripts/check_capability_dashboard.py
```

The validator uses privileged, scripted velocity commands through real shared
physics. It does **not** call SUPER or a foundation model. All demonstrations are
labeled `scripted geometry fixture; NOT architecture performance`. They prove
physical reachability and scenario scoring, not a planner's autonomous capability.
Fresh output folders are required; previous evidence is never overwritten.

The existing debugger now replays current obstacle geometry and landmark positions
per frame. It displays private task status, ordered visits, gate events, and
tracking duration. No-model demonstrations: `reports/debugger/capability_scenarios.html`.
