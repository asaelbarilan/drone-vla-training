# Drone VLA training: what we are doing, what we found, what is decided

Status as of 2026-09-21. This is the orientation document for the drone
vision-language-action (VLA) work: the literature it rests on, the data, the
training runs, the measurements, and every decision taken with the reason for it.

Per-decision detail lives in `CHANGES.md` (D-numbered entries) and in the report
directories named at the end. `AGENTS.md` holds the current next steps. This file
is the map, not a replacement for either.

---

## 1. The goal, and the one rule

Train a small vision-language-action model that flies a drone from a natural
language instruction and a camera image, and measure honestly whether it works.

**The standing rule, learned the hard way:**

> Every model number is reported beside two others — the same model with its
> images replaced by flat gray, and a baseline that uses the instruction text
> with no image at all. A model number alone is not a result.

Section 4 is why.

---

## 2. Hardware and what it rules out

| | |
| --- | --- |
| GPU | one NVIDIA RTX 4060 Laptop, 8 GB VRAM |
| Storage | `D:` with ~890 GB free; all data and runs live under `D:/drone_vla_pilot` |
| Cloud | none used. No AWS resource has ever been started by this project |

8 GB is the binding constraint on everything below. It permits LoRA fine-tuning
of 256M–500M models comfortably, 4-bit *inference* on a 7B model (openfly-agent-7b
runs at 5.5 GB peak), and **not** LoRA fine-tuning of a 7B model. Section 8 is
where that bites.

---

## 3. The literature

15 aerial learned-action architectures were audited, plus 3 aerial benchmarks and
1 boundary case, screened from 31 candidates. Full matrix in
`docs/research/vla_results_audit_20260919/`.

### What they report

| architecture | reported result |
| --- | --- |
| OpenFly | 34.3% seen / 22.6% unseen flight success; 26.09% real flights |
| CognitiveDrone | 59.6% → 77.2% cognitive benchmark, with reasoning assistance |
| RaceVLA | 79.6% visual / 45.5% semantic, real tests |
| AutoFly | 47.9% simulation; 60% indoor / 55% outdoor real |
| AerialVLA (Xu) | 47.96% seen / 37.58% unseen maps |
| SpatialFly | 38.54% seen / 13.57% unseen maps |
| LongFly | 36.39% seen / 11.27% unseen maps |
| FLIGHTVLA | 59% Flow tasks; 13.5% fine-grained navigation |
| WorldVLN | 79.12% Flow; 41.76% IndoorUAV-VLA |
| ImagineUAV | 13/20 real flights with planner vs 9/20 without |
| Exp2VLA | 65% π0.5 / 15% SmolVLA, multi-object simulation |
| FSD-VLN | 26.7% seen / 13.6% unseen, urban split |
| UAV-Track VLA | 61.76% seen / 55% unseen, simulation |
| VLA-AN | 98.1% object navigation; evaluation details incomplete |
| GRaD-Nav++ | 16/24 trained / 6/12 unseen, real two-stage tasks |

### Three things this table is not

1. **Not a leaderboard.** These are authors' own numbers on their own setups.
2. **Not one task.** Action interfaces range from discrete primitives, through
   velocities (vx, vy, vz, yaw rate) and 3D waypoints, to dense trajectory chunks.
   A success rate means a different thing in each row.
3. **Not uniformly reproducible.** Several have no verified code or weights.

### Where cross-paper comparison is actually possible

Only two clusters share a benchmark:

- **UAV-Flow / Flow-Sim** — WorldVLN 79.12%, ImagineUAV 70.9%, FLIGHTVLA 59.0%
- **OpenUAV / TravelUAV** — AerialVLA 47.96%, SpatialFly 38.54%, LongFly 36.39%
  (two of the three have no verified code or weights)

This is why UAV-Flow was chosen in section 6.

---

## 4. Phase 1 — OpenFly, and why its metric failed

### What was trained

Three models were jointly fine-tuned on OpenFly data plus our local simulator
data: SmolVLM-256M, SmolVLM-500M, and Qwen. 400 LoRA updates each, 2,929 native
plus 1,156 local training examples, 110 routes split 88 train / 22 validation.
Completed 2026-09-17. Adapters are at
`D:/drone_vla_pilot/runs/{smol256,smol500,qwen}_joint_20260917_a/adapter_s400/`.

### The metric

Next-direction agreement on a 72-decision panel, balanced at 12 examples per
recorded direction across 21 routes and 11 environments. Each decision gives the
model three causal frames plus the route instruction; it picks one of six
primitives.

### The scores that started the investigation

| model | correct | valid |
| --- | --- | --- |
| openfly_vla (released 7B) | 20/72 | 48/72 |
| smol256 | 20/72 | 72/72 |
| smol500 | 21/72 | 72/72 |
| qwen | 24/72 | 72/72 |

The released model appeared to lose to our tiny fine-tunes. Three things were
wrong with that reading.

### Finding 1 — the released model is charged for unparsed output

24 of openfly_vla's 72 outputs did not decode under the `vlnv11` profile and were
scored as wrong. On the 48 that parsed it is 20/48, the best of the four. Its
decoder calibration is still unresolved.

### Finding 2 — the panel cannot separate anything

A constant "forward" answer scores 12/72 by construction. All four models sit at
20–24 with fully overlapping confidence intervals.

### Finding 3 — a no-vision oracle beats every model

The instruction is identical for every step within a route: 21 distinct
instructions across 72 decisions. An oracle that ignores every image and answers
each route's single most common action scores **36/72** — above all four models.

**Conclusion, recorded as D152:** next-direction agreement on this panel cannot
rank these models. It is not flight success, and it rewards a text prior as
readily as grounding.

---

## 5. The blind control — the method that produced the above

Every model answers the same panel twice: once with real frames, once with every
frame replaced by flat gray (127,127,127). Same prompts, same checkpoints, same
greedy decoding. If blinding does not change the score, the score was not coming
from the camera.

Before interpreting anything, the harness was verified: smol256 and openfly_vla
reproduced the stored predictions exactly (72/72 identical action ids; openfly_vla
also 72/72 identical action tokens), and all 216 frames were SHA-256 checked.

| model | real | gray | answers changed | McNemar p |
| --- | --- | --- | --- | --- |
| openfly_vla | 20/72 | 10/72 | 35/72 | **0.021** |
| smol256 | 20/72 | 15/72 | 64/72 | 0.49 |
| smol500 | 21/72 | 14/72 | 64/72 | 0.25 |
| qwen | 24/72 | 20/72 | 55/72 | 0.60 |

Only the released model's score depends on the image — right because of vision on
13 cases against 3 the other way. Our three adapters move 55–64 of 72 answers when
blinded, but roughly symmetrically: pixels perturb the decision without making it
more correct.

**The ranking was inverted with respect to grounding.** Qwen led while
contributing nothing measurable from vision; openfly_vla trailed while being the
only grounded model.

Viewer: `reports/vla_dataset_review_20260916/blind_control.html` — all 21 routes,
every decision, the frames each model received, four models under both conditions.

---

## 6. Phase 2 — UAV-Flow

### Why this dataset

Three separate papers report on it, so cross-paper comparison is possible. Its
instructions are single free-form goals rather than step-by-step route listings,
and its actions are continuous real-flight trajectories rather than a menu of
primitives. Both properties directly address the failures in section 4.

### The two datasets

| | `wangxiangyu0814/UAV-Flow` | `wangxiangyu0814/UAV-Flow-Sim` |
| --- | --- | --- |
| content | real flights | simulated flights |
| size | 240 GB, 54 parquet shards | 33.5 GB, 22 files |
| license declared | **none** | **none** |

The published 79.12% / 70.9% / 59.0% numbers are on **Sim**, evaluated
closed-loop. We downloaded one 4.7 GB shard of the **real** set.

The code repository `buaa-colalab/UAV-Flow` is Apache-2.0, but neither dataset
declares a license of its own. Public and ungated is not a license. **This is
unresolved and blocks publication of any result built on it.**

### Vocabulary

- **Shard** — one of 54 parquet files the dataset is split into. Purely a
  storage chunk.
- **Episode** — one flight: one instruction, one take-off, one landing.
- **Frame** — one camera photo, saved about 5 times a second.
- **Step** — the move between two consecutive frames.

Our downloaded shard: 500 episodes, 34,018 steps, about 68 steps per flight.
A typical step is ~9 cm of translation.

### Record structure

Each row is one frame, carrying `id`, `frame_idx`, `image`, and a `log` JSON with:

| field | meaning |
| --- | --- |
| `instruction` | free-form command, e.g. "Make way to the road sign from the left side" |
| `instruction_unified` | normalised phrasing of the same |
| `raw_logs` | absolute pose per timestep plus a Unix timestamp |
| `preprocessed_logs` | 6-DoF pose **relative to the start**, one row per step |

"6-DoF" is six degrees of freedom: three translations (forward/back, left/right,
up/down) and three rotations (roll, pitch, yaw).

---

## 7. What we built and what it measured

### The split

500 episodes, 412 train / 88 validation, split by SHA-256 hash of the episode id
so it is stable and order-independent. Verified: **zero** episodes have steps in
both splits. 47 of 59 validation instructions also appear in training — not flight
leakage, but it is exactly what the text baseline exploits.

### Baselines, computed before any training

Predicting a validation endpoint with no image at all, using training episodes
only:

| predictor | median final-position error |
| --- | --- |
| global mean, no text at all | 5.79 m |
| mean of training episodes with the same instruction | **2.26 m** |
| (median validation trajectory length, for scale) | 7.34 m |

**2.26 m is the bar.** A model that cannot beat it is not earning its vision.

### D153 result — endpoint pilot

SmolVLM-256M + LoRA, 400 updates, first frame + instruction → final displacement.

| condition | median final error | distinct answers |
| --- | --- | --- |
| model, real frames | 3.21 m | 56 / 88 |
| model, blinded | 6.47 m | 6 / 88 |

Paired sign tests over the 88 validation episodes:

- versus blinded: better on **62 of 83**, p = 7.5e-06
- versus the text-only baseline: better on **30 of 88**, p = 0.0037

**Reading:** the task format works — this is the first model in this project whose
score demonstrably depends on the camera. But it loses to a trivial instruction
lookup, significantly. That is a scale result, not a verdict on the approach, and
it is not to be reported as a success.

### Harness defects found and fixed

Every one of these was in the measurement code, not the model:

1. A loose parser searched anywhere in the output, scraped digits out of prompt
   text the untrained model echoed back, and scored a 1049 m "prediction" instead
   of reporting a failure.
2. Its strict replacement required an exact full match. The model emits a trailing
   fourth number because no end-of-sequence token was ever trained, so all 88
   predictions were discarded as unparsed. Fixed by anchoring to the start of the
   output and training an EOS token.
3. The manifest builder hashed a shard prefix via `read_bytes()`, pulling 4.6 GB
   into memory. Fixed to read one megabyte.

Reported numbers come from a separate scoring pass over the saved adapter, not
from the training loop's own counters.

### D154 — next-step 6-DoF rebuild

The endpoint task was a reduction chosen to match an already-computed baseline. It
is not the shape UAV-Flow is modelled with, and it left only 412 training
examples. The rebuild makes every step an example: current frame plus instruction
→ the 6-DoF step to the next frame, in the episode's start frame.

- 34,018 steps, **28,304 train / 5,714 validation**, same episode split
- rollout evaluation: sum predicted steps from frame 0, compare the endpoint to
  the recorded endpoint, so the 2.26 m bar still applies
- body-frame actions would need the dataset's rotation convention, which is
  undocumented and is not guessed at

Data is built. Training not yet run.

---

## 8. The official recipe, and the gap to our hardware

Found 2026-09-21 in `github.com/buaa-colalab/UAV-Flow` (Apache-2.0). **A complete
recipe exists and our scripts were written without it.**

| piece | official implementation |
| --- | --- |
| data prep | `dataset_tools/prepare_data.py` — parquet → per-episode folders of JPEGs plus `log.json` |
| training | `OpenVLA-UAV/` — an OpenVLA fork, `vla-scripts/finetune_uav.sh` |
| inference server | `vla-scripts/openvla_act.py` |
| evaluation | `UAV-Flow-Eval/` — closed-loop in UnrealZoo Gym / UnrealCV |

Their published training configuration:

```
openvla-7b base, LoRA rank 32, batch_size 2, grad_accumulation_steps 1,
learning_rate 5e-4, image_aug False, 8 GPUs (--nproc-per-node 8)
```

Their evaluation is closed-loop in the DowntownWest campus environment of the
packaged UnrealZoo build, **tested on Windows**.

### What this means for us

1. **Our data prep is equivalent** — per-episode folders of JPEGs plus the log,
   the same shape as `prepare_data.py`. No change needed.
2. **The training recipe does not fit our GPU.** It fine-tunes a 7B model across
   8 GPUs. One 8 GB card cannot do that. Our 256M/500M substitution is a
   deliberate downscale and must be described as one — it is not the published
   method, and no number from it is comparable to a published number.
3. **Their evaluation is closed-loop and Windows-packaged.** This is the first
   piece of good news on the simulator front: the D151 blocker was a Linux/WSL
   renderer for OpenFly, and UnrealZoo ships a Windows build. Closed-loop
   evaluation may be reachable here without any cloud machine.
4. **The published numbers are on the Sim set**, not the real set we downloaded.
   Comparing to them requires the 33.5 GB Sim dataset and their closed-loop
   harness.

---

## 9. Decisions taken

| # | decision | reason |
| --- | --- | --- |
| 1 | Stop using next-direction agreement to rank models | A no-vision oracle scores 36/72, above all four models (§4) |
| 2 | Report a blind control and a text-only baseline beside every model number | Three of four models showed no vision benefit that the headline metric revealed (§5) |
| 3 | Move to UAV-Flow | Three papers share it; free-form goals; continuous actions (§6) |
| 4 | Compute the baseline *before* training | 3.21 m sounds fine until you know text alone gets 2.26 m (§7) |
| 5 | Predict next-step 6-DoF, not an endpoint | It is the modelled shape, and it turns 412 examples into 28,304 (§7) |
| 6 | Split by episode, never by step | A flight straddling the split would leak; verified zero do (§7) |
| 7 | Scale data before updates, and data before model size | The endpoint pilot was data-starved, not under-trained (§7) |
| 8 | No cloud spend | Nothing so far has required it; the renderer case is now weaker still (§8) |
| 9 | Downscale the model deliberately and say so | 8 GB cannot run the published 7B × 8-GPU recipe (§8) |

---

## 10. Open questions and blockers

1. **Dataset license.** Neither UAV-Flow nor UAV-Flow-Sim declares one. The code
   repo is Apache-2.0; that does not cover the data. Blocks publication.
2. **Comparability.** A rollout over recorded frames is not closed-loop flight.
   The published 79% / 70% / 59% numbers stay out of reach until their UnrealCV
   harness is running here. Do not claim otherwise.
3. **Model size.** The recipe wants OpenVLA-7B on 8 GPUs. Options are a deliberate
   small-model study, 4-bit training experiments, or cloud — none chosen.
4. **Frame history.** Our step policy sees a single frame. OpenFly gave its models
   three. Untested here.
5. **OpenFly decoder calibration.** 24 of 72 outputs still fail to parse under
   `vlnv11`. Unresolved, and it distorts any comparison involving that model.
6. **The paper's OpenFly section.** It must not present the 20/20/21/24 table as a
   ranking, and must not silently score unparsed outputs as wrong.

---

## 11. Where everything lives

| | |
| --- | --- |
| Current next steps | `AGENTS.md` |
| Per-decision history | `CHANGES.md`, `docs/RESEARCH_LOG.md` |
| Literature audit | `docs/research/vla_results_audit_20260919/` |
| OpenFly joint training | `reports/vla_joint_openfly_20260917/` |
| OpenFly decoder/alignment repair | `reports/vla_openfly_repair_20260918/` |
| Blind control (D152) | `reports/vla_blind_control_20260920/` |
| UAV-Flow text-only audit | `reports/uav_flow_text_only_20260921/` |
| UAV-Flow endpoint pilot (D153) | `reports/uav_flow_pilot_20260921/` |
| UAV-Flow next-step data (D154) | `reports/uav_flow_steps_20260921/` |
| Viewers | `reports/vla_dataset_review_20260916/*.html`, served on `localhost:8771` |
| Weights, data, runs | `D:/drone_vla_pilot/` |

Scripts, in the order a rebuild would run them:

```
scripts/prepare_uav_flow_pilot.py      # endpoint split + baselines (D153)
scripts/audit_uav_flow_text_only.py    # how much the instruction alone predicts
scripts/train_uav_flow_pilot.py        # endpoint pilot
scripts/score_uav_flow_pilot.py        # scores a saved adapter vs the baselines
scripts/prepare_uav_flow_steps.py      # per-frame next-step 6-DoF data (D154)
scripts/evaluate_joint_repair_controls.py   # OpenFly adapters, real or gray panel
scripts/evaluate_openfly_repaired.py        # released OpenFly model
scripts/build_blind_control_review.py       # builds the blind-control viewer
```

---

## 12. Lessons from the 19 audited works, applied to our training

Read before the next training run. Each lesson names the evidence and what it
changes for us. Sources are the per-work records in
`docs/research/vla_results_audit_20260919/evidence.json`.

### 12.1 Seen-to-unseen collapse is the field's dominant failure

| work | seen | unseen maps | drop |
| --- | --- | --- | --- |
| LongFly | 36.39% | 11.27% | -69% |
| SpatialFly | 38.54% | 13.57% | -65% |
| FSD-VLN | 26.7% | 13.6% | -49% |
| OpenFly | 34.3% | 22.6% | -34% |
| AerialVLA (Xu) | 47.96% | 37.58% | -22% |

**What it changes.** Our validation split shares 47 of 59 instructions with
training. That is a *seen* split, and any number from it is optimistic in exactly
the way this table describes. Before reporting anything as a result we need a
second split held out by instruction, and ideally by environment. Build it now,
not after the numbers look good.

### 12.2 Robotics-pretrained backbones beat VLM adaptations, consistently

| work | strong model | weak model |
| --- | --- | --- |
| Exp2VLA | pi0.5 84.1% / 65.0% | SmolVLA 46.6% / 15.0% |
| HUGE-Bench | pi0.5 TCR 0.581 | adapted OpenVLA 0.112 |
| IndoorUAV | fine-tuned pi0 27.16% | OpenFly-Agent 4.12% |

**What it changes.** Nothing about whether to run the small-model study, but
everything about how to frame it. SmolVLM-256M/500M and Qwen are the weakest
family in this literature. The study is "how far does a small VLM get", not "can
a small VLM win". Exp2VLA released only its pi0.5 weights, not its SmolVLA ones.

### 12.3 Almost nobody predicts one step at a time

| work | action unit |
| --- | --- |
| UAV-Track VLA | 25-step chunks of delta position and yaw |
| FLIGHTVLA | dense trajectory / action chunks |
| Exp2VLA | normalized vx, vz, yaw-rate action chunks |
| ImagineUAV | future video to 6-DoF motion to planner-refined trajectory |
| LongFly, SpatialFly | continuous 3D waypoints |
| UAV-Flow Colosseo | pose trajectories / action chunks with look-ahead |

**What it changes.** Our D154 design predicts a single next step. That is
off-pattern for the whole field, and single-step rollouts accumulate error over
~68 steps. Predict a chunk of K future poses instead, and roll out chunk by chunk.

### 12.4 The recorded poses are achieved motion, not commands

UAV-Flow Colosseo's own record states that recorded poses are achieved motion,
not automatically commanded velocities, and that its simulation success rate comes
from **manual inspection of whether the executed trajectory fulfils the
instruction** - not from an endpoint distance threshold.

**What it changes.** Two things. Training to predict these poses is imitating
outcomes rather than commands, which is a real caveat to state, not a bug to fix.
And our 2.26 m endpoint metric is *not* their metric - it is a local proxy, useful
for gating our own progress, and not comparable to any published success rate.

### 12.5 Stopping and history are separate learned signals

LongFly's record notes explicitly that history and stopping matter; its action
interface is "continuous 3D waypoints **and stop**". AerialVLA (Chen) carries
waypoint, stop and progress heads plus BEV history. OpenFly gives its models three
frames of history, as did our own D147 panel.

**What it changes.** Our step policy sees one frame and has no notion of finishing.
Add frame history, and treat termination as its own output rather than something
that falls out of the trajectory.

### 12.6 Headline numbers routinely include assistance

ImagineUAV: 13/20 real flights **with** a planner against 9/20 without.
CognitiveDrone: 59.6% base, 77.2% with the reasoning variant. VLA-AN's 98.1% is a
whole system including a depth-based safety module that adjusts unsafe
trajectories. AutoFly's record notes it is not pure zero-shot sim-to-real.

**What it changes.** Whenever we add a helper - a planner, a reasoning pass, a
safety filter - report with and without it, separately, as those papers did.

### 12.7 Real-flight denominators are tiny everywhere

OpenFly's real-flight 26.09% is 23 trials. ImagineUAV's is 20 flights.
GRaD-Nav++ reports 16/24 and 6/12. GRaD-Nav++'s simulation caption also disagrees
with its own printed denominators.

**What it changes.** Do not over-read any real-flight number, ours or theirs, and
state the denominator every time.

### Summary: changes to make before the next training run

1. Build a second validation split held out by instruction, and by environment if
   the field allows it (12.1).
2. Predict a chunk of K future poses rather than one step (12.3).
3. Feed frame history rather than a single frame (12.5).
4. Add an explicit termination output (12.5).
5. Describe the endpoint metric as a local gate, never as a success rate (12.4).
6. Frame the three-model run as a small-model study, not a bid to win (12.2).
