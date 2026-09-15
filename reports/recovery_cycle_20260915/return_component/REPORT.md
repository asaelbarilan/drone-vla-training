# D-117: VLM-selected observed-view return (named extension)

This is not the published OnFly recovery. A VLM chooses backtrack,continue,or hold
from a current image and one retained model-confirmed historical view. Only the
backtrack choice starts return to that recorded onboard pose AND heading. No
model-supplied world coordinates or simulator target position enters execution.
The policy has one return request per episode and a20s execution deadline; old
anchors expire after30s. Normal current-image decisions otherwise remain unchanged.

A private, typed option binding authorizes only the exact stored pose/heading.
The return verifier applies generic geometric checks without repairing coordinates;
normal point proposals retain OnFly provenance checks. Both use the same SUPER
planner/controller. The optional waypoint view_yaw_rad is a terminal camera heading,
not mission stop. Shared controller aligns it inside0.25m. Stationary view requests
have an explicit planner hold path with a known-free braking check. Old waypoints
without this field retain existing behavior.

Saved-state component: replayed784 controls to39.2s, including planner observations
and last confirmed policy view obs680/33.95s. A STUB selects backtrack, so this is
execution evidence only. Return completes48.2s: position error0.02315m,
heading error3.133degrees,zero collisions. All10 option refresh/hold proposals
accepted. Historical,start,and final RGB images visually inspected: red target is
absent at start and visible after return. That does not guarantee mission success
or successful recovery in other scenes.

An initial component iteration exposed rejection of zero-length observation hold;
stationary-view support fixes that explicit handoff. Unit checks cover missing/old
anchors,forged coordinates,blocked return,timeout,one-request budget,position AND
heading completion,fresh next decision,nonfinite heading,and braking clearance.
The config initially exceeded the16-level inheritance limit; using the existing
Qwen baseline plus the explicit fresh-view flag preserves the same resolved settings.
No real-model flight has run for this variant yet.

Files: RESULT.json,anchor.png,view_0.png,view_180.png; script
scripts/probe_observed_view_return.py. One of four authorized model flights used
before this component. Next freeze a single same-seed model flight only after tests.
