# D152: blind control on the full aligned 72 panel

## Question

The D147 aligned table ranks `qwen` (24/72) above the released `openfly_vla`
(20/72) on next-direction agreement. That ordering is only meaningful if the
scores are produced by reading the camera. This decision measures that directly:
every model answered the same 72 decisions twice, once with the real frames and
once with every frame replaced by flat gray (127,127,127), same prompts, same
checkpoints, same greedy decoding.

D147 did run a gray control, but on 24 cases drawn from the `openfly:` panel,
which shares only 13 (route, frame) pairs with the `aligned:` 72 scored in the
headline table. This is the first real-versus-gray comparison on one panel.

## Harness check before interpreting anything

Both re-runs on real images reproduced the stored D147 predictions exactly:

- `smol256`: 72/72 identical action ids, 20/72 correct, matching the stored run.
- `openfly_vla`: 72/72 identical action token ids and 72/72 identical decoded
  actions against `aligned_openfly_probe.json`.

All 216 referenced frames were SHA-256 verified against the frozen panel before
inference. The faster wall clock on the repeated `openfly_vla` run (71 s versus
213 s) is warm weight cache, not a different computation; the emitted tokens are
bit-identical.

## Result

| model | real /72 | gray /72 | answers changed /72 | valid real | valid gray | McNemar p |
| --- | --- | --- | --- | --- | --- | --- |
| openfly_vla | 20 | 10 | 35 | 48 | 38 | **0.0213** |
| smol256 | 20 | 15 | 64 | 72 | 72 | 0.4869 |
| smol500 | 21 | 14 | 64 | 72 | 72 | 0.2478 |
| qwen | 24 | 20 | 55 | 72 | 72 | 0.5966 |

The panel is balanced at 12 examples per recorded direction, so a constant
answer scores 12/72. McNemar is the exact two-sided binomial test on the
discordant pairs; the counts behind it:

| model | right only with vision | right only when blind |
| --- | --- | --- |
| openfly_vla | 13 | 3 |
| smol256 | 19 | 14 |
| smol500 | 17 | 10 |
| qwen | 18 | 14 |

## What this shows

**The released model is the only one whose score depends on the image.**
Blinding `openfly_vla` halves its agreement, 20 to 10, and it is right because
of vision on 13 cases against 3 the other way, p = 0.021.

**None of our three fine-tuned adapters show a detectable vision benefit.**
Their answers move constantly when blinded — 55 to 64 of 72 change — but the
movement is close to symmetric, so accuracy does not separate from the blind
condition at this panel size. Pixels reach the decision and perturb it without
making it more correct.

**The headline ranking is therefore inverted with respect to grounding.** `qwen`
leads the table at 24/72 while contributing nothing measurable from vision;
`openfly_vla` trails at 20/72 while being the only model that uses the camera,
and it is additionally charged 24 unparsed outputs as wrong. Scored only on
outputs that decoded, it is 20/48 with vision against 10/38 blind.

Next-direction agreement on 72 balanced cases cannot rank these models. It is
not a flight benchmark, its confidence intervals all overlap, and it rewards a
text prior as readily as grounding.

## Limits

This decision does not measure flight success, does not resolve the
`openfly_vla` decoder calibration (24/72 outputs still fail to parse under
`vlnv11`), does not establish that the released checkpoint matches the v7 paper,
and does not license any ranking claim. A blind control proves a score is not
image-driven; it does not prove a score that is image-driven is good.

No training ran. No weights, adapters, dataset indices, splits or protected
seeds changed. No AWS resources were used.

## Evidence

- `summary.json` — scores, confusion matrices, Wilson intervals, McNemar counts.
- `real_panel.jsonl`, `gray_panel.jsonl` — frozen inputs with per-frame hashes.
- `{smol256,smol500,qwen}_{real,gray}.json` — adapter outputs.
- `openfly_{real,gray}/probe.json`, `predictions.jsonl` — released-model outputs.
- Viewer: `reports/vla_dataset_review_20260916/blind_control.html`, served at
  `localhost:8771/blind_control.html`. All 21 routes, every decision, the three
  causal frames each model received, and all four models under both conditions.

## Reproduction

```
python scripts/evaluate_joint_repair_controls.py --model <m> \
  --panel reports/vla_blind_control_20260920/<real|gray>_panel.jsonl \
  --out-dir reports/vla_blind_control_20260920 --tag <real|gray>
python scripts/evaluate_openfly_repaired.py \
  --out reports/vla_blind_control_20260920/openfly_<real|gray> \
  --eval-data reports/vla_blind_control_20260920/<real|gray>_panel.jsonl \
  --norm-key vlnv11
python scripts/build_blind_control_review.py
```

`evaluate_joint_repair_controls.py` gained optional `--panel`, `--out-dir` and
`--tag`; its default behaviour is unchanged.
