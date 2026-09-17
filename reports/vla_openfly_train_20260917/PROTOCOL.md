# D142: native OpenFly training pipeline diagnostic

Frozen before optimization, 2026-09-17. Local only, no AWS spending.

The prior 51-frame official evaluation diagnostic is not published flight success.
Smol256 has 51 invalid outputs, Smol500 45 invalid and six HOLD outputs, Qwen
45 mixed commands, and OpenFly 32 mixed vectors. These are different failures.
The original scores remain unchanged. The checkpoint contains vln_norm and
vlnv1; the model-card setup used vln_norm whereas released eval.py uses vlnv1.
Its training history sampler also differs from our causal preceding frames.
Some released builder branches index image_array[-1/-2] at early timesteps;
we do not copy future-image access. Published performance is not reproduced.

Official TRAIN manifest: revision a12316d56a4e35a32ad626fb725ed7089937a1c4,
100,226 trajectories. No identity overlap with all 3,000 official seen/unseen
trajectories. Negative action IDs are unresolved; exclude entire affected
trajectories from this pilot. Selection is label-based, never model-based:
minimum SHA256 route per environment with vertical actions where available,
and a different minimum SHA256 route for development; lengths 3..80.

22 complete trajectories, 258 TRAIN and 171 dev decisions, 11 environments.
615,934,301 parquet bytes. Source images, pose/yaw and coarse action agree
with annotations. Train/dev image hashes are disjoint; downloaded official
evaluation image hashes also excluded. Full official evaluation image duplicate
checking is unavailable without downloading all 3,000 evaluation trajectories.
Dev has no vertical labels; lateral IDs6/7 are absent throughout the manifest.
See selection.json and data_audit.json for reproducible details.

New policy contract openfly_native_action_id_v1: output one original action ID
0..9. Preserve forward distances 3/6/9m; do not invent velocity conversion.
Turn/vertical amplitudes remain unapproved for simulator or real control.
Inputs: instruction and three causal front images (two past and current,
repeat first at episode start), max256px each. No odometry, future labels,
frame index or target pose. This is offline next-action imitation, not a
closed-loop VLA benchmark. Source recordings are labelled as recordings.

SmolVLM-500M base, BF16, fresh language-only LoRA r8/alpha32/dropout0,
AdamW2e-4, seed142, microbatch1/accumulation4, class-rotating mixed batches,
assistant token/EOS cross entropy, max2048 tokens, one-hour optimization cap.
First80 updates on one TRAIN example per represented action (8 examples).
Gate: at least7/8 unconstrained greedy exact outputs; otherwise stop and
diagnose. On pass reset to identical base and run160 fresh pilot updates.
No old FRD adapter is overwritten or resumed.

Compare native-ID dev generation before/after and blank-image intervention,
report exact accuracy, per-class recall and invalid outputs; inspect raw outputs.
Save adapter and verify four reload predictions exactly. Success for the
pipeline is source/split checks, memorization gate, finite gradients and reload.
Evidence of useful learning additionally requires improvement over base and
majority, macro recall and image dependence. Failure does not trigger a sweep.
No official seen/unseen rows used for optimization or checkpoint selection.
No local held-out seeds1–40 or1060–1064 enter this experiment.
