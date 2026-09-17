# Smol capacity and training duration

Protocol: [PROTOCOL.md](PROTOCOL.md), research decision D137.
Status:256M complete;500M mixed run in progress. This report will be completed
with both outcomes, without changing the frozen schedule.

## Why the old loss curve looked unusual

Each optimizer update used one shuffled example and a weighted action-value
loss. The old validation plot used ordinary answer-token cross entropy.
Those quantities were not directly comparable. Motion,HOLD,STOP and visual
examples also have substantially different loss levels, creating jaggedness.
The new measurements use evaluation mode and the same loss definition on all
252 TRAIN and84 VAL examples, with separate task breakdowns.

## Completed256M continuation

The original400-step adapter reproduced all28 stored predictions exactly.
800 additional updates used the predetermined sample IDs and5e-5 learning rate,
with a fresh optimizer every200. Optimization took335.407seconds; peak PyTorch
allocation1.051GB. Four final reload checks are identical.

| Step | TRAIN weighted loss | VAL weighted loss | TRAIN ordinary CE | VAL ordinary CE |
|---:|---:|---:|---:|---:|
|400|0.4957|0.5180|0.1456|0.1528|
|600|0.4399|0.6118|0.1262|0.1764|
|800|0.4130|0.7554|0.1171|0.2164|
|1000|0.3710|0.6857|0.1052|0.1961|
|1200|0.3342|0.7316|0.0955|0.2091|

This trajectory supports overfitting under the current recipe. It does not mean
all metrics deteriorate: coordinate velocity MAE on12 fixed generation probes
improves0.3342->0.2214m/s,and yaw MAE0.1367->0.1211rad/s. But visual direction
remains8/16,both instruction-pair and color-swap-pair scores remain0/8,and STOP
remains0/2. Overall exact full actions fall4/28->0/28 while validity stays28/28.

At1200,blanking images changes16/16 predictions but does not improve pairwise
correctness; image sensitivity alone is not successful visual grounding. Saved
visual actions execute64ticks over16 byte-exact source scenes and improve
angular error8/16. An independent command/frame/dynamics audit passes. These
are0.2s action diagnostics,not a new closed-loop flight or realtime test.

The current dataset has only four validation scene groups. These are repeatedly
inspected development validations,not untouched test results. No protected seeds
or external training data were used. Existing baselines/checkpoints stay intact.
