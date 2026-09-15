# D-117 cycle 2: return works, navigation still fails

Qwen explicitly selected backtrack at39s. Shared verified execution restored the
stored camera pose at48.5s. The actual current camera shows the red target again;
the monitor also confirms it at47.2/49.2/51.2s. This is live-model evidence of one
successful viewpoint-return option, not completion of the navigation mission.

After return, decisions available50/51s point correctly at red pixels in their
source frames (RGB202,79,79). The target becomes occluded again during movement;
at52s the policy chooses an exploration point on a gray face. At53.2s the monitor
reports LOST again. The one-return budget prevents an infinite return loop.

| Metric | D-115 baseline | D-116 fresh handoff | D-117 return option |
|---|---:|---:|---:|
| Outcome | timeout | timeout | timeout |
| Closest distance |13.746m|13.401m|14.930m|
| Final distance |29.295m|29.939m|17.007m|
| Collisions |0|0|0|

The return keeps the drone nearer the target at timeout, but closest approach
regresses. No aggregate improvement, reliable planner claim or profile promotion.
Minimum obstacle distance is1.106m. One development seed,90 simulated seconds,
235.49 wall seconds;124 completed local calls plus1 cancellation,zero errors.

## Next causal check: monitor semantics

The current_grounding monitor asks only whether the target is visible in ONE
current image. Code in onfly.py maps visible to STOP-candidate and absence to LOST
before the arrival guards. Thus the VLM is not currently choosing a semantic
CONTINUE-versus-LOST judgment using trajectory history. Temporary occlusion and
loss of mission progress are conflated by this profile's normalization rule.
This may trigger recovery during a legitimate detour; that causal effect remains
to be tested, not presumed. Both post-return target points were actually on red,
so these two proposals are not target-localization failures.

Before more flights or recovery extensions, reproduce the absence/status contract
offline. Compare the intended history-based semantic monitor with the current
visibility-only gate. Preserve strict current-image identity and geometric arrival
checks for STOP. Inspect the separate normalization that changes CONTINUE+absence
to LOST even when structured semantic output says CONTINUE. Do not simply disable
monitoring, suppress failures, extend time, or label all occlusions safe progress.
No additional flight is scheduled until this check yields a concrete hypothesis.

## Evidence

Exact replay1800 new poses;79 current policy-call images and the1 historical return
image match original rendered source observations. Both compared runs total3600
matching poses. Browser32 seeks/2 playbacks,no JS errors. Actual49s dashboard and
33.95/49/51/53.2s camera sequence inspected. POST_RETURN_POINTS.json records actual
source pixels. Raw calls/images/source snapshots and compressed events archived.
Macro refreshes are executive waypoint updates, not additional model calls.

393 unit tests pass. Runtime implementation commit45a092c; report audit recognizes
historical/current image ordering explicitly. Dedicated11435 unloaded/stopped;
shared11434 and Valley8765 untouched. Two of four authorized flights used.

Dashboard: http://127.0.0.1:8766/recovery_cycle2.html#run=c5_observed_view_return_20260915_s1061&t=49
