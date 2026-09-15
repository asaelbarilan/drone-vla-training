> **Correction (D-120):** D-118/D-119 used history constructed at every control
> tick, not the live policy-cycle memory cadence. Their current source RGB and
> raw responses are exact, but their history is not an exact runtime replay.
> Event-ordered reconstruction matches1340 poses and68 recorded memory counts.
> At35.95s the actual latest history is34.95s (1s gap), not27.85s (8.1s).
> The claimed live-history gap is withdrawn. No model calls were repeated.

# D-119 separate temporal status: no flight supported

Three calls complete, valid schema, no retries/errors. Current-only grounding is
preserved as supplied evidence; temporal answers cannot change coordinates,
visibility, or authorize STOP. Replies:33.95s CONTINUE,35.95s LOST,66.95s LOST.
Evidence acknowledges the correct current presence/absence in all three cases.
The first-occlusion verdict therefore fails the frozen experiment-entry criterion;
there is no support here for another flight using this monitor change.

Six exact image hashes and the retained model digest verified; all three model
residencies are CPU-only while Valley runs. Wall times66.750/37.359/65.188s are CPU
probe measurements, not flight latency. CPU placement and prompt both differ from
D-118, so this is not a controlled estimate of the separation's performance effect.
Saved grounder outputs are reused, not three additional fresh grounding calls.

The history at35.95s ends at27.85s, missing the last actual visible source33.95s.
At33.95/66.95s the latest historical images are6.1/16.3s old. The preserved global
keyframes may lack the recent transition needed to judge a short occlusion. This
is an input limitation, not proof the model should have returned CONTINUE. Neither
experiment establishes that the narrow route was feasible or that LOST caused failure.
Three cards and six expanded details browser-checked, no broken images/JS errors.
Exact current and history images are the already visually inspected D-118 inputs.
Dashboard: http://127.0.0.1:8766/temporal_status.html

Do not tune these same frames again. No runtime integration, no new model flight.
Next return to the execution question: in cycle2, correct target-bound goals at
50/51s are replaced at52s by an exploratory gray-wall point. A bounded saved-state
component can hold the last accepted goal and ask whether SUPER/controller can
complete it. Use actual saved planner state/pose and no oracle steering, no model
calls. This separates unfinished motion from goal replacement before another
architecture change. Success at an intermediate waypoint is not mission success.

Dedicated11435 unloaded/stopped; main11434 and Valley8765 untouched. Flight count
remains2/4; saved-frame calls15 total. Freeze commit91009be. No runtime changes
since401 passing unit tests. All evidence retained, including the failed criterion.
