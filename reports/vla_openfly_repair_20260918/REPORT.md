# D147: decoder repair and deeper data/evaluation audit

Implemented an explicit vertical-capable decoder, validated it, and reran the existing checkpoints. The investigation found independent problems in decoder coverage, compressed frame/action alignment, eight source motion records, and the interpretation of STOP/aggregate scores. None supports declaring the small adapters equal to a validated OpenFly policy.

## What is fixed

`src/uavlab/training/openfly_codec.py` now checks that every evaluated primitive survives actionâ†’tokenâ†’action round-trip. Invalid vectors never become STOP; output must contain eight actual action tokens. The old vlnv1 profile is rejected for the six-direction task; the model-card vln_norm also fails coverage. Published vlnv11 covers STOP, forward3/6/9, left/right turn and up/down. It is an explicit vertical-capable adapter choice, NOT proven to be the checkpoint's historical calibration profile. No score-based profile search or nearest-codebook projection was used.

Five regression tests cover silent vertical collapse, premature EOS/non-action tokens, zero-vector fallback, mixed vectors and primitive round trips. All eight tested primitives also survive the actual released LLaMa2 training chat/tokenizer suffix round-trip. The repaired local NF4 rerun produces correct up/down on9/24 old-panel cases (previously impossible); strict direction overall is16/72, so fixing coverage does not rescue overall performance.

## Verified data discrepancy: compressed action uses the wrong decision boundary

For all110 pilot routes,1,106 compressed forward commands reference the LAST raw frame inside their2- or3-step block. In284 cases the advertised motion does not match the future path starting at that frame, although it matches the block ending there. A frame0â†’3 forward9m block is tagged with frame2, from which only3m of that block remain. This is not a reversed-axis issue.

We reconstruct each block start from its explicit length, require all blocks to partition the raw action sequence in order, and verify the endpoint pose. This produces a separate `aligned_macro_manifest.jsonl`:1,639 verified examples, same88 train/22 dev routes, eight quarantines. Old atomic data, adapters, original annotation files and splits are unchanged. Future poses are used only to verify labels; every input image index is at or before its action start. No labels, future frames or goal coordinates enter model prompts.

On12 mismatch pairs selected before inference, OpenFly direction improves7/12â†’11/12 and exact macro6/12â†’9/12 when only the image/history moves to the verified block start. These selected forward-only cases diagnose alignment; they are not a representative performance estimate. The fresh balanced72-case matched rerun is separate and frozen by SHA256 identity within each class.

## Verified raw-source anomalies and limits of the audit

Across3,752 raw frames:3,634 moving transitions match their next pose; eight disagree;110 STOPs are terminal. All eight disagreements were already excluded from the latest joint training data. Six have identical before/after decoded pixels despite a turn label; one has nearly identical pixels (MAE0.004/255); one visibly changes (MAE54.5/255) while yaw metadata does not. The latter cannot be repaired by blindly relabeling the image as no motion. All eight remain quarantined.

No exact three-image/instruction conflicts or current-image duplicates across our train/dev split were found. This is not a perceptual deduplication of the entire published dataset. All15 routes containing vertical actions have explicit vertical language, but that lexical check does NOT validate all landmark descriptions or instruction phase. Human visual inspection covered the documented alignment example and a quarantined turn; full semantic instruction correctness remains unverified.

## Evaluation discrepancies

-74/3,752 raw frames have vertical labels (about2%); the balanced panel dedicates24/72 (33%) to them. Balanced macro recall is useful but not representative trajectory-frequency accuracy.
-Our small adapters emit atomic3m forward; OpenFly can emit6m/9m. Direction agreement is the common metric. Exact macro distance is reported separately for OpenFly and must not penalize a small model for a contract it was not trained to emit.
-21/60 old-panel nonterminal observations lie within20m of the recorded terminal pose. Both historical OpenFly nonterminal STOP predictions meet that distance threshold. The old phrase false STOP means disagreement with the recorded terminal label, not necessarily failure under the paper metric. This offline distance check does not establish actual closed-loop success.
-The released checkpoint's training routes may overlap these official TRAIN routes. They remain unseen by our adapters. No equal-unseen or published-benchmark claim is made.

## Full annotation audit: phase tags and mixed pose schemas

All100,226 TRAIN annotations have matching action/image lengths, nonempty instructions and unique route IDs. However9,728 routes contain231,395 tags outside the released0–9 action map: all115,575 `-1` tags form initial climb runs, and all115,820 `-2` tags form trailing descent runs AFTER the sole recorded STOP. The pilot intentionally excluded these routes, creating a phase/route-selection bias. Do not equate the pilot's2% vertical rate with the full dataset.

The released evaluator uses the last position as its goal. On8,160 of these TRAIN routes, the recorded STOP position is over20m from that last position (range3–90m across all9,728). This is a direct phase/goal-contract discrepancy, not evidence that the official test set has exactly the same frequency. The parser now keeps initial climb and post-STOP descent explicit and defines navigation goal at the recorded navigation STOP. It does not silently convert negative tags into motion/landing commands or download/admit unverified images for training.

Positions also mix3-component XYZ and4-component XYZ+yaw:23,717 of1,608,519 positions carry the redundant yaw. The separate yaw agrees on every checked4-component position. The schema parser validates it before extracting XYZ. All100,226 episode schemas pass after this explicit handling; regression tests reject ambiguous phases, mixed-length fields and inconsistent yaw.

## Controlled reruns

See `summary.json` and the interactive repair page for the final matched72 results and gray-image controls. All three adapter reloads reproduce their24 original raw outputs exactly. Gray controls keep instructions and image dimensions fixed. Image-sensitive outputs do not by themselves establish correct visual grounding. No models were trained in this investigation.

## Remaining uncertainty and next experiment

The corrected code and manifests are ready; a trustworthy reproduction of the published policy is not established. The release contains conflicting prompt, historical-feature pooling and history-selection paths. D146 isolated prompt and pooling changes without improvement. D147 resolves physical macro alignment and action coverage, but historical checkpoint normalization mapping remains unverified. A bounded six-case BF16 reference (with CPU offload,218s) gives identical decoded actions to NF4 on all six, so quantization alone does not explain those cases; full-panel equivalence remains untested. Source discussions show others encountered related issues, not that any proposed workaround is authoritative.

Do not launch a larger training run based on falling loss or this ranking. Use the verified raw/macro contract in a small follow-up training experiment with broader unique routes and per-action validation, while keeping the released model labelled as a provisional adapter baseline until its calibration is established. A subsequent shared closed-loop test must use the same action/controller contract and explicit goal tolerance. There was no AWS spend, no new physical flight, and no protected-seed use.

Reproduction: `audit_openfly_dataset_full.py`, `build_openfly_aligned_manifest.py`, `evaluate_openfly_repaired.py --norm-key vlnv11`, `evaluate_joint_repair_controls.py` and `summarize_openfly_repair.py`. Protocol and exact manifests are frozen alongside outputs. First repaired runner attempt failed before prediction due to report metadata accidentally entering generate kwargs; retry corrected this, with no change to weights or cases.

### Fresh matched72 results

| Model | Direction | Valid output | Up | Down |
|---|---:|---:|---:|---:|
| openfly_vla (explicit vlnv11 adapter) |20/72|48/72|6/12|4/12|
| Smol256 |20/72|72/72|4/12|0/12|
| Smol500 |21/72|72/72|0/12|2/12|
| Qwen |24/72|72/72|2/12|1/12|

These are weak next-direction results. The table is not proof of reliable flight or of equivalence to the published OpenFly policy. The gray-image controls show image-dependent outputs but little consistent accuracy advantage for our adapters, supporting further investigation of useful visual grounding and route progress rather than longer training by default.
