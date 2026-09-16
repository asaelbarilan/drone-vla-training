# Cached SmolVLM and expanded local-data comparison

We used the already cached SmolVLM-256M-Instruct and expanded the experiment
on existing local data before admitting external data. Both models train and
reload successfully, but neither passes the full useful-pilot gate because
neither predicts the two tested terminal STOP commands.

## Frozen experiment (D136)

252 TRAIN examples (204 coordinate navigation,48 visual yaw),84 VAL
(68 coordinate,16 visual), preserving original scene-group splits. The same
400-example schedule trains fresh language-only rank8/alpha32 adapters:
200 updates at2e-4,200 at5e-5. No external data, cloud, paid APIs or physical
flights. Seeds1-40 and1060-1064 were not used. Final step400 was fixed before
validation; the better step200 validation loss was not used to select a model.
Smol uses BF16, Qwen NF4; native processors/tokenizers differ.

Smol first passed the separate tiny correctness gate:16/16 TRAIN examples
exact after400 updates, with identical save/reload. This is memorization only.

## Results on fixed validation probes

| Measurement | Smol256 | Qwen4B |
|---|---:|---:|
| Valid output |28/28|28/28|
| Exact full action |4/28|4/28|
| Visual direction with zero translation |8/16|16/16|
| Both instructions correct within a pair |0/8|8/8|
| Both color swaps correct within a pair |0/8|8/8|
| Direction correct with blank image |8/16|8/16|
| Direction correct with blank instruction |7/16|0/16|
| Tested terminal STOP correct |0/2|0/2|
| Coordinate velocity MAE (m/s) |0.3342|0.0608|
| Coordinate yaw MAE (rad/s) |0.1367|0.0703|
| Optimization time (seconds) |140.4|466.8|
| Peak PyTorch allocation (decimal GB) |1.050|4.546|
| Median final generation (seconds) |2.094|3.688|

Smol emits the same clockwise action on all16 visual cases; blanking the
image changes none. Qwen responds to image and instruction counterfactuals,
but its turn magnitudes remain approximate. Execution of these saved actions
for0.2 simulated seconds reduces target bearing error in8/16 Smol scenes and
16/16 Qwen scenes. These are single-action diagnostics, not full visual flights.
Independent audits check source pixels, commands, dynamics and resulting images.

Training and validation losses are in [mixed_loss_curves.png](mixed_loss_curves.png)
and in the expandable loss section of the prediction viewer.
Loss falls without guaranteeing useful actions: ordinary answer-token CE
includes many syntax tokens, STOP is sparse, and model tokenizers differ. Weighted training
loss emphasizes the action values. Do not rank models by absolute CE alone.

## Review and limitations

Prediction review: http://127.0.0.1:8771/local_mixed_predictions.html
Choose model, example and before/after/blank-input condition. Original source
images, exact prompts, target, raw prediction, physical setpoint and resulting
visual image are retained.176 browser assertions pass.

Only two visual and two coordinate validation scene groups support these
numbers. This is a pipeline diagnostic, not a generalization benchmark.
Generation is far slower than the0.2s action horizon; flight diagnostics pause
simulation during inference. Real-world and other-simulator readiness is untested.

Next local experiment should isolate the failures before importing data:
verify Smol can overfit visual contrast pairs alone, test balanced STOP/HOLD/
motion sampling with a fresh adapter, then expand independent local scenes and
longer visual rollouts. Freeze the next protocol before training, retain these
splits, and do not tune on protected seeds. External simulated and real-flight
data remain required later under D127, with license/calibration/action audits.

## Reproduction and artifact locations

- Dataset: `D:/drone_vla_pilot/data/local_mixed_20260917_v1`.
- Cached base: `HuggingFaceTB/SmolVLM-256M-Instruct`, revision
  `7e3e67edbbed1bf9888184d9df282b700a323964` (image-only, not SmolVLM2).
- Final adapters: `D:/drone_vla_pilot/runs/{smol256,qwen}_mixed_20260917_a/adapter_s400`.
- Reports retain the exact base paths, train/validation IDs, native input
  lengths, raw generated answers, intervention answers and reload spots.
- `mixed_manifest.json` fixes source hashes, index hash and all400 training IDs.
- `qwen_execution_audit.json` and `smol_execution_audit.json` validate executed
  IDs, finite nonzero gradients and train/validation separation.
- `scripts/build_local_mixed_dataset.py` reproduces the frozen union;
  `data_reproduction.json` records identical manifest/index hashes.
- `scripts/run_local_mixed_vla.py --model smol256|qwen --data DATA --gate GATE
  --out NEW_DIRECTORY` runs the frozen protocol using the local venv_qwen.
- `scripts/execute_saved_visual_predictions.py` executes final saved visual
  actions without making new model calls; `audit_saved_visual_execution.py`
  independently verifies coordinate signs, commands, dynamics and images.
- `scripts/build_local_mixed_review.py` rebuilds the generated review page;
  `scripts/check_local_mixed_review.py` checks all176 browser cases.

The4 reload checks in each mixed run are representative spot checks, not a
claim of all28 predictions reloaded. Tiny Smol used full16/16 reload checks.
Peak memory measures PyTorch allocation, not total GPU occupancy. Reported
optimization seconds exclude loading, validation and generation diagnostics.
