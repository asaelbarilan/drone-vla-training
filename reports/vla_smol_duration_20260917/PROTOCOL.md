# Smol model size versus training duration (D137)

The user requests an image-only SmolVLM-500M comparison and questions whether
400 updates were too few for256M. Keep data and sampling fixed to separate this
from a future data-balancing experiment.

-252 existing TRAIN examples,84 development VAL examples;original groups intact.
-Image-only SmolVLM-256M and500M, BF16, language-only LoRA rank8/alpha32.
-Compare total updates400 and1200.256 resumes its preserved400 adapter;
 500 starts a fresh adapter after passing the same tiny correctness gate.
-Original first400 IDs unchanged;complete shuffled passes continue with seed132.
-Learning rate2e-4 for the first200,5e-5 thereafter;fresh AdamW every200.
-The optimizer reset at400 is deliberate and matched between models.
-Full TRAIN/VAL losses in evaluation mode every200 steps use the same weighted
 action objective and the same ordinary answer-token CE. Each example counts
 once in the split mean;also report visual,motion,HOLD,STOP separately.
-The256 curve begins at400;no invented earlier full-TRAIN measurements.
-At400/1200 generate the same28 fixed validation probes. Final image/instruction
 blank controls and4 exact save/reload spots test behavior and reproducibility.
-Success criteria remain D136:>=27/28valid,>=12/16correct visual directions with
 zero translation and stop=false,both selected terminal STOPs exact,and>=20%
 lower coordinate action MAE than the corresponding zero-shot base.
-No validation-selected checkpoint and no adaptive duration or sampling change.

The two pretrained models are not a controlled parameter-count-only ablation.
The dataset has only four validation scene groups,so conclusions are diagnostic.
An improvement in action prediction does not establish closed-loop flight or
real-world transfer. No new closed-loop flight sweep is part of D137;exact-source
0.2s execution of saved visual actions supplies the bounded control diagnostic.

The prior jagged training curve used single shuffled examples and weighted loss;
its validation curve used ordinary token CE. They were not directly comparable.
The new curves remove that measurement mismatch. Exposure counts are retained:
STOP appears10times by400 updates and28times by1200,versus100exposures in a
400-update tiny gate with4STOP examples out of16. This is a possible explanation
for STOP difficulty,not a demonstrated causal effect.

Local jobs only,one GPU model at a time,70%GPU memory cap,45minutes per duration
job and20minutes per optimization block. No AWS,external training data,physical
flights or protected seeds1-40/1060-1064. Preserve earlier checkpoints/baselines.

Next separate experiments,not mixed into this one:visual-only memorization,
balanced STOP/HOLD/motion/visual sampling,then broader independent local scenes.
External simulator and real-flight data remain later requirements under D127.
