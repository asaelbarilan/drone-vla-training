# Saved-view diagnosis: history alone versus action choice

Six completed local Qwen3-VL4B calls; no new flight, no retries, no runtime changes.
Two saved current frames: obs800/39.95s and obs920/45.95s; historical obs680/33.95s.
Current images do not contain the red target. Historical image and relative odometry
come from recorded onboard observations and prior VLM classification, not goal truth.

| Condition | obs800 | obs920 |
|---|---|---|
| Current image, point-only | exploration; point on small gray pillar | exploration; point on gray pillar |
| History + current, point-only | exploration; point on large gray wall | exploration; point on gray pillar |
| History + current, diagnostic action choice | backtrack | backtrack |

All six valid JSON answers classify the current target as absent (`exploration`).
However, history/point evidence says `red tower` while the selected CURRENT pixel
is gray: historical semantics contaminated grounding. All four point replies land
on obstacle faces, verified from actual images and displayed point overlays.
Action replies distinguish historical/current images and choose backtrack, but
this is NOT a demonstrated safe or effective trajectory. Evidence strings are
schema-limited and are not a full model reasoning trace. Two cases in one scene
cannot establish general planning ability, and the action prompt changes as well
as its schema. The experiment is a mechanism probe, not a model ranking.

This also refines the prior cycle's visual description: movement initially heads
toward the open side, but the VLM-selected pixel itself is on the small pillar.
A direction that looks plausible on the map is not proof of a clear chosen ray.

## Architecture boundary and next test

Local ONFLY_IMPLEMENTATION_LOCK.md explicitly gives the decision agent a current
image plus a previous-goal reprojection, and assigns keyframe memory to the monitor.
It explicitly commands heading restoration rather than return to a stored position.
The diagnostic grounded prompt omits the previous-goal cue; adding last-seen visual
memory plus return-to-view selection is a NEW named architecture variant. Do not
silently call it an OnFly reproduction or claim that a longer turn solves it.

Next: define a bounded `return_to_observed_view` option selected by the VLM.
The option refers only to a stored onboard pose/heading from a model-confirmed
view, not hidden target coordinates. Existing planner/verifier/controller execute
and can reject it; there is no automatic scripted target-search route. First
prove pose+heading handoff and fresh-view reacquisition in a saved-state component
fixture, including blocked return, missing anchor, timeout and repeated request.
Do not launch a flight before those checks or implement infinite backtracking.
A successful return would still leave the question of choosing a different route
on the next approach; reacquisition alone is not mission success.

## Evidence

Frozen six requests in FREEZE.json, six raw responses and attempt markers,
RESULTS.json (exact input bytes/digest verified), original PNGs, Edge dashboard
capture and checks. Four displayed point markers inspected visually. No JS errors.
First call includes cold model setup; these wall times are not a latency benchmark.
Dedicated11435 unloaded/stopped, shared11434 and Valley8765 untouched. One of four
flight slots still used. Dashboard: http://127.0.0.1:8766/recovery_context.html
