# D146 forensic investigation, scoped to OpenFly

Question: does the unexpectedly poor released-model comparison arise from our
labels/evaluator, inconsistent released interfaces, quantization, or model limits?
Sources: official OpenFly paper (methods/evaluation), pinned released training and
inference code, checkpoint config/model card, dataset raw Parquets/annotations.
Search terms: OpenFly action normalization, history/keyframe, dataset alignment,
released inference. Date:2026-09-18. Exclude unrelated model surveys; user narrowed
the question to this integration. Stop when interface differences and bounded
controlled tests distinguish proven defects from remaining uncertainty.

Preserve D144/D145 scores and splits; no training, AWS or held-out seeds1-40.
Audit current panel against raw pose deltas and annotation frame identities,
inspect training image order and action-token codec, compare paper/released code.
Register interventions before inference. Change one factor at a time; no choice
of best-looking results as a claimed correction. Never use future frames/labels
as model inputs, even if example training code does. Use local 4-bit model for
bounded inference; quantify quantization only if a matched reference is feasible.
Report unsupported full-precision/published-benchmark reproduction as unproven.
Outputs: source evidence, executable audits/controlled predictions, corrected
interpretation in dashboard, research log/CHANGES and coherent commits.

Controlled intervention A (registered before inference): same frozen72, same NF4 checkpoint, vlnv1, images and decoding; change only raw instruction to lowercased LLaMa2 training chat template. Capture generated length to reject early-EOS token slicing. No score-based prompt selection.

Controlled intervention B (registered before inference): raw prompt baseline plus only history DINO average-patch pooling from training vision_backbone.py, instead of HF prefix/CLS token. Current-last ordering retained (training prismatic.py explicitly reverses feature list). This is a source-consistency diagnostic, not a verified replacement checkpoint interface.
First A attempt failed before any prediction because instrumentation assumed keyword input_ids; corrected to support positional input_ids, retry B suffix.
