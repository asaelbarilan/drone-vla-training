# D-105 AerialClaw completion and requested perception

Coordinate completion and the visible-target skill flow now pass their development
cases. Search is still unresolved. No general reliability or paper ranking is claimed.

| Case / profile | Outcome | Sim / wall seconds | Evidence |
|---|---|---|---|
| Public coordinate, completion fix | PASS | 26.0 / 16.32 | 2 completed text calls, exact coordinate, explicit stop |
| Visible target, strict selected-pixel depth | timeout | 60.0 / 14.62 | Detection saw red pillar but pixel fell ~5 px below valid depth; no translation |
| Visible target, bounded pixel refinement | PASS | 35.7 / 9.50 | 3 completed text calls + 1 image call; final distance 1.415 m, explicit stop |
| Hidden target, same refined profile | timeout | 60.0 / 12.12 | 4 completed text calls, zero detection-tool requests; legacy search advice assumes passive perception |
| Hidden target, intended strategy profile | INVALID SETUP | 60.0 / 10.62 | Failed code insertion left old strategy active; not a valid test of repaired advice |

All five flights have zero collisions and constraint violations. Historical D-104
coordinate and visible-target failures are included for comparison. The original
strict visual failure and invalid setup trial remain available in the debugger.

## Architecture boundary

Text-only LLM chooses detect_object, goto, scan and done. On a requested detection,
the tool captures the next available synchronized RGB-D observation, calls Gemma for
an object location, and unprojects measured depth. It returns semantic position
memory with the original observation timestamp. Only a later model-selected goto
can command motion. The existing skill executor and SUPER continue the selected
world goal without further model waypoints. No simulator semantic hits, goal truth
or automatic image-to-motion loop is used by the tool.

Completion for known_goal_nav reads one unambiguous explicit world ENU coordinate
from the public instruction, with current distance <= mission radius and speed
<=0.75 m/s checked by both policy and runtime. It does not author actions.
Semantic tasks retain their existing evidence-supported completion contract.

The refined tool is a named opt-in variant: if the selected pixel has no depth,
a window of at most 3% of image size may supply a single connected, range-consistent
observed surface. The pixel moves onto that surface before lifting; range is never
invented for the empty original ray. Multiple surfaces, distant geometry and absent
objects remain rejected. This can still produce a biased object-position estimate;
the 1.415 m final error in this single trial is not a localization-accuracy benchmark.
A saved-image bbox probe also missed; that approach was not adopted.

The visual profile declares a single public object query (red pillar). Multi-object
ordering, generic state reasoning and dynamic tracking are not implemented here.
Motion/semantic code for OnFly was not changed. Existing point-only and legacy text
profiles remain selectable; all new behavior is identified in manifests/commits.

## Search and process limitation

Search advice was changed to distinguish rotating a camera from detecting an object.
The first insertion failed to match formatted source. Its focused test detected this,
but the PowerShell chain continued into commit and flight: the intended-strategy run
is INVALID for assessing the change. The insertion was corrected and tested offline;
no additional flight was launched. Future command chains explicitly gate on exit code.
Corrected c1_visual_search_gemma_dev is NOT flight-validated. This is the next
bounded validation before expanding tasks or claiming a working search architecture.

## Timing and inference budget

All real calls use local gemma4:e2b with the pinned repaired-projector digest.
C1's inherited simulated policy charge remains 8.5 s; perception is explicitly 1.2 s.
Wall times are separate. The new perception charge is a declared development setting,
not calibrated hardware performance, so this is not a matched-latency comparison.

Five new flights: 21 completed calls and 5 cancelled boundary calls. One extra completed saved-frame bbox probe. No cloud calls, other model loads, held-out seeds or additional scheduled runs.

## Evidence and reproduction

- Dashboard: http://127.0.0.1:8765/aerialclaw_tools.html
- RUNS.json: all outcomes, metrics, call roles/image counts and replay provenance.
- Each new run subdirectory: manifest, result, compressed original events and exact calls/images.
- SAVED_FRAME_GEOMETRY.json: exact-image equality plus original/refined depth outcome.
- bbox_saved_frame_probe.json: unsuccessful alternative, preserved.
- scripts/report_aerialclaw_tools.py rebuilds the seven-run page from local runs.
- scripts/check_aerialclaw_tools.py checks playback, images and source associations.
- scripts/verify_aerialclaw_saved_detection.py repeats the geometry check without inference.

Final verification: 406 unit/contract tests pass (one pre-existing dateutil deprecation warning). Seven saved trajectories replay-match; 21 browser timeline checks and seven playback checks pass. Tool entries show their exact image and matched source observation. Selected successful-flight screenshots inspected directly.
