# D146: OpenFly comparison investigation

The D145 ranking must not be interpreted as evidence that our small models match or outperform the released OpenFly agent. A definite decoder coverage problem exists, alongside protocol differences and unresolved checkpoint compatibility. The audited panel does not support a blanket claim that the dataset is mislabeled.

## Confirmed evidence

- Independent source audit: 72/72 original image hashes and frame identities match; 60/60 nonterminal labels match the next recorded body-frame motion (tolerance0.01); 12/12 STOPs are final raw frames with final official STOP annotation. All64 panel frames present in the compressed annotation agree in direction; eight intermediate raw frames are absent there. These checks do not validate the natural-language route semantics or prove all dataset rows correct.
- `vlnv1`, hardcoded by released eval.py, has q01=q99=0 for both vertical components with mask=true. The decoder formula therefore always returns zero on them. Up/down make up24/72 panel targets. The model-card vln_norm instead has forward q99=5 and down q99=0: it is not a drop-in solution for our codebook either. Several other profiles permit vertical motion; the source does not establish which key belongs to which checkpoint/data context.
- All72 baseline outputs contain action-range tokens. All13 invalid vectors are exactly all-zero after rounding, not malformed text. Unknown vectors remain invalid rather than silently becoming STOP. Alternative normalization can reveal vertical or mixed components, so clipping dimensions can conceal model output.
- Training dataset.py and model/load_model.py build a lowercased LLaMa2 action chat prompt; HF eval.py sends the instruction directly. The controlled same72 prompt intervention isolates this difference.
- Training vision_backbone.py pools historical DINO patch tokens; HF modeling_prismatic.py uses the historical DINO prefix/CLS token. Current-image ordering is NOT reversed accidentally: training prismatic.py explicitly reverses the feature list, placing the full current image last, matching our wrapper.
- The example released dataset builder selects final images at idx1 and can select a future first-transition keyframe. It also overwrites the last two actions with STOP. This is a source-code reproducibility hazard, not proof that the released checkpoint used this exact placeholder builder. Our data pipeline never uses future observations.
- The paper uses action-transition history keyframes; our shared panel uses three adjacent causal raw frames. This is a matched-observation diagnostic, not reproduction of the full paper policy. Its current image and recent history may not identify progress through a long route.
- Our labels are atomic raw-frame actions; released predictions include forward6m/9m macro actions. Direction scoring credits these, exact scoring does not. Sixty-four frames also exist in the compressed annotations; no direction contradiction was found there.

## Controlled tests and interpretation

| Intervention | Direction /72 | Valid vector /72 |
|---|---:|---:|
| Original raw prompt + vlnv1 |18|59|
| Training prompt only + vlnv1 |17|59|
| Training history pooling only + vlnv1 |18|60|
| Original tokens decoded with vertical-capable vlnv11 (unverified mapping) |16|46|

Restricted to48 STOP/forward/turn cases, historical direction counts are openfly_vla18, Smol25615, Smol50014, Qwen14. This illustrates the decoder coverage confound; it is not a replacement six-action benchmark or evidence of a statistically reliable winner.


See results.json for exact counts, all predictions and horizontal-only restricted scores. Prompt and pooling interventions each change one factor relative to the preserved baseline. Decoder sensitivity reuses the same saved tokens with the published profiles; vlnv11 is a representative vertical-capable profile, NOT a verified correction or a selected best key. No checkpoint was trained or changed. New runs verify eight generated action tokens for all examples and no missing/unexpected checkpoint keys.

The official metric is closed-loop flight success within20m of the goal, with reported SR33.2% seen and10.7% unseen. It is not next-action agreement on our balanced72-frame sample. Source: https://arxiv.org/html/2502.18041v6 (sections5–6, appendixI). Our six local simulator flights and this offline score cannot reproduce that benchmark.

## What remains before a defensible comparison

1. Obtain or reconstruct from release artifacts the checkpoint's actual normalization/environment mapping and history interface; do not choose these by validation score. Explicitly test that every evaluated target action is representable before admitting any model to a leaderboard.
2. Add a separate source-native macro-action panel at original annotation decision boundaries, with documented causal history, while preserving the current atomic panel. Audit instruction-to-route alignment visually, especially route transitions and terminal cases.
3. Compare all models on that agreed contract and then on common closed-loop routes. Report per-action confusion and outcome, not only average loss or token accuracy.
4. Quantization remains an untested contributor: no matched full-precision reference was run. More training should wait for this baseline contract to be established.

Evidence: label_audit.json, source_evidence.json (pinned commit and SHA256), results.json, controlled probe JSON, PROTOCOL.md, scripts/audit_openfly_forensics.py and scripts/summarize_openfly_forensics.py. The first prompt diagnostic failed before predicting because token-count instrumentation assumed a keyword input; the retry supports positional input. No data or split changes, no AWS and no protected seeds used.
