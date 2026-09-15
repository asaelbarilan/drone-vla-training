# D-118 semantic progress gate: FAIL, no new flight

The existing monitor's code conflates current target absence with LOST. The opt-in
candidate restores a VLM progress status over hybrid visual history plus current RGB.
The six-call gate rejects this candidate because it corrupts current target grounding.

| Source | Legacy current-only | Candidate history + current |
|---|---|---|
| 33.95s, target visible | Correct red pixel (202,79,79); accepted CONTINUE | Claims visible but points at ground (104,112,96), raw STOP; accepted CONTINUE |
| 35.95s, first occlusion | Correct absence; accepted LOST | Claims target in HISTORY4/5, falsely visible now; points at gray wall (132,132,138), raw STOP; accepted CONTINUE |
| 66.95s, sustained loss | Correct absence; accepted LOST | Correct absence; raw/accepted LOST |

All six replies validate against their exact JSON schemas and arrive in the thinking
channel. No errors/retries. Nine encoded inputs match frozen SHA256 and saved PNG
bytes; model residency digest matches the retained Qwen3-VL4B. Three current RGB
frames match original policy-call images and 1,340 replay positions match controls.
The memory is reconstructed by running the configured hybrid memory on every saved
observation, including snapshots. Independent monitor cases start ever_acquired=true
with no confirmed arrival memory: this isolates response normalization, not complete
hidden monitor-state replay or a trajectory counterfactual. See FREEZE.json.

Actual image inspection confirms the wall/ground point misses and the target appearing
only in HISTORY4/5 at35.95s. POINTS.png overlays model coordinates on current images.
The six-card dashboard, exact history inputs, prompts and runtime outcomes were
browser-checked: six cards/details, no broken images or JS errors (BROWSER.json).
Dashboard: http://127.0.0.1:8766/semantic_progress.html .

Distance/confirmation checks blocked every STOP in these independent cases. The false
35.95s target nevertheless creates an incorrect geometric candidate at3.674m, so this
is not evidence that repeated false identities would be harmless. Current identity
must remain reliable before promoting this variant.

## Decision

Do not run a flight with this candidate, and do not infer that temporal monitoring
cannot work. This joint prompt/schema fails the current-image identity gate on two
of these three selected cases. It gives no valid evidence for bypassing initial
occlusion. It is disabled by default and has no enabled flight profile.

Next bounded step: separate current-only target grounding from temporal progress
judgment. First freeze a status-only temporal probe supplied with the unchanged
current-only grounding result as timestamped evidence; temporal output must have no
coordinates, no authority to redefine current visibility and no authority to STOP.
Reuse saved current-only results for that offline comparison (clearly labeled);
if live execution is later warranted, account for both inference calls and latency.
Only consider another flight after valid status behavior distinguishes plausible
short occlusion from prolonged failed movement. No oracle route labels or goals may
enter model inputs. A CONTINUE alone does not prove the narrow route traversable.

## Validation and budget

401 unit tests passed (one existing dateutil deprecation warning); runtime/test lint
passed. Layout requires separate history/current inputs. Legacy profiles unchanged.
Code/freeze commit02b3deb. Six local calls completed; total saved-frame calls this
bounded session12. Model flights remain2/4. Dedicated11435 unloaded and stopped;
shared11434 and Valley8765 untouched. No cloud calls or deleted model reinstalls.
