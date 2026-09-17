# D138 - Expanded local data and balanced effective batches

The additive dataset is audited and the real Smol256 accumulation path passes
its two-update GPU smoke test. No full comparison training or new learned-flight
result is claimed. This is still the same local renderer and narrow task family.

| Coverage | Before | After |
|---|---:|---:|
| TRAIN examples | 252 | 1,156 |
| TRAIN scene groups | 12 | 60 |
| Original VAL examples | 84 | 84 unchanged |
| Additional VAL examples | 0 | 216 |
| VAL scene groups total | 4 | 16 |

TRAIN:766 motion,304 visual,64 HOLD,22 STOP. VAL:196 motion,80 visual,18 HOLD,
6 STOP. All original336 rows and28 generation probe identities remain exact.
20 new coordinate flights vary4/8/12/16m goals and heading setup;40 new visual
scene groups vary requested color, swapped colors, heading, bearing and distance.
Only seed1450-1469 and1500-1539 are newly collected. Seed%5 assigns validation.
No held-out1-40 or protected1060-1064 scenes collected or trained on.

Quality gates:814 raw coordinate samples;3,636 exact replayed controls/poses,
3,196 label-to-control checks and2,442 original image checks. All20 teacher
flights complete.320 visual segments have1,600 audited states,960 source/after
frames,1,280 controls and320 pair checks. All visual teacher segments reduce
observed bearing error; this is teacher correctness, not learned performance.
15 geometry proposals with unobservable/clipped/occluded targets rejected before
writing pairs.14 new rows excluded for exact-image cross-split conflicts; full
IDs/reasons in excluded_rows.json. Final admitted index has zero cross-split
exact image duplicates. This check cannot exclude near-duplicate scene content.

New dataset:
D:/drone_vla_pilot/data/local_expanded_20260917_v4
Index SHA256:7318727a1c23868e32ed8e5db9fadb07155c0e2421a85a66a8af01551641c064.
Raw coordinate source retains FLU; admitted targets/prompts are FRD. All814
conversions preserve physical actions exactly. Original corpora are untouched.

Each effective batch contains one visual,one motion,one HOLD,one STOP example.
Shuffle without replacement within each task until exhaustion; deterministic
seed138. Each sample loss divided by4;backward four times,clip once,step once.
This is microbatch1/accumulation4, not four images resident simultaneously.
The deliberate25% class prior oversamples STOP/HOLD;monitor premature STOP and
unnecessary HOLD as well as aggregate loss.400 scheduled steps mean1,600 sample
exposures, not400 as in previous runs.400 motion exposures do not cover all766
motion rows in the expanded set;report exposure counts rather than call it an epoch.

The smoke test uses fresh language-only LoRA on the cached image-only Smol256,
8 actual sample exposures,finite nonzero gradients and900,276,736 allocated
GPU bytes peak. Smoke loss values are pipeline diagnostics, not learning evidence.
53 relevant unit tests pass including analytic mean-gradient equivalence,
validation exclusion,task coverage and action contracts. Ruff passes.
Debugger verification:1,120 admitted new options,36 exact source/target/state
checks across9 examples,20 teacher flights,8 exact scheduled batches,responsive
mobile layout,no JavaScript errors. No model predictions are invented.

Review: http://127.0.0.1:8771/expanded_data.html
Replays: http://127.0.0.1:8771/expanded_teacher_flights.html

Failed pre-admission attempts remain on disk:v1 required manifest field missing,
v2 cross-split duplicate rejection,v3 missing/clipped target rejection. None is
admitted to training. v4 adds conservative image exclusions and observable-scene
rejection;default original generator behavior remains available.

Next: freeze a matched Smol256 balanced-existing versus balanced-expanded short
comparison, equal initialization,optimizer steps and sample exposures. Report
original and new-scene validation separately;preserve all checkpoints. Validate
STOP/HOLD, paired instruction/color swaps and actual saved-action executions.
No AWS spending. Additional local diversity still needed:altitude/vertical
motion,obstacles,search,recovery,appearance,wind and dynamics. External simulation
and calibrated real-flight action data remain required under D127. This collection
does not establish real-world readiness or broad paper-task coverage.
