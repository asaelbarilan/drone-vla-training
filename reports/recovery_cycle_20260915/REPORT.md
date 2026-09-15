# Autonomous recovery cycles — 15 September 2026

**Three new flights completed and visually audited. None completed the mission.**
The last named extension cleared the obstacle and approached to 4.65 m before the
90-second timeout. All three had zero collisions. No cloud models or paid calls.

| Trial | Change tested | Closest / final distance | Finding |
|---|---|---|---|
| 1, D-116 | Fresh image after LOST reorientation | 13.40 / 29.94 m | Handoff works; navigation still fails. |
| 2, D-117 | VLM-selected return to an observed viewpoint | 14.93 / 17.01 m | Return restores target view; later occlusion interrupts progress again. |
| 3, D-121 | Bounded persistence of an accepted target goal | 4.65 / 4.65 m | Detour restores view; steady final approach, but no completed arrival/stop. |

The last trial's model output differs before the extension first activates, with
CPU placement different from the earlier GPU runs. Its better distances therefore
are promising descriptive evidence, not proof that the architecture change caused
all the gain. These are development experiments, not held-out paper results.

## What we learned about the failure

There are separate mechanisms, not one generic "bad VLM" failure. The return trial
shows correct red-target points followed by loss during movement. Current-visibility
monitoring treats occlusion as LOST; fresh exploration goals and yaw recovery can
interrupt an accepted intention. A saved-state held-goal probe and the last flight
show that preserving the goal can let common local planning make a useful detour.
The VLM supplies the semantic goal; this added executive persistence is a named
architecture extension. Native paper profiles remain unchanged.

Two temporal-monitor prompt probes did not pass the selected identity/status
checks and were not promoted into a live flight. Their historical-image construction
was later found to use the wrong update cadence; D-120 explicitly corrects that
limitation. Do not cite those constructed histories as exact original live requests.

## Evidence and next step

- [Cycle 1](cycle1/REPORT.md), [cycle 2](cycle2/REPORT.md), [cycle 3](cycle3/REPORT.md).
- [Latest flight debugger](http://127.0.0.1:8766/recovery_cycle3.html#run=c5_target_commitment_20260915_s1061&t=74).
- D-120 [saved-state execution probe](goal_hold_component/REPORT.md).
- 392 completed requests across the three flights, three boundary cancellations;
  15 additional saved-frame diagnostic calls. All local. No extra model downloads.
- Changes are committed separately; raw evidence and source snapshots are retained.

Next: validate an exact replay checkpoint before a bounded continuation that tests
arrival and stopping beyond 90 s. Report that separately from the failed 90-second
benchmark. A matched-placement comparison is also needed before attributing the
outcome improvement to target commitment. Three of four available flight slots
used; no rushed fourth trial. Dedicated inference stopped; debugger stays available.
