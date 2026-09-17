## D139 - Matched balanced-data Smol256 comparison (2026-09-17)

Status: frozen before training. User requests a goal and autonomous execution.
Rationale: isolate data expansion under identical four-task batch balance.
Two fresh cached image-only Smol256 BF16 language-only LoRA r8/alpha32 runs:
existing_control252TRAIN versus expanded1156TRAIN from D138v4. Same base,
initial seed132,initial adapter digest,400 optimizer updates/1600 exposures,
per-update visual/motion/HOLD/STOP, loss divided by4, clipping once. LR2e-4
for200steps then freshAdamW5e-5 for200. No checkpoint selection on validation.
45min/model wall limit; sequential GPU jobs. No AWS spending or external data.
Full eval-mode weighted/ordinary loss at0/200/400, original and new cohorts
separate, per task. Existing-control new TRAIN cohort is unseen diagnostic,
not its training loss. Preserve old28 generation probes; also evaluate all64
new visual VAL and six equally spaced coordinate probes per new VAL seed,
plus all previously unselected VAL HOLD/STOP rows. Fixed by data only before
training; same probes for both runs. Original16 visual blank-image and blank-
instruction interventions, four final exact save/reload spots.
Primary pilot gate remains>=27/28valid,>=12/16 constrained visual directions,
both original STOP probes exact,coordinate MAE at least20% below zero-shot.
Also require>=48/64 new visual constrained directions,report same-image
instruction/color-swap pair scores and all STOP/HOLD errors including false
STOP. Success is not established by loss alone. Compare expanded/control
without declaring model-size or real-world generality from one training seed.
Two original validation flights1400/1405 per condition,10simseconds/50calls
each,simulation paused during inference and actual latencies reported. Keep
zero-shot reference; no changes to architecture baselines or heldout1-40.
Execute original visual saved actions and independently audit controls/images.
Evidence before run:D138 data audits,53tests,two-update accumulation smoke.
