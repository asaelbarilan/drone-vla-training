# Local VLA correctness pilot - 2026-09-16

The pipeline and actual Qwen QLoRA execution are verified; the learned policy fails the frozen overfit and flight gates. This is not a deployable VLA or architecture comparison. No AWS resource, paid API or long training was used.

## Evidence

- D128: 4096 codec/controller samples and128 paired physics segments; source-yaw level forward/left/up axes, explicit hold versus mission STOP.
- D129: eight public-coordinate teacher flights,272 observations,204train/68validation.1194 replayed controls/poses,1064 label/control checks and816 exact camera images. The task can be solved without vision.
- D130: pinned Qwen3-VL4B NF4,r8 language-only LoRA;200 optimizer updates in269.234s;16.5M trainable parameters;4.47GB peak PyTorch allocation on RTX4060 Laptop8GiB.
- Sixteen train-only examples;404-502 tokens; strict assistant-only loss. Mean loss first/last16 steps0.228933/0.058143.16/16 valid JSON,9/16 exact targets,0/4 STOP,4/4 HOLD,5/8 motion. Frozen overfit gate FAILED.
- Adapter save/reload gives identical16/16 greedy predictions. Median reload generation4.3355s versus0.2s action horizon. This is not a demonstrated real-time control loop.

## Actual model flight diagnostics

Simulation was paused during inference. Seeds1400/1405 are frozen validation scenes;1401 is a training-scene diagnostic. All start at reset, without teacher-only setup rotations. Maximum10 simulated seconds/50 calls per scene;15min combined wall cap. No validation feedback was used for further training.

| Seed | Split | Outcome | Final goal distance | Calls |
|---|---|---|---:|---:|
| 1400 | val | timeout | 2.952m | 50 |
| 1405 | val | timeout | 1.750m | 50 |
| 1401 | train_diagnostic | timeout | 8.003m | 50 |

All three fail. Two approach then stall; the training-scene reset remains in hold. Zero collisions in these empty diagnostic scenes is not a safety/generalization result. Full audit checks150 exact source mosaics/prompts and600 decoded/executed controls, plus exact trajectory replay. Modified-image and modified-control negative copies are rejected. Browser checks nine response/image/prompt/time matches, three terminal outcomes, playback and responsive layout.61 focused unit/regression tests pass.

## Review

- Model flights: http://127.0.0.1:8771/model_flights.html
- Teacher flights: http://127.0.0.1:8771/teacher_flights.html
- Original uncorrected corpus: http://127.0.0.1:8771/viewer.html
- Model raw runs: D:/drone_vla_pilot/runs/qwen_rollout_20260916_a
- Adapter: D:/drone_vla_pilot/runs/qwen_overfit_20260916_c/adapter
- Corrected fixture: D:/drone_vla_pilot/data/public_goal_fixture_20260916_v1

The existing debugger labels reconstructed views separately from exact saved model inputs. Input images, prompt, raw response, action evidence and measured inference latency are visible. Saved runs are replay, not live real flights.

## Next gates

Diagnose training-only numeric/STOP token errors and sample ordering, then freeze one bounded correction; do not use the validation outcomes to select it. No larger training run follows a failed tiny overfit gate. Resolve the4.3s/0.2s cadence mismatch before transfer claims. A typed action head or chunked horizon would be a separately declared interface change, not a silent patch to paper baselines.

The mandatory expansion plan remains docs/research/VLA_DATA_EXPANSION_PLAN.md. Only eight local coordinate episodes are admitted; zero real or external-simulator episodes. Small schema previews identify different raw log widths and missing command/calibration/license evidence. Next source audits are5 complete training flights per candidate before bulk download. Cover all eight paper regimes, multiple scenes/instructions and held-out domains; adjacent frames or disk size do not establish adequacy.

AWS remains off. Before launch and paid training, obtain approval for the exact machine, predicted duration, storage retention and maximum charge. Seeds1-40 and1060-1064 were excluded from training; original data, baselines and other-session services were preserved.
