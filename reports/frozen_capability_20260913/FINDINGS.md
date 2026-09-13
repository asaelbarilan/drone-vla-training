# What the frozen comparison establishes

All 24 preregistered development flights completed without runtime errors. No flight
was repeated, no policy/config was tuned, and all 24 manifest configurations match
FREEZE.json. Source/config hashes remained unchanged. Historical runs are preserved.

| Implementation | Full task completion | Interpretation |
|---|---|---|
| C0 / privileged final-goal SUPER | 6/8 | Oracle execution baseline; skips ordered red visit and stops instead of tracking |
| C1 / AerialClaw family | 2/8 raw; 2/3 in implemented coordinate/single-object coverage | Coordinate and visible-target pass; search has a demonstrated scan/perception contract conflict; five other cells lack visual integration |
| C5 / OnFly current-frame profile | 0/8 | Full completion absent; arrival and partial task progress occur, so a general planning-incapability conclusion is unsupported |

These are eight task types on ONE development seed, not eight independent reliability
trials. C0 is privileged; C1 switches explicitly declared profiles by supported input
contract, and C1/C5 simulated inference charges differ. This is a compatibility and
debugging screen, not an architecture ranking for publication.

## Failure classification and next falsifiable checks

| Cell(s) | Evidence | Classification | Next isolated check, not executed |
|---|---|---|---|
| C1 known coordinate | goto(12,0,3), explicit done, PASS at 26.0 s | Prior coordinate completion bug repaired and reproduced | Retain repair; later test other coordinates without tuning |
| C1 visible target | detect_object -> measured target goto -> done, PASS at 35.7 s; final 1.415 m | Supported single-object tool flow; localization remains approximate | Other layouts as a separately declared robustness check |
| C1 search | Target visible in camera at 10 s; sole detector source at 21.95 s has no target; second scan rejected by full-turn gate | Demonstrated integration conflict; effect of a repair still untested | Separate physical rotation from actually inspected viewing directions, and test scan/retry legality on saved state before a flight |
| C1 overturned/gate/ordered/closure/follow | All 20 completed requests contain zero images; no semantic hits or requested tool in these five profiles | Missing visual/task integration, not a negative result for visually equipped AerialClaw | Define required object/state evidence and task completion contract before a new condition |
| C0 ordered visit | Goes to blue, stops, red subgoal count 0 | Known missing task sequencing in oracle policy | A task-aware oracle would be a separate baseline |
| C0 follow | Approaches then stops at 5.75 s | Known final-goal policy mismatch with sustained tracking | Separate tracking controller/oracle condition |
| C5 known coordinate | Enters goal region at 8.05 s, closest 0.731 m at 9.15 s; no stop | Completion contract mismatch is a concern: current monitor asks for a visual destination even for coordinate instruction | Saved-odometry completion audit, independently of navigation |
| C5 visible target | Enters goal region at 10.15 s; closest 0.335 m at 13.05 s, then departs. Last identified monitor sample range 2.092 m; next sample lacks target | Observed arrival/stop failure; individual causal contribution of sampling, geometry and control unresolved | Saved-state arrival replay with target range, capture/availability times and view loss; do not merely relax the threshold |
| C5 search | Never closer than initial 11.314 m | Observed search failure; no isolated root cause | Source-aligned heading/viewpoint/decision audit |
| C5 overturned vehicle | Closest 4.005 m, no completion | Unresolved perception/selection/approach behavior | Inspect exact distinguishing vehicle images and selected pixels |
| C5 conditional gate | Correct branch recorded, closest final-goal distance 8.605 m, no completion | Partial route success; later failure unresolved | Inspect post-crossing decisions, not just final timeout |
| C5 ordered visit | Red visit completed at 6.95 s, blue not reached (closest 11.528 m) | Partial sequencing behavior; task-state transition needs audit | Check whether explicit red-complete/blue-active state reaches policy and monitor |
| C5 closing passage | Closest 12.715 m; final task incomplete | Recovery failure observed, root cause unresolved | Align closure, map, proposals, gates and actual movement |
| C5 follow | 5.9 of required 13.5 good seconds in fixed 5–20 s window | Tracking criterion not met; this profile's single-destination monitor is not task-aware | Audit distance/bearing control and tracking completion separately |

No new verifier, classical semantic planner, relaxed goal radius, extended horizon
or patched profile was introduced during this comparison. Confirmed contract defects
are candidates for targeted fixes. Missing capabilities require a named implementation
extension. Other failures remain unresolved, rather than being labeled model defects.

## Budget, safety and verification

743 completed local Gemma calls (31 C1 + 712 C5), plus 16 boundary cancellations.
C0's zero-token simulated entries are not real model calls. No cloud calls, model
swaps or credential-file reads. Summed flight wall durations: 495.745 s, separately
from fixed simulated charges; analysis/rendering time is additional.

Zero collisions. C5 records 14 constraint violations across six flights; their
precise mechanisms are not assigned from the counter alone. C0/C1 record none.
All 19,414 recorded poses across 24 flights replay exactly, with no missing source
frames. Browser checks: 72 timeline seeks, 24 playbacks, plus 24 closest-approach
inspections; no browser errors. Exact C1 perception images match decision source IDs.
Search and OnFly arrival screenshots were directly inspected alongside source calls;
C0/C1 ordered-task and successful C1 approach screenshots were also inspected.
36 focused AerialClaw tests passed before launch. No runtime source changed, so the
previous 406-test suite was not unnecessarily repeated. New tooling passes lint
(long embedded HTML strings exempted from line-length check).

## Evidence and reproduction

- PLAN.md / FREEZE.json: preregistered matrix, resolved configs and source hashes.
- SUMMARY.json / CALL_BUDGET.json: per-cell outcome, closest approach, calls and replay proof.
- SEARCH_INSPECTED.md / ONFLY_ARRIVAL.md: exact causal boundary observations.
- Per-run directories: manifests, results, events.jsonl.gz, exact calls/images/source snapshots.
- browser/: timeline checks, screenshots, task transitions and inspection summary.
- scripts/run_frozen_capability.py: refuses retries/overwrites; existing experiment is complete.
- scripts/report_frozen_capability.py: rebuilds dashboard with no inference.
- scripts/check_frozen_capability.py and scripts/inspect_frozen_capability.py: browser verification.

Dashboard: http://127.0.0.1:8765/frozen_capability.html
No further flight is active or scheduled. Next work should start from a named row
and its isolated check, with the frozen results retained as the comparison baseline.
