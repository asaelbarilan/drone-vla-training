# D142 - OpenFly native-action pilot

Status: **complete**. Smol500 BF16 language LoRA; local, no AWS.

22 official TRAIN routes, 258 train /171 dev decisions; original evaluation untouched.
Pipeline gate passes (8/8 memorization, finite updates, four reload spots exact).
Learning gate FAILS:18/171dev exact, macro recall0.149, below majority113/171
and majority macro recall0.167. Blank images give11/171 (all STOP); image
dependence does not establish useful grounding.26false STOPs/160nonterminal.
The untrained base has171invalid outputs; its0/171 primarily measures format
failure. Falling CE also rewards learned formatting, not just action competence.
8-example overfit then a fresh-base160-update pilot, conditional on overfit gate.

|Evaluation|Exact|Invalid|Macro recall|Majority reference|
|---|---:|---:|---:|---:|
|overfit_before|0/8|8|0.000|1/8|
|overfit_after|8/8|0|1.000|1/8|
|dev_before|0/171|171|0.000|113/171|
|dev_after|18/171|0|0.149|113/171|
|dev_blank_images|11/171|0|0.167|113/171|

Exact native action ID scoring differs from the earlier coarse FRD transfer diagnostic.
No velocity conversion, physical flight, or autonomous OpenFly simulator rollout claimed.
Motion audit:910/911 raw transitions align, one zero-yaw right turn flagged. Compressed
annotation frame gaps are not primitive durations (22/22 ID8 gaps measure3, not6).
Training imitates released native IDs; continuous-control labels are not validated.
Dev routes contain no up/down actions; neither lateral ID occurs in the full manifest.
Only11dev trajectories: correlated frames do not count as171independent flight trials.
Blank-image intervention measures dependence, not causal proof of good visual grounding.

OpenFly integration: identical saved tokens re-decoded with released-evaluator vlnv1
change coarse accuracy12/51 to29/51, mixed vectors32 to0, turn accuracy remains0/12.
This post-hoc sensitivity does not replace the original table or reproduce published flights.
Prompt/history, controller semantics and4-bit effects remain incompletely isolated.

Data hashes, selected routes, predictions, sampling exposures, adapter hashes and reload
evidence accompany this report. Broader simulation/real-flight coverage remains necessary.

Viewer: http://127.0.0.1:8771/openfly_training.html

Next: reconcile the released inference prompt/history and normalization; build a versioned atomic-action dataset with verified temporal alignment, retaining current frozen results; broaden train/dev route and vertical coverage before scaling. No physical-flight data was added in this pilot.
