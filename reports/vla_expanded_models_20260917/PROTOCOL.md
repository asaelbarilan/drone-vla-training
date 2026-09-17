# D141 - Expanded Smol500/Qwen and official OpenFly validation

User authorizes4-bit OpenFly,official validation measurements of our models,and
expanded-data Smol500/Qwen training. No higher-precision OpenFly sweep.

Local training:each fresh adapter,400optimizer updates/1600exposures,identical
D139expanded schedule,dataSHA7318727a1c23868e32ed8e5db9fadb07155c0e2421a85a66a8af01551641c064,
seed132,r8/alpha32/dropout0,language-layer LoRA,AdamW2e-4 first200 then fresh
AdamW5e-5 last200,one visual/motion/HOLD/STOP per effective batch. Smol500 BF16;
Qwen3-VL4B NF4. Existing Smol256 expanded checkpoint is reference,not retrained.
Native processors differ;compare behavioral metrics rather than raw cross-model
CE. Full original/new TRAIN/VAL losses at0/200/400;fixed134generation probes,
blank interventions,and4reloadspots. Same unchanged pilot gates asD139.
Sequential GPU jobs;2update smoke first. Local wall caps5400sSmol500,10800sQwen;
no AWS or physicalflight. Keep existing baselines and all splits unchanged.

OpenFly official release inventory revisiona12316d56a4e35a32ad626fb725ed7089937a1c4.
Identify held-out validation membership before using rows;never import evaluation
rows into training. Initial bounded subset selected deterministically from official
membership without looking at model outputs. Offline actions and closed-loop
flight success must remain distinct. Do not invent odometry or missing cameras.
Freeze actual admitted evaluationmanifest/actionmapping before inference. If the
release lacks validation images/labels,state what is unavailable and continue
independent training. Local held-out seeds1-40/1060-1064 remain excluded.


## Frozen external evaluation subset and metric (before any external inference)

51decision frames from14official held-out trajectories,one per environment:
41seen/10unseen. Manifest SHA a4d6d72bcc9dd1234708308a337eb7661b0c58d94bfe7c8cc19cec5dea0358c3
is the exact UTF-8/LF file hash. Targets26forward/7leftturn/
5rightturn/13STOP. Two selected negative-ID records excluded as outside official
0..9 mapping,not reinterpreted. Image IDs/pose/yaw and coarse Parquet action
agree;1e-9 pose tolerance handles numeric serialization. No outputs consulted.

Score coarse semantic action class,macro recall by class,seen/unseen breakdown,
format invalids,mixed commands andfalseSTOP. Forward3/6/9 collapse toforward;
no claim of exact displacement/velocity equivalence or fullflight success.
Unknown native vectors are NOT silently STOP. Always-forward baseline26/51.

OpenFly uses fixed official training chat template,vln_norm,previous2annotation
frames+current (repeat first atstart),NF4. Existing adapters keep theirFRDJSON
contract and single-image native processor;frontimage only,explicitly unavailable
odometry/downwardcamera,no fabricated zero state. This observation mismatch is
reported as transfer limitation. No ground-truth future frames/actions/pose are
passed to models. Do not choose prompts using measured external scores.
