# D-111: clutter diagnostic, first flight retained

c5_clutter_stable_20260914_s1061 times out at90 s, final37.906 m, closest22.583 m.
Zero collisions. The328 raw constraint violations were later verified as speed-roundoff excesses
no larger than2.22e-16 m/s. Counters remain unchanged. Historical corrected-depth seed1061
closest14.940 m/final30.015 m: this combined variant is not an improvement here.

First concrete semantic mismatch: call000004 captures obs40 at1.95 s, returns at3 s:
"a tall, grey, rectangular structure",kind=target,(850,500), despite exact mission
"fly to the red tower and stop there". Current source image has gray structures,
no red tower. Later call000022 repeats gray target; call000045 selects green target.
Exact prompt contains correct mission and attribute-matching instructions. This is
not a missing mission string. These statements describe returned evidence, not
hidden reasoning. Incorrect grounding precedes the requested narrow-gap question.

Both1800-pose dashboard replays match exactly;10 seeks/2 playbacks pass.134 completed
local Gemma calls+1 cancellation,zero cloud. Frozen environment/execution parameters
match historical corrected-depth run. No runtime change. Propose saved-frame test
of existing VLM-reported color/alternative-point contract before one matched rerun.
Policy guard uses model-reported observed_color, not RGB thresholds or ground truth.
Outcome of proposed repair not yet known; preserve baseline.


## Completed matched rerun and image transport check

c5_clutter_attributes_20260914_s1061 also times out. Closest33.343 m at5.6 s,
final67.845 m, versus first run closest22.583 m/final37.906 m. Do NOT promote the
attribute variant as a navigation improvement. All89 effective decisions are
exploration; false target labels no longer pass this contract, but the alternative
points do not form an effective search. The first alternative (900,500) points at
the right gray structure in the exact initial RGB. At26 s the camera faces a green
distractor and the trajectory has already turned away from the target area.
The gate fixes label consistency, not passage choice or search memory. An accepted
SUPER plan does not certify that a VLM-selected subgoal is useful for the mission.
No narrow-gap traversal conclusion follows: these new routes diverge earlier.

Two new flights,one matched setting change,three saved-frame probes,then stop.
No new runtime code,default changes,third flight or promotion. Next isolate the
VLM exploration contract (what constitutes a useful open continuation) on saved
frames, including a case with a clearly visible red target. Do not tune SUPER
clearance or claim VLM incapacity from these two trajectories.

User asked whether RGB/BGR was swapped. IMAGE_TRANSPORT.json and the offline
check_vlm_image_transport.py exercise the policy encoder and actual backend request
construction with network intercepted:224x224 RGB PNG,Base64 in messages[0].images,
POST /api/chat. Exact captured PNG bytes survive JSON/request construction. Known
red center pixel remains RGB(205,46,46); gray input center(142,142,146). No client
RGB/BGR swap observed. DebugCapture writes base64-decoded request bytes and passes
the original request unchanged to backend. This does not inspect server-internal
image preprocessing. Zero additional model calls for this transport check.
Exact images were shown to the user, not later replay views.

Validation:33 existing attribute/target-stop tests pass. AUDIT.json verifies all
3,600 new flight poses and178 policy source images pixel-for-pixel. Three displayed
replays total5,400 exact poses,zero missing frames;15 browser seeks/3 playbacks pass.
Both navigation freezes and captured source hashes verify unchanged. Both flights
have zero collisions/out-of-bounds. Raw speed violations328/465 are all at most
2.22e-16/1.11e-16 m/s respectively, retained without altering metrics.
Budget:268 completed flight Gemma calls+2 boundary cancellations;3 completed saved
frame probes;271 completed local model calls total,zero cloud. No inference errors.
Dashboard: http://127.0.0.1:8766/clutter_stable.html (Valley8765 untouched).
