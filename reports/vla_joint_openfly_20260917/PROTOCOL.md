# D144: three-model OpenFly + local pilot

User authorized local training of SmolVLM-256M, SmolVLM-500M and Qwen3-VL-4B.
No AWS resources or spending. Frozen before full optimization, 2026-09-17.

## Data and conversion

110 official TRAIN trajectories across eleven available environments: 88 train,
22 validation. Preserve D142's 11/11 assignments; deterministic additive selection.
Official seen/unseen evaluation trajectory IDs are all excluded. No local protected
seeds (1–40 or 1060–1064). Existing local validation/baselines remain unchanged.

OpenFly supplies 2,929 train / 815 validation decisions from raw consecutive frames.
Eight inconsistent motion annotations are quarantined. Check movement against the
next pose before admitting a target. Three causal front images, no future image.
Source Parquets total 2,490,861,917 bytes. Existing local data adds 1,156 train /
300 validation examples. Exact hashes, selection and schedule: data_audit.json.

Native atomic targets are 0=STOP, 1=forward 3m, 2=left turn 30 degrees,
3=right turn 30 degrees, 4=up 3m, 5=down 3m. These come from raw action_type and
verified pose deltas, not compressed annotation gaps or guessed velocities.
STOP agrees with the terminal annotation; independent goal geometry is unavailable.
Native images are resized to at most 256 pixels per side; no synthetic interpolation.

Local targets retain existing forward/right/down/yaw-clockwise bins and STOP JSON,
their original prompts and image processing. The instruction explicitly identifies
the action mode. This is joint learning of two tasks; OpenFly supervision is not
evidence of calibrated velocity control, real-world safety or real-time execution.

## Frozen optimization

Each model starts from its original base, not an earlier adapter. Language-only
LoRA r8/alpha32/dropout0; Smol BF16 and Qwen NF4. Same shuffled 400-update schedule,
microbatch1, accumulation8: four local samples (visual, motion, HOLD, STOP) plus
four native samples cycling the six actions. Thus 1,600 exposures/source/model.
Oversampling rare vertical/terminal examples is intentional and recorded; it does
not increase the number of unique trajectories or establish class generalization.

Local loss is the existing 90% equal action-value fields + 10% format/EOS loss.
Native loss is 90% action digit + 10% surrounding format/EOS. Mean sample loss is
normalized over eight samples, avoiding output-length-based domain weighting.
AdamW 2e-4 for 200 updates, fresh AdamW 5e-5 for remaining 200; gradient clip1.
Seed144. No validation-driven checkpoint selection. Save every100 updates.
Limits per job: Smol5,400s, Qwen10,800s. One GPU process at a time; stop on failure.
Smoke tests: two mixed updates/model, finite nonzero gradients, exact input prefix,
image hashes, training-only schedule and four identical save/reload predictions.
Earlier memorization pilots remain recorded separately; a smoke test is not an
overfit or generalization result.

## Evaluation and completion gates

Frozen generation panel: preserved local generation IDs plus 12 native validation
examples/action (72 total). Report exact, valid, per-class recall, macro recall,
false STOP, and the always-forward reference on the same native panel. This
class-balanced diagnostic is not the official full OpenFly benchmark.
Comparable eval-mode losses at 0/100/200/300/400 on the same train/validation
probes, separately by source. Raw optimization losses are noisy and task weighted.
Do not compare absolute token losses as model-quality rankings across tokenizers.

Run the unchanged local simulation at development seeds1400/1405 for each final
adapter. Audit actual predictions, decoded controls, images and outcomes; show
separately from source OpenFly clips. Simulation pauses during inference. No native
OpenFly closed-loop or physical-flight success claim.

Pipeline completion requires all 400 updates, finite losses, exact reload spots,
held-out predictions and audited simulations. Learning evidence requires improvement
over the same model's base on native macro recall beyond the 1/6 always-forward
reference without collapsing local validity/control. Two local flights are diagnostic,
not statistical evidence. Failures remain visible; no automatic larger run or AWS.
