# D145: released openfly_vla on the same OpenFly panel

Frozen before inference: 72 D144 native cases, same IDs, instructions and three
causal raw frames (max256px), no future image/pose/action label in inputs.
Released 7B checkpoint, NF4 language/BF16 vision, local venv_openfly. Raw route
instruction and vlnv1 normalization match released train/eval.py. No prompt sweep.
Model-specific image/token processing remains necessary. 1800s wall limit.

Report direction agreement and exact decoded primitive separately. Decode with
the released rounded-vector codebook; never map unknown vectors to STOP. Forward
6m/9m may agree in direction but cannot count as the exact 3m next primitive.
Both raw tokens and vectors are retained. No guessed velocity conversion.
Our adapters use a six-ID action instruction; OpenFly uses its native vector.
This is an offline matched-observation diagnostic, not a flight benchmark.

These official TRAIN routes were held out from our adapters but potentially seen
by openfly_vla pretraining; this is not an equal-unseen generalization comparison.
Local velocity-JSON exact scores are not comparable to native OpenFly outputs.
No new model training, no AWS, no modification of D144 evidence or held-out splits.
