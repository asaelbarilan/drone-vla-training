# FRD local VLA follow-up — 2026-09-16

The tiny overfit gate now passes. In the frozen two-scene offline comparison,
zero-shot completed0/2 and the trained adapter completed1/2. This is a diagnostic,
not a reliability estimate, architecture ranking or deployable drone policy.
No AWS, paid APIs or physical flights were used.

## What changed and why

D131 adds a distinct, heading-level FRD contract: forward/right/down velocity
and clockwise yaw rate. JSON keys are forward_bin,right_bin,down_bin,yaw_cw_bin,
stop.65bins span+-5m/s and+-1.5rad/s;32meanszero. Source yaw defines a level frame,
not the aircraft's tilted roll/pitch frame. STOP terminates the mission and is
not a landing command. Old FLU schema, corpus, checkpoint and baselines remain.
4096 conversion examples preserve physical commands;272converted labels and
816source images preserve splits/bytes. Original fixture hashes rechecked.

D132 diagnosis found syntax already correct while action values/STOP failed.
The new loss allocates90% across five action-value fields and10% to syntax;
examples shuffle within the same16TRAIN IDs. Rank8 language-only LoRA on pinned
Qwen3-VL4B, frozen NF4 base and vision encoder. Attempt b:200updates,13/16exact,
allSTOP/HOLD correct;gate failed. D134 allows one same-data convergence retry:
200more updates at5e-5 with fresh AdamW. Result16/16exact,allSTOP/HOLD,reload
identical,loss decreased;gate PASSES. Total optimization529.500s;peakPyTorch
allocation4.617GB on the local8GiB GPU. This demonstrates memorization only.

Loss evidence: [PNG](frd_losses.png) / [SVG](frd_losses.svg). The two panels
separate the weighted training objective from ordinary token cross entropy.
Both are TRAIN curves, not validation learning curves. All prior failures remain.

## Matched model flights

Same validation seeds1400/1405, initial image/prompt/environment/controller,
reset-start without teacher setup rotation,10simsec/50calls maximum. Same
pinned base, processor, strict FRD parser and deterministic greedy generation.
No validation feedback selected the overfit retry. Teacher only checks the
public goal/stop conditions;it never substitutes an action. STOP requires
within0.35m and speed<=0.1m/s. Simulation pauses for inference.

| Seed | Mode | Outcome | Final distance (m) | Calls |
|---|---|---|---:|---:|
| 1400 | zero_shot | timeout | 8.929 | 50 |
| 1405 | zero_shot | timeout | 8.619 | 50 |
| 1400 | trained | timeout | 3.630 | 50 |
| 1405 | trained | agent_stopped | 0.113 | 36 |

Median generation: zero-shot3.625s;trained3.969s,
versus0.2s action horizon. This remains a deployment blocker. Zero collisions
in these empty scenes is not a safety claim.1400 approaches then moves away;
1405 reaches the goal and emits a valid STOP. The coordinate/odometry task does
not require vision. Do not infer visual grounding from this successful flight.

[Flight curves PNG](flight_comparison.png) / [SVG](flight_comparison.svg).
Independent audit verifies186exact model mosaics/prompts,741decoded controls,
all replayed positions and final outcomes, plus matched initial conditions.
Separate image/control mutations are rejected. Browser checks12exact response/
image/prompt/source-time matches,all4outcomes,playback and responsive layout.
The first browser assertion assumed every outcome was a failure string;it was
corrected to check the existing Completed display for a successful saved result.
77focused contract/data/masking/debugger tests pass. No baseline code changed.

## Modest data expansion and limitations

64new visible-pillar yaw segments,48train/16val,8scene groups1410-1417.
32unique images each have opposite red/blue instructions;swapping colors
reverses the same instruction's label. Teacher uses exact mosaic pixels,
instruction and fixed camera calibration;hidden targets are rejected.
Independent replay checks320states,192source/after frames,256controls and
64paired checks. No cross-split exact-image duplicates. This verifies DATA
image/instruction dependence. The model has NOT trained on these pairs yet.
They are synthetic alignment primitives,not full navigation/search/recovery.

Five complete TRAIN preview sequences audited per external source:
UAV-Flow294frames;UAV-Flow-Sim237frames;10,007,986imagebytes total. All531image
hashes and native pose/log counts checked;start/middle/end visually inspected.
These are pinned HF viewer assets,not original parquet-byte validation.
Data-license fields are absent;camera calibration,units/axes/timing,command-vs-
achieved-motion labels and site/group split independence are unresolved.
ZERO external episodes admitted to action training. Native logs stay intact;
no invented downward camera or velocity-command conversion. Exp2VLA video
inspection and broad eight-regime data collection remain future work.

Data review verifies158exact browser frame/native-log checks across74entries
and659images (local before/after included). External playback5fps is display
cadence only;source timing has not been established.

## Review and reproduction

- Model comparison: http://127.0.0.1:8771/frd_comparison.html
- Data expansion: http://127.0.0.1:8771/data_expansion.html
- Preserved previous FLU flights: http://127.0.0.1:8771/model_flights.html
- Raw comparison: D:/drone_vla_pilot/runs/qwen_frd_comparison_20260916_a
- Adapter: D:/drone_vla_pilot/runs/qwen_frd_overfit_20260916_c/adapter
- FRD coordinate data: D:/drone_vla_pilot/data/public_goal_fixture_20260916_frd_v2
- Visual pairs: D:/drone_vla_pilot/data/visible_yaw_pairs_20260916_v3
- External previews: D:/drone_vla_pilot/external_samples_20260916_a

Scripts evaluate_qwen_frd_pair.py, audit_qwen_frd_pair.py,
check_qwen_frd_debugger.py reproduce the comparison and its inspection.
visual_yaw_fixture.py and audit_visual_yaw_fixture.py reproduce the local pairs;
build_vla_expansion_review.py rebuilds playback. Source revisions/hashes,
checkpoint hashes and preservation evidence are in adjacent JSON reports.
Use the isolated venv_qwen for model code and PYTHONPATH=src. Output directories
must be new;failed attempts are preserved.

## Remaining gates

Freeze a short mixed-task training protocol using audited labels;evaluate
learned image/instruction dependence and larger independent scene groups.
Address latency with an explicitly versioned action-head/chunk/control design
before real-time claims. Resolve external-source contracts and add full-task,
terminal,recovery,multi-environment and real-flight coverage per D127.
The current data is far too narrow for general real-world drone autonomy.

Seeds1-40 and1060-1064 remain excluded from development training. Original
splits/data/baselines and other-session services are preserved. Before paid
compute,seek user approval for exact machine,runtime,storage and maximum charge.
