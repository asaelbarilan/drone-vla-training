# Gemma 4 E2B comparison — 2026-09-07

## Result

Real Gemma 4 E2B completed 0/5 development missions: all timeouts, zero collisions, zero premature stops, zero monitor parse errors. Policy and monitor inference events identify gemma4:e2b in every run. This is a rejected capability gate, not proof that Gemma is generally worse.

| Seed | Outcome | Final distance (m) | Policy call (s) | Monitor call (s) |
| ---: | --- | ---: | ---: | ---: |
| 1060 | timeout | 57.46 | 0.347 | 0.687 |
| 1061 | timeout | 20.66 | 0.346 | 0.692 |
| 1062 | timeout | 30.35 | 0.342 | 0.689 |
| 1063 | timeout | 32.87 | 0.343 | 0.724 |
| 1064 | timeout | 47.83 | 0.385 | 0.834 |

Mean measured call latency: policy 0.353 s; monitor 0.725 s. Observed GPU residency at an 8192-token context: Gemma 1,712,586,751 bytes versus Qwen 4,235,345,264 bytes. This measures GPU residency, not total parameters, CPU RAM, or disk size.

The retained Qwen baseline scored 1/5. Its recent fence-only repeat succeeded on 1061 and timed out on 1060/1062; no fence recovery triggered on those three runs. Gemma did not improve success in this fixed setup. The five-seed Qwen target-bound-stop experiment scored 0/5 and regressed the positive control.

## What was held fixed

Gemma used the same pixel convention, camera/depth, planner, monitor mechanism, memory, native dynamics, 90 s horizon and development seeds. The backend and both agent model IDs were explicitly changed. Gemma uses the content channel with think=false and a 96-token output cap, sufficient for complete schemas. Qwen original baseline used 48; original monitor replies fit that cap. The normalized simulated latency remains fixed at policy 1.0 s / monitor 1.2 s, so this screen isolates decision behavior and records actual speed separately. It does not measure the potential navigation benefit of a faster Gemma-native schedule.

## Historical correction

The five c5_gemma_dir_s1060–1064 artifacts actually called Qwen for both roles. Their policy label said gemma3:4b, but the backend was qwen3-vl:4b and the inference events confirm it. D-71 supersedes D-68 as a model comparison. Do not attribute those results to either Gemma 3 or Gemma 4. The backend now rejects model-ID mismatches before HTTP; regression tests cover the historical error and both true Gemma profiles.

## Validation and remaining work

285 unit/contract tests pass after the identity guard; changed transport code and tests pass Ruff. Earlier CPU selection passed 380 tests with 20 deselected. No held-out model evaluation was performed. Boundary-long and combined-fix gates remain paused and unvalidated; Gemma target-bound profile passed its schema probe but has not flown. No new configuration is accepted.

Raw results: `GEMMA4_E2B_FIVE_SEED_20260907.json`. Request probe: `GEMMA4_E2B_CONTRACT_PROBE_20260907.json`. All raw flight artifacts are listed in the results JSON.
