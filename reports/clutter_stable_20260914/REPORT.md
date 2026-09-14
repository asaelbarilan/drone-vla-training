# D-111: clutter diagnostic, first flight retained

c5_clutter_stable_20260914_s1061 times out at90 s, final37.906 m, closest22.583 m.
Zero collisions. Raw328 constraint violations require numerical/physical audit;
no safety conclusion from zero collisions alone. Historical corrected-depth seed1061
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
