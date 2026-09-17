# D140 - OpenFly local inference and viewer corrections

The released OpenFly weights are downloaded and verified (15,086,411,278 bytes,
all listed sizes and LFS SHA256 hashes). The model runs on the local RTX4060
Laptop8GiB in4-bit NF4, with BF16 vision/projector/lm_head. No training or AWS.
Peak PyTorch allocation5,858,114,560 bytes (~5.46GiB); training-template median
inference0.7185s. This is allocated tensor memory, not total GPU consumption.

Model revision:21dcce235f1f2d40fc23c76998051abc5434cc99.
Official source revision:c075075497a7122bad82f5b76b9be926ad5a81b3.
Checkpoint:D:/drone_vla_pilot/models/openfly-agent-7b.
Source:D:/drone_vla_pilot/models/OpenFly-Platform.
Environment:D:/drone_vla_pilot/venv_openfly (isolated overrides, read-only system
packages). Pins:transformers4.48.1,tokenizers0.21.1,timm0.9.16,bitsandbytes0.48.2,
accelerate1.7.0;torch2.6.0+cu124. Existing model environments untouched.

## Initial comparison

Same16 original visual development cases (seeds1410/1415), no held-out seeds.
OpenFly gets exact front image,initial history repeated3times,and instruction;
Smol previously got dual-view mosaics and local fine-tuning. This is a transfer
and integration diagnostic, not a fair overall model ranking or native benchmark.

| Condition | Correct turn direction | STOP | Behavior |
|---|---:|---:|---|
| Smol256 original data |8/16|0/16|constant direction|
| Smol256 expanded data |8/16|0/16|constant direction|
| OpenFly model-card prompt |0/16|16/16|alwaysSTOP|
| OpenFly official training template |8/16|0/16|alwaysright|

Model-card example uses raw instruction; official training uses
LLaMa2ChatPromptBuilder and 'What action should the robot take to ...?'. Both
preserved; training prompt checked because the raw-prompt collapse warranted
an input-contract audit. No selection of a winning benchmark condition.
Both use vln_norm from the model card; official eval.py instead uses vlnv1.
Changing normalization is not justified by which produces a better score.

All32outputs contain legitimate action tokens. Token31744 is the documented
upper digitize endpoint; an initial too-strict range check was corrected from
recorded tokens using the official ActionTokenizer definition. Exact arrays,
tokens,prompts,images and latencies retained in *_probe.json. No missing,
unexpected,mismatched checkpoint keys or loading errors.

Compatibility fixes: suppress redundant timm pretrained downloads because all
encoder weights are supplied by checkpoint (strict loading audit); append the
model's29871 action-start token AND attention-mask entry before predict_action
(the original wrapper appends only the token). Weights remain unchanged.

## Execution boundary

OpenFly emits an8-component flight-primitive vector, not our65-bin FRD velocity
JSON. Left/right semantic direction can be compared now. Full flight evaluation
is NOT completed. Official code labels turn component15 but executes30degrees;
vertical/lateral amplitudes also differ between encoded vectors and execution.
A versioned native-primitive execution adapter must state those semantics and
normalization, verify control effects, then run matched development flights.
Never treat an unknown rounded vector as STOP (official eval defaults toSTOP).
Realistic native-scene sanity check and quantization reference remain needed
before interpreting synthetic-scene collapse as general OpenFly performance.

## Dashboard fix and teacher semantics

Original/Expanded appear in titles and every run choice. Immutable run IDs and
all source evidence preserved. Notes now keyed by page+run. Actual model call,
control interval,and motion/HOLD/STOP/invalid counts make stationary execution
explicit. Expanded1400 ran50calls/200intervals/10s:allHOLD. Expanded1405 made
one immediate falseSTOP. Original approaches thenSTOPs short; these failures
are the comparison, not missing runs. Zero-shot invalid outputs clearly marked.

TeacherSTOP:distance<=0.35m AND speed<=0.1m/s. HOLD while within radius but still
moving. Expanded TRAIN includes64HOLD/22STOP;both included in every effective
batch. Such aggressive balancing may contribute to stopping bias; causal effect
not established by these two data-condition runs.

C5 is our OnFly-inspired architecture with keyframe memory, not OpenFly weights.
No architecture baseline or evaluation split changed.

Validation:8original+6expanded exact-source browser checks,four outcomes each,
playback,responsive layouts;explicit condition labels/actioncounts and stationary
clock progress;16OpenFly exactimage/prompt/output browser checks. NoJSerrors.

Viewer:http://127.0.0.1:8771/openfly_comparison.html.
Reproduce inference:venv_openfly Python scripts/probe_openfly_local.py --limit 16
--prompt-style training --out NEW_D_DIRECTORY.
Rebuild pages:scripts/label_balanced_flights.py; scripts/build_openfly_probe_review.py.
