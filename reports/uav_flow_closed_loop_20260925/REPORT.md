# Qwen3-VL-4B drone VLA on UAV-Flow: training and closed-loop evaluation

Date: 2026-09-25. Branch `codex/vla-aws-pilot-20260916`, decisions D158–D164 in
`CHANGES.md`. This file is the self-contained record of the first model we
trained end to end and flew in the official UAV-Flow closed-loop simulator.

## 1. Headline

On 100 closed-loop UAV-Flow-Sim tasks (10 per motion class), our LoRA adapter on
Qwen3-VL-4B reaches **mean nDTW 0.129**. The released OpenVLA-UAV checkpoint,
run through the identical harness, reaches **0.395** and wins 77 of 100 paired
flights. Our model is better only on Retreat. It was trained on 1,987 **real**
flights and never saw simulator data; the released model's action statistics are
the simulator (`sim`) ones.

| Motion class | OpenVLA-UAV (released, 7B) | Ours (Qwen3-VL-4B + LoRA) |
|---|---|---|
| Turn | 0.176 | 0.154 |
| Move | 0.121 | 0.044 |
| Shift | 0.675 | 0.106 |
| Rotate | 0.349 | 0.110 |
| Surround | 0.753 | 0.001 |
| Ascend/Descend | 0.775 | 0.057 |
| Approach | 0.389 | 0.320 |
| Retreat | 0.293 | **0.355** |
| Pass | 0.252 | 0.134 |
| Land | 0.167 | 0.004 |
| **Mean nDTW (100 tasks)** | **0.395** | **0.129** |
| Median steps flown | 50 | 26 |
| Median end distance to reference end | 0.61 m | 2.62 m |

nDTW is the official automatic metric (`UAV-Flow-Eval/metric.py`, unchanged
functions). The papers' headline number is a human-judged success rate
(OpenVLA-UAV 65.6%), which is a different metric and is not reported here.

## 2. The model

| Item | Value |
|---|---|
| Base model | `Qwen/Qwen3-VL-4B-Instruct` (Hugging Face), loaded in bf16 (no quantisation) |
| Adapter | LoRA, rank 32, alpha 32, dropout 0, bias none |
| LoRA targets | all linear layers of language model, vision tower and merger (`q/k/v/o_proj, gate/up/down_proj, qkv, attn.proj, linear_fc1/2`) |
| Trainable parameters | LoRA only; base frozen |
| Action head | none added: actions are 256-bin tokens on the last 256 vocabulary ids (OpenVLA scheme), spliced by id |
| Output per call | K = 8 future steps x 4 values = 32 action tokens + EOS |
| Adapter files | `D:\drone_vla_pilot\release\qwen3vl4b_uavflow_k8_10shard_s2500\` (also on the AWS disk, `~/runs/official_k8_10shard/adapter_s2500`) |

## 3. Data

| Item | Value |
|---|---|
| Source | UAV-Flow real-world set, `wangxiangyu0814/UAV-Flow`, shards `train-00000` … `train-00009` of 54 |
| Flights read | 5,000 |
| Split | site-disjoint unseen split: validation holds out whole 300 m sites; any training flight whose instruction wording also appears in validation is dropped |
| Train / validation / dropped | 1,987 / 791 / 2,222 flights |
| Train frames | 133,637 (153,507 with the official first/last-frame x5 oversampling) |
| Train examples after mirroring | 307,014 |
| Format | official OpenVLA-UAV `uav_dataset.py`, ported and verified: 0 mismatches over 5,000 flights |
| Action | (dx, dy, dz, dyaw) in the drone's current local frame, from `raw_logs` [0,1,2,4], yaw deg→rad, last frame's action zero |
| State in prompt | `preprocessed_logs` [0,1,2,4] (start frame, metres, yaw in degrees), rounded to 0.1 |
| Prompt | `Current State: {x,y,z,yaw}, What action should the uav take to {instruction}?` |
| Instruction wording | both `instruction` (free) and `instruction_unified` (template), alternating by frame |
| Horizon | K = 8 steps (1.6 s at 5 Hz); padded with zero actions past the end of a flight |
| Action range | per channel 0.1/99.9 percentiles of training actions (official is 1/99): q_low [-0.544, -0.442, -0.133, -0.457], q_high [1.188, 0.442, 0.193, 0.276]; 256 uniform bins on [-1, 1] |
| Augmentation | left-right mirror copy of every example: image flipped, dy and dyaw negated, side words swapped (left↔right, clockwise↔counterclockwise); verified that a mirrored chunk integrates to the mirrored path |
| Images | frames stored as 256 px thumbnails (JPEG q92) |
| Data manifest | `data_manifest_10shard.json` (sha256 of the episode file included) |

## 4. Training

| Item | Value |
|---|---|
| Hardware | 1 x NVIDIA A10G 24 GB (AWS g5.2xlarge), peak 12.7 GiB |
| Batch | 8 per step x 4 accumulation = 32 examples per update |
| Updates | 2,500 (80,000 examples ≈ 0.26 epoch of the mirrored set) |
| Optimiser | AdamW, lr 5e-4, cosine schedule with 3% linear warm-up, gradient clip 1.0 |
| Gradient checkpointing | on (non-reentrant) |
| Wall time | ≈ 4.2 h (≈ 6.0 s per update), about $5 |
| Tracking | Weights & Biases, run `asael/vla training/official_k8_10shard` |
| Code | `scripts/train_uav_flow_vla.py --format official --chunk 8 --precision bf16 --instruction both --mirror --batch-size 8 --accum 4 --workers 6 --updates 2500 --schedule cosine` |

Loss (token cross-entropy on the 33 answer tokens): train 10.57 → 2.55.
Held-out loss (128 fixed validation examples), every 250 updates: 11.02, 2.94,
2.80, 2.72, 2.70, 2.64, 2.61, 2.60, 2.58, 2.57, 2.566 — still falling at the end,
no overfitting (a 1-shard run overfit after about 1.3 epochs).

## 5. Offline evaluation (before the simulator)

150 unseen-site validation flights, open loop (recorded frames and states),
endpoint error after integrating the predicted chunks:

| Condition | Median endpoint error |
|---|---|
| Representation floor (true actions through the tokeniser) | 0.072 m |
| Real photos | 3.067 m |
| Flat gray photos | 3.115 m |
| Photos from a different flight | 3.121 m |
| Text-only nearest-neighbour baseline | 4.533 m |
| No-text mean-path baseline | 4.208 m |

The adapter beats both text baselines, but the camera contributes only about
5 cm (gray sign test p = 0.29, swap p = 0.085). A mirror probe (60 flights x 3
frames; does the action change when the photo is mirrored?) rose over training:
0% at update 250, 11% at 500, 19% at 1,000, 14% at 1,500, 12% at 2,000, 26% at
2,500. The released OpenVLA-UAV changes its action in 16 of 20 cases.

## 6. Closed-loop evaluation setup

| Item | Value |
|---|---|
| Benchmark | UAV-Flow-Eval (github.com/buaa-colalab/UAV-Flow), DowntownWest map |
| Simulator | UnrealZoo `Collection_WinNoEditor_0424_25` (official Windows build) |
| Machine | AWS g6.xlarge, NVIDIA L4 24 GB, Windows Server 2022, GRID driver 596.86 |
| Tasks | 100 of the 273 test tasks: the first 10 (sorted by file name) of each of the 10 classes |
| Episode limit | 100 executed steps, or 10 consecutive near-still steps (official rule) |
| Our server | `scripts/uav_flow_eval_server.py` (official HTTP protocol). Model outputs metres; the simulator uses centimetres, so the state is divided by 100 into the prompt and each step multiplied by 100. The 8 predicted steps are integrated in the drone frame and returned as 8 poses; a new image is taken only after each chunk |
| OpenVLA-UAV server | same file, official maths (one step per call, `unnorm_key="sim"`), bf16 + eager attention (official uses flash-attention) |
| Local changes to the evaluator | render frame rate capped (`t.MaxFPS 10`); offscreen rendering (the instance has no desktop) |
| Known quirk kept as-is | the official evaluator passes UnrealCV's BGR image to PIL as RGB (orange sky) — both models see the same images |
| Model calls | OpenVLA-UAV 5,463; ours 404 |
| Scoring | `scripts/score_uav_flow_sim.py` (official nDTW functions + end distance / yaw) |

Invalid attempts, kept for the record and not used: the Linux UnrealZoo build
(`Collection_v4`) never moved the camera with the drone (every task's first frame
identical); a laptop run froze the 8 GB GPU; our first Windows attempt had a
missing library and made no model calls.

## 7. Caveats for a publication

1. **Domain gap.** Trained on real flights, evaluated in simulation. The released
   baseline carries simulator action statistics. This is the most likely cause
   of the gap and must be stated, not hidden.
2. **Subset.** 100 of 273 tasks, first 10 per class — not the full benchmark.
3. **Metric.** nDTW only; no success rate (needs human judgement or a validated
   automatic rule).
4. **Units.** The metre-to-centimetre conversion is inferred from the released
   model's action statistics (forward q99 ≈ 48.7 per step), not documented by
   the authors.
5. **Undertrained.** 0.26 epoch of 10 of 54 shards; held-out loss still falling.
6. **Single seed**, single checkpoint (update 2,500).
7. **Evaluator changes** (frame-rate cap, offscreen) affect rendering speed, not
   the images; the released baseline ran under the same changes.

## 8. Files

| File | Content |
|---|---|
| `REPORT.md` | this description |
| `closed_loop_ours.json` | per-flight and per-class scores, our adapter |
| `closed_loop_openvla_uav.json` | the same for OpenVLA-UAV |
| `data_manifest_10shard.json` | data split, counts, action statistics, checksums |
| `adapter_config.json` | exact LoRA configuration |
| Flight logs and plots | `D:\drone_vla_pilot\runs\sim_eval_win\{qwen,openvla}\flights\` and `s3://vla-eval-artifacts-512068640697/results/` |


## 9. Update D165 (2026-09-25): adding simulator flights

The domain-gap explanation was tested directly. The adapter above was trained
for 2,000 more updates on real + UAV-Flow-Sim flights and flown on the same 100
tasks.

**Simulator data.** `wangxiangyu0814/UAV-Flow-Sim`, 21 shards, 10,109 flights.
Leak check against the 273 test tasks: only 1 test task had a simulator flight
with the same start (<0.5 m) and the same instruction; 54 had a simulator flight
starting within 0.5 m. Every simulator flight starting within 0.5 m of any test
start was removed (168), leaving 9,941 flights / 307,834 frames. The simulator
data is recorded in the same town (DowntownWest) as the tests, so this is a
same-environment, disjoint-trajectory evaluation. Simulator positions are in
centimetres and were divided by 100 to match the real data; the action range
(section 3) was kept, and 5.6% of simulator steps fall outside it.

**Training.** Initialised from the section-2 adapter (update 2,500), fresh AdamW,
lr 2e-4 cosine with 3% warm-up, 2,000 updates x 32 examples, same K = 8, mirror,
both wordings; 1,121,502 training examples (real + simulator, mirrored), about
3.4 h on one A10G. Train loss 2.23 -> 1.19; held-out loss on the REAL unseen
split 2.565 -> 2.582 (unchanged). Adapter:
`D:\drone_vla_pilot
elease\qwen3vl4b_uavflow_k8_realsim_s2000\`.

**Closed loop, same 100 tasks (mean nDTW; one empty flight counted as 0):**

| Motion class | OpenVLA-UAV | Ours, real only | Ours, real + sim |
|---|---|---|---|
| Turn | 0.176 | 0.154 | 0.120 |
| Move | 0.121 | 0.044 | 0.020 |
| Shift | 0.675 | 0.106 | 0.664 |
| Rotate | 0.349 | 0.110 | 0.259 |
| Surround | 0.753 | 0.001 | 0.612 |
| Ascend/Descend | 0.775 | 0.057 | 0.721 |
| Approach | 0.389 | 0.320 | 0.343 |
| Retreat | 0.293 | 0.355 | **0.467** |
| Pass | 0.252 | 0.134 | 0.142 |
| Land | 0.167 | 0.004 | 0.051 |
| **Mean** | **0.395** | **0.128** | **0.333** |
| Median steps / end distance | 50 / 0.61 m | 26 / 2.62 m | 34 / 1.29 m |

Simulator data lifts the adapter from 0.128 to 0.333 (better than the real-only
adapter on 69 of 100 flights), which confirms the domain gap as the main cause.
It is now within 0.06 of the released 7B model (theirs better on 62 of 100) with
a 4B model that shares its weights with the testbed's VLM, and it beats it on
Retreat. Still weak: Land, Move, Turn, Pass. Files:
`closed_loop_ours_real_sim.json`, `training_report_real_sim.json`,
`sim_data_added.json`.
