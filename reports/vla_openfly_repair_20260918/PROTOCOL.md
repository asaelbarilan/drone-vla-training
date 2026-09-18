# D147 decoder repair and data/evaluation audit
Date:2026-09-18. Scoped evidence-first investigation of OpenFly only.
Primary sources: pinned release source/checkpoint, official HF RLDS metadata, upstream maintainer discussions and our pinned110 raw training-route Parquets. Secondary user reports are leads, not proof.
No training, cloud spend, split changes, held-out seeds or new model sweep.

Acceptance: strict decoder rejects unsupported evaluation action sets; all evaluated primitives round-trip through tokens; no silent all-zero-to-STOP; exact generated length checked. Use published vlnv11 bounds as an explicit vertical-capable adapter (not a verified historical normalization mapping). Keep raw prompt, released pooling and NF4 fixed for same72 retry.
Audit all110 existing routes: action/next-pose alignment; compression start/end boundaries; terminal positions; image duplicates/conflicting same-input targets; instruction vertical wording; split overlap. Freeze new motion-verified macro panel from existing dev routes only before inference. History must be causal. No future labels enter prompts.
Interventions: baseline same72 with explicit vertical-capable decoder; a separate forward-macro panel using starts verified from raw motion and paired original annotation frames; first24 balanced original cases with gray images as a visual dependence control. Compare direction separately from macro distance. Report results even if worse. Stop after these targeted inference checks and audit, not after score improves.
Full-precision equivalence and official closed-loop reproduction are outside this bounded local rerun; distinguish unresolved limits.

Final matched rerun (registered before inference): 72 aligned macro-manifest DEV cases, 12 per direction, chosen by lowest SHA256 of immutable id within class. All four existing checkpoints receive same three causal frames and route instruction with their unchanged model-specific prompt. Main common metric is direction, since our adapters have only3m forward output. Report exact macro only for OpenFly. No retraining or checkpoint choice. Macro alignment controls remain a separate selected diagnostic, not a benchmark.

Precision diagnostic: available RAM16.98GiB permits a bounded unquantized BF16 model with CPU offload. First original case per action, six total, frozen before this run; same profile/prompt/images. Run only after all other GPU jobs finish. Wall cap600s; preserve partial outputs if infeasible. This can identify a precision contribution on these six cases, not estimate full-benchmark accuracy.
