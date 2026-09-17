# D139 - Balanced original versus expanded data: complete

Only cached image-only SmolVLM-256M was trained in this experiment, with two
data conditions. Earlier Smol500 and Qwen experiments are preserved; neither
was rerun here. Both D139 runs completed and passed exact checkpoint reload
checks. Neither passed the useful-pilot gate or completed a matched flight.

## Matched experiment

Fresh BF16 language-only LoRA rank 8 / alpha 32, seed 132. Identical initial adapter
hash,all 28 zero-shot outputs and all initial loss measurements.400 optimizer
updates/1,600 sample exposures each,one visual/motion/HOLD/STOP per effective
batch. Microbatch 1, accumulation 4, equal sample weighting,one clip/step. LR2e-4
for 200 updates, then a fresh AdamW optimizer at 5e-5 for 200. Both fixed step 400 endpoints retained;
no validation-selected checkpoint. Full original/new cohort losses at 0/200/400.

| Measurement | Balanced original | Balanced expanded |
|---|---:|---:|
| TRAIN pool | 252 | 1,156 |
| Unique examples actually exposed | 252 | 790 |
| Original VAL weighted action loss | 0.4171 | 0.4081 |
| New-scene VAL weighted action loss | 0.4835 | 0.4012 |
| Original valid generation probes | 27/28 | 27/28 |
| Original visual direction, no translation/STOP | 8/16 | 8/16 |
| New visual direction, no translation/STOP | 32/64 | 32/64 |
| Original instruction pairs correct | 0/8 | 0/8 |
| New instruction pairs correct | 0/32 | 1/32 |
| Original color-swap pairs correct | 0/8 | 0/8 |
| New color-swap pairs correct | 0/32 | 1/32 |
| All VAL STOP cases correct | 0/6 | 5/6 |
| All VAL HOLD cases correct | 14/18 | 11/18 |
| Premature STOP on nonterminal probes | 1/128 | 8/128 |
| Matched trained flights complete | 0/2 | 0/2 |
| Training/evaluation job wall time | 28.21min | 26.89min |
| Peak PyTorch allocated GPU memory | 0.903GB | 0.904GB |
| Median validation generation time | 2.3435s | 2.3280s |

Expanded data reduced new-scene loss by about 17% and improved terminal recall,
but introduced more premature stops and did not establish visual instruction
following. The one successful new visual pair does not make the 50% individual
direction result a useful visual policy. Blank-image changes 16/13 physical
outputs and blank-instruction changes 6/5 for original/expanded,without improved
paired behavior; image sensitivity alone is insufficient evidence of correct
visual grounding. No invalidity changes in these interventions.

New coordinate probes have valid-only velocity MAE 0.1118->0.0854 m/s,while
original probes worsen0.2083->0.2794 m/s. The main summary also retains the
predeclared maximum-range penalty for invalid outputs; do not interpret that
penalized MAE as an actual executed velocity. Some original STOP/format failures
persist despite low teacher-forced STOP loss. Free generation and flight are
therefore separate gates from loss minimization.

## Actual flights and executed actions

Original-data adapter:seed 1400 stops falsely after 7.25 simulated seconds, 1.9358 m from
goal;seed 1405 stops falsely after 5.65 s, 1.3908 m from goal. At the first STOP
request on 1400, the public-goal vertical error is about 1.79 m. This is a model
command/completion failure,not evidence that the frame-conversion audit failed.

Expanded-data adapter:seed 1400 repeatedly HOLDs at the start for 10 simulated seconds,
remaining 8.5407 m from goal;seed 1405 falsely STOPs immediately at 8.0001 m. No
collision in these runs does not imply useful navigation. Both zero-shot
references emit invalid first outputs and are rejected,with explicit recorded
failures and no teacher substitution.

Each condition's 16 original saved visual actions was executed for 0.2 s using
its exact source scene/image:8/16 reduce target bearing in each condition.
All 128 visual controls pass independent frame/dynamics/image audit. Across
all 8 flight runs,121 actual generations and463 controls are source/replay
audited. Starting prompt,image and environment match across conditions.
The controller executes the model's decoded output; teachers are evaluation
references only. Simulation pauses during inference:these are offline policy
checks,not real-time deployment tests. Median generation exceeds the0.2s action
horizon by roughly 12 times on this machine.

## Data, evidence and validation

D138v4 SHA256:7318727a1c23868e32ed8e5db9fadb07155c0e2421a85a66a8af01551641c064.
Original 84 VAL rows and 28 probes preserved; 216 new VAL rows are separate. All
134 generation probes were declared from data before training. New TRAIN pool
has 951 unique mosaics and 24 instruction strings,only TWO visual templates plus
22 public-coordinate goals.558 examples contain vertical commands;vertical motion
is not absent, but obstacle/search/recovery and richer instruction coverage is.
No external/real action rows admitted. No held-out 1-40 or protected 1060-1064
collection/training. One initialization and 16 VAL scene groups do not establish
a paper-level comparative success rate; these repeatedly used VAL sets are
development data,not an untouched final test.

Both schedules,raw responses,targets,validity/exact flags and four reload spots
are checked. D138's 53 data/action tests remain the pipeline evidence;D139's
scoring regression passes for perfect targets,constant-turn collapse,invalid
outputs,translation and STOP spam. Ruff and whitespace checks pass. Browser
QA: 388 exact image/prompt/output/physical-action checks,all 3 plot bytes,14 flight
source-time checks,8 outcomes, responsive layouts and playback;no JavaScript errors.

Artifacts:summary.json, *_report.json, *_flight_audit.json,
*_visual_audit.json, matched_artifact_audit.json and prediction_ui_check.json.
Weights/raw runs remain under D:/drone_vla_pilot/runs/smol256_balanced_*_20260917_a.
Final report/adapter hashes and measured latency ranges are pinned in the
matched artifact audit. Previous data/checkpoints/reports and paper baselines
remain intact. Both jobs and simulation evaluation exited successfully. No AWS
resources or spending were used.

Review: http://127.0.0.1:8771/balanced_comparison.html
Control flights: http://127.0.0.1:8771/balanced_control_flights.html
Expanded flights: http://127.0.0.1:8771/balanced_expanded_flights.html

## Before full training

Do not scale this recipe merely because aggregate loss improved. Next isolate
visual-only TRAIN memorization and matched instruction/color swaps;add targeted
HOLD-versus-STOP boundary contrasts and 3D goal-completion failures. Use these to
locate input/representation,loss/output-format and model-capacity limitations
before choosing a larger training budget. A matched Smol500/Qwen extension is a
separate next experiment,not already done by this comparison.

Then fill the paper's eight task categories,admit audited external-simulator
and real-flight action data,freeze scene/site/instruction/domain transfer splits,
and validate the target controller/timing interface. Dataset adequacy must be
measured by coverage and per-task/domain learning curves,not an assumed row
count or disk size. See FULL_TRAINING_GATES.md and D127. Before any paid cloud
launch/training,present the exact machine,storage retention and maximum charge
for the user's approval. Physical flights require a separate platform/flight
plan;offline simulation is not deployment validation.
