# D-107 targeted contracts: outcome and remaining limits

Final OnFly arrival-window flight passes at 13.2 sim seconds, final distance
0.370503 m, zero collisions/constraint violations. Search remains unresolved.
Corrected ordered C1 detects/reaches red and completes its first dwell, but never
requests blue or proceeds to it. No general architecture reliability is established.

| New run | Outcome | What the exact evidence shows |
|---|---|---|
| c1_inspected_search_20260913_s1061 | timeout, 60 s | Six negative detections from one unchanged view; no scan/motion. Prompt phase says scan_current_viewpoint, but model keeps requesting detection |
| c5_arrival_memory_20260913_s1061 | timeout, 60 s | Candidate stop at source 11.95 s; 3 s evidence TTL expired at response availability 13.2 s (age 3.25 s); live recheck refuses it |
| c1_ordered_visual_20260913_s1061 | timeout, 60 s | Four scans, zero requested detections. Exact prompt accidentally retained old passive-detector/full-turn advice; integration-confounded trial |
| c5_arrival_window_20260913_s1061 | PASS, 13.2 s | Same 2 m bound, same policy/camera/SUPER, confirmed anchor still valid in 4 s window; live stop accepted, final 0.371 m |
| c1_ordered_requested_20260913_s1061 | timeout, 60 s; first visit completed | detect red -> goto red -> hover -> repeated goto red; no blue query. Onboard first-dwell completion at 24.3 s is present in calls 4–6 |

Three historical D-106 runs remain alongside these five in the dashboard.
All failed runs are retained with exact images, prompts, outputs and source snapshots.

## What changed and what did not

### Inspected search

Named c1_inspected_search_gemma_dev replaces commanded angular coverage with actual
negative-detection viewing coverage (conservative complete 5-degree bins). Translation
resets coverage. Short model-selected scan steps are limited to 1.3 radians so views
can overlap. Physical rotation without inspection cannot prohibit another scan.
Default legacy coverage is unchanged; model selects every scan/detection/direction.
Offline regression reproduces the historical 7.5-radian gate state and verifies that
a short scan is now permitted. The real model never proposes that action in this trial.

### Arrival evidence and availability

Named current-grounding variants retain a stationary target position confirmed in
two distinct RGB-D observations, preserving original timestamps and rejecting jumps,
invalid ranges, repeated frames, expired evidence and live departure. Visual identity
confirmation can precede physical arrival. Odometry supplies current distance; neither
simulator goal truth nor a navigation waypoint can authorize stopping. The stop radius
remains 2 m. A live odometry/age check after inference prevents stale terminal stops.

The first saved-response probe checked capture-time eligibility only and incorrectly
suggested the 3 s window would solve the whole flight. Its original artifact is retained
as SAVED_ONFLY_ARRIVAL.json. The corrected probe SAVED_ONFLY_AVAILABILITY.json replays
identical RGB inputs, responses and controls through return-time checks: the 3 s window
fails at age 3.25 s; 4 s (two existing monitor periods) accepts the same arrival while
still expiring stale anchors. One final real flight verifies that specific repair.
This is a named temporal-memory extension, not a claim that the original paper specified
this mechanism. It is restricted to stationary single-object missions, not tracking.

### Ordered visual task

New policy exposes both public object queries and preserves separate semantic labels,
RGB-D locations and original timestamps. LLM selects tools and goto; SUPER executes.
The public instruction is parsed only to validate order, dwell and terminal completion.
Onboard odometry at control frequency verifies the first visit's 0.5 s dwell; sparse
observations cannot fabricate dwell. Policy and runtime both reject blue-first or
red-only stopping. Static object estimates expire at 30 s, and final speed is bounded.
No simulator task counters or answer-bearing semantic detections enter the policy.

Exact-input review found inherited passive-detector advice in the first ordered prompt.
The final named condition removes that strategy. The model then uses the new detector
and completes the first visit. Calls 4–6 contain first_visit_completed=true,
first_completed_t_ns=24300000000 and final_object=blue pillar, but model remains at red.
This is observed non-transition, not proof of general VLM planning incapacity. The
prompt still includes inherited per-label context keyed to the last queried object;
its consistency with the global ordered contract needs an explicit saved-state audit
before attributing the repeated red actions solely to model capability.

## Scope amendment and process corrections

Initial assistant-imposed cap was three flights. Exact-input/availability audits
found two concrete implementation mistakes after those flights. The cap was explicitly
amended to five and communicated before the final two launches. No additional model
probes, cloud calls, model changes or held-out seeds were used. No further run is active.

Failed preflight steps were retained in CHANGES.md: standalone probe initially imported
a test helper unavailable on its script path; a depth test fixture used integer storage
for infinity; initial browser monitor selection used the wrong time-field name. These
were fixed with explicit exit-code gates; no inference ran from failed preflight chains.
Browser selection now asserts monitor source 11.95 s and exact live-rejection evidence.

## Verification and evidence

- Full final offline suite and focused checks are recorded in VERIFICATION.json.
- Saved-response replay checks exact input RGB equality and every replayed pose.
- Eight debugger replays match trajectories, with zero missing source frames.
- Browser QA: 24 timeline checks, eight playbacks, exact detector source/image links.
- Successful arrival, stationary search and ordered target views were directly inspected.
- New-call budget: CALL_BUDGET.json; per-run metrics/replay proofs: RUNS.json.
- Per-new-run directories retain manifests/results, compressed events and exact calls,
  images and source snapshots; .gitattributes preserves their bytes across checkouts.

Dashboard: http://127.0.0.1:8765/targeted_contracts.html
Rebuild with scripts/report_targeted_contracts.py (no inference), then
scripts/check_targeted_contracts.py. Saved causal probe: scripts/probe_saved_onfly_arrival.py.
Do not rerun a full batch: remaining work is bounded tool/ordered-state contract diagnosis.
