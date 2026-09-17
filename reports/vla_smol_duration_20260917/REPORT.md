# Smol capacity and training duration

Protocol: [PROTOCOL.md](PROTOCOL.md), research decision D137.
Both local arms are complete. Doubling model size and extending training did
not solve visual contrast pairs or STOP under this recipe. Both sizes pass the
tiny memorization gate, but fail the mixed-data useful-pilot gate.

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

## Completed 500M arm and comparison

The public image-only500M model is pinned in smol500_files.json. Its separate
400-update tiny gate passes16/16 exact including HOLD/STOP,with16 identical
reloads. The mixed run starts a fresh adapter; memorization weights are not used.

| Step | TRAIN weighted loss | VAL weighted loss | TRAIN ordinary CE | VAL ordinary CE |
|---:|---:|---:|---:|---:|
|0|1.7106|1.5981|1.1089|1.0887|
|200|0.5776|0.5002|0.1651|0.1432|
|400|0.4997|0.4572|0.1435|0.1304|
|600|0.4042|0.4400|0.1151|0.1246|
|800|0.3919|0.4772|0.1122|0.1360|
|1000|0.3349|0.4959|0.0975|0.1424|
|1200|0.2910|0.5474|0.0828|0.1564|

500M shows a smaller generalization gap than256M, but the final validation
loss is worse than its400-step value. Its lower600-step validation loss did
not select the final checkpoint:1200 was fixed in advance.

| Metric | 256M:400 ->1200 | 500M:400 ->1200 |
|---|---:|---:|
| Valid actions |28/28 ->28/28|28/28 ->28/28|
| Exact full action |4/28 ->0/28|4/28 ->4/28|
| Visual direction,zero translation |8/16 ->8/16|8/16 ->8/16|
| Terminal STOP |0/2 ->0/2|0/2 ->0/2|
| Coordinate velocity MAE(m/s) |0.3342 ->0.2214|0.2214 ->0.1649|
| Coordinate yaw MAE(rad/s) |0.1367 ->0.1211|0.0586 ->0.1133|

At1200 both models score0/8 on instruction pairs and0/8 on color-swap pairs.
For500M,removing the task instruction changes0/16 outputs;blanking the image
changes4/16 but leaves direction accuracy8/16. Both models therefore fail the
visual-pair test despite some numeric improvements. This does not isolate a
parameter-count cause:pretraining differs,adapters are language-only,and the
dataset/representation remains narrow. It does show that more updates or this
larger model alone do not repair the failures under the tested recipe.

500M uses1.609GB peak PyTorch allocation and492.796 optimization seconds for
all1200updates.256M uses1.051GB and335.407seconds for800additional updates;
its original400updates took140.359seconds. These exclude model loading,
validation and generation. Median final generation is2.360s/2.328s respectively,
far above the0.2s action horizon;these sequential laptop runs are not a rigorous
latency comparison. Only four representative final predictions per model were
reload checked,not all28;the256starting checkpoint did reproduce all28.

## Verification and review

Both exact schedules pass:256executes the remaining800IDs,500executes all1200;
first400match D136,all IDs are TRAIN,all gradients finite/nonzero. All336 input
rows have verified image hashes,prompt construction and untruncated labels.
Both models execute16 saved visual actions over64ticks each,with8/16 bearing
improvements each. Independent frame/command/dynamics audits pass. No new
closed-loop flight success is claimed. Synthetic STOP regression evidence is
explicitly separated and excluded from these model scores.

The browser passes176 exact source-image/prompt/raw-response/physical-command
checks,including final execution images. Full/focused/task loss plots are
verified byte-for-byte in the browser;responsive layout and no JS errors pass.
Four focused unit tests and Ruff pass. All work stays in the isolated branch.

[Interactive comparison](http://127.0.0.1:8771/smol_duration.html)
[Focused loss plot](duration_loss_curves.png)
[Full loss history](duration_full_loss_curves.png)
[Task losses](duration_task_losses.png)

Raw adapters/reports are at D:/drone_vla_pilot/runs/
{smol256,smol500}_duration_20260917_a;source model and data hashes accompany
this report. Prior datasets,checkpoints,architecture baselines and splits remain.
No external data,AWS/paid resources,protected seeds or physical flights used.

Next freeze a visual-only TRAIN contrast-pair overfit test to isolate visual
learning from mixed-task interference. Then separately test balanced STOP/HOLD/
motion/visual sampling. Broader local scenes and later external simulator/real
flight data remain necessary;the current findings do not establish deployment
readiness or justify a larger cloud training run.
