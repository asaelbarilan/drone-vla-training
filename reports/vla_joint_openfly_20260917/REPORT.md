# D144 — Joint OpenFly/local three-model pilot

All three local runs completed 400 updates with separate saved/reloaded adapters.
No AWS spending. This completes the bounded experiment, not real-world qualification.

## Frozen held-out action results

| Model | Native base exact | Native trained exact | Native macro recall | Native valid | False STOP / 60 nonterminal | Local trained exact | Local valid |
|---|---:|---:|---:|---:|---:|---:|---:|
|smol256|0/72|18/72|25.0%|72/72|9/60|2/28|28/28|
|smol500|0/72|16/72|22.2%|72/72|5/60|2/28|26/28|
|qwen|16/72|17/72|23.6%|72/72|8/60|12/28|28/28|

Native panel: 12 examples for each of six actions; always-forward reference12/72
and macro recall16.7%. These are held-out routes selected from official TRAIN,
not the full official seen/unseen benchmark. Local panel is28 preserved cases,
not all300 local validation rows. Full per-class confusion is in summary.json.
Base format failures and exact JSON mismatches are not flight-success measures.

## Actual local simulation flights

- smol256, seed1400: timeout; success=False; distance=8.541m; 50 actual model calls.
- smol256, seed1405: timeout; success=False; distance=8.000m; 50 actual model calls.
- smol500, seed1400: timeout; success=False; distance=6.453m; 50 actual model calls.
- smol500, seed1405: timeout; success=False; distance=0.670m; 50 actual model calls.
- qwen, seed1400: false_stop; success=False; distance=2.097m; 33 actual model calls.
- qwen, seed1405: false_stop; success=False; distance=0.432m; 33 actual model calls.

Each model controls two local development flights, with simulation paused
during inference. Audits verify actual answers, source images, decoded controls
and replayed positions. Two flights/model are diagnostic, not statistical evidence.
OpenFly source clips are recorded dataset observations, not native model rollouts.

## Findings and next gate

All three models learn the output contracts, but native action accuracy remains
low. Qwen moves from16/72 native base to17/72 after training; this small panel
does not establish an improvement. All six local flights fail the frozen gate.
Smol256 holds at its initial pose; Smol500 moves but times out; Qwen ends both
missions outside the0.35m goal radius. Lower training loss is not sufficient.
All native validation losses are lowest at the measured100-update checkpoint
and worsen later. This is evidence against simply extending this same pilot.
Before a longer run, isolate visual/history dependence and action/mission-phase
ambiguity on training-only cases, then freeze a follow-up using broader unique
route coverage. Do not tune against protected seeds or the official test split.

## Interpretation limits

110 OpenFly routes:88TRAIN/22dev,2929/815 admitted decisions;8 inconsistent
motion labels quarantined. Local1156TRAIN/300VAL unchanged. Same400-update
schedule/model, four examples/source/update,1600 exposures/source; actual unique
coverage592native examples across all88TRAIN routes and790local examples.
Native classes are deliberately oversampled; repeated rare actions are not new data.
Native3m/30-degree primitives and local FRD velocity JSON retain explicit separate
instruction contracts. No guessed OpenFly velocity/duration labels were introduced.
Smol uses BF16 and QwenNF4, with different tokenizers/processors; absolute token
loss magnitudes are not cross-model quality rankings. No checkpoint selection
used validation; final400-step adapters are the evaluated outputs.
Real-time control, native OpenFly closed-loop transfer, physical drone data
coverage and real-world deployment remain open. Do not infer readiness from loss.

## Evidence

PROTOCOL.md; data_audit.json; preflight.json; exposure_audit.json;
*_training_report.json; *_flight_audit.json; *_flight_browser/model_ui_check.json;
summary.json; loss_curves.png/PDF. All original baselines and protected seeds preserved.
Live review: http://127.0.0.1:8771/joint_openfly.html
