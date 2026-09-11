# Five bounded debugging trials: navigation remains unresolved

2026-09-11, D-87–D-93. All five trials used development seed **1061** and the same repaired local **gemma4:e2b**. These are adaptive trials on one seed, not a five-seed evaluation. No cloud inference, held-out seeds, new backbone loads or task changes. Three additional local saved-image recognition calls followed the flights. No run remains active.

## Outcome

No trial completed the mission. Every trial timed out without collision or premature stop. No experimental profile was promoted; the original active development profile remains unchanged.

| Run | Profile | Closest distance, m | Final distance, m | End |
|---|---|---:|---:|---|
| 1 | c5_gemma_ground_monitor_dev | 14.15 | 14.15 | timeout |
| 2 | c5_gemma_grounded_policy_dev | 21.80 | 40.25 | timeout |
| 3 | c5_gemma_attribute_guard_dev | 32.94 | 72.45 | timeout |
| 4 | c5_gemma_guarded_monitor_dev | 14.32 | 14.62 | timeout |
| 5 | c5_gemma_fresh_guarded_monitor_dev | 32.59 | 77.18 | timeout |

Historical repaired target-stop baseline on this seed: closest 13.22 m, final 20.18 m, timeout. None of the new variants improved closest approach over that baseline. Final distance alone would overstate improvement in runs 1 and 4. Removing only the previous-point cue in run 5 also regressed; copying was observable but not established as the primary cause.

## What was debugged and changed

1. **False identity accepted as arrival evidence.** The saved false-stop image is a gray obstacle. Prior `target_consistent` meant stable 3-D geometry, not verified object identity. D-87 separates one-image grounding from metric arrival and distinct-frame confirmation. It remains an opt-in experiment; one-image recognition loses useful temporal context and is not accepted as a general replacement.
2. **Contradictory semantic claims.** D-88 makes target versus exploration explicit and logs visual evidence. The model repeatedly writes “gray rectangular building” while selecting `target` for a red-target mission. D-89 compares the VLM-reported candidate color with the explicit positive mission color. In run 3 it rejected 48 contradictory claims. Exploration alternatives remained model-selected, but were poor and led away from the goal. There is no RGB color detector, simulator truth or scripted target search in the policy.
3. **Weak variants set aside.** D-90 restores the original waypoint policy and isolates the guarded monitor. D-91 tests removal of only the previous-point cue. Both remain unaccepted candidates. Historical profiles are intact and all code/config changes have separate commits.
4. **Evaluation bug corrected.** D-92 scores monitor answers against `evidence_observation_seq`, not the image at response completion. The camera moves during inference. Earlier intermediate visibility-accuracy values in CHANGES.md, D-87/D-90 and commentary are superseded by the source-aligned results below. Success, collision and distance measurements were unaffected. Both replay analyzers now count missing source-frame matches explicitly.
5. **Evidence logging repaired.** Normalization used to discard some grounding descriptions. These survive in the new logs; candidate scale and geometric consistency are explicitly distinguished from visual identity.

## Corrected monitor evidence

All monitor events matched their source observation. TP/FN refer to frames where the red target body is visible; FP/TN to absent frames. Visibility scoring is offline only. Trajectories differ, so these are diagnostics rather than a matched-input accuracy ranking.

| Trial | TP | FN | FP | TN |
|---|---:|---:|---:|---:|
| Historical baseline | 12 | 5 | 26 | 2 |
| 1: current-frame monitor | 1 | 16 | 7 | 21 |
| 2: grounded policy | 0 | 1 | 13 | 31 |
| 3: attribute-checked policy/monitor | 0 | 0 | 0 | 45 |
| 4: original policy, guarded monitor | 3 | 6 | 0 | 36 |
| 5: same, without previous-point cue | 0 | 0 | 0 | 45 |

Runs 3 and 5 contain no target-visible monitor inputs. Their 100% overall visibility accuracy does **not** demonstrate target recognition. Run 4 rejects absent views but misses 6/9 positive views. Policy waypoints need not lie on the target, so the earlier off-bbox policy scores cannot automatically be called grounding errors. Explicit monitor target claims are the appropriate identity evidence.

## Saved-image controls: the remaining blocker

Exactly three calls used the actual guarded-monitor prompt/schema after navigation ended:

- Gray false-stop image: correctly reports absent; no coordinates.
- Clear red approach image from a previously successful flight: describes a vertical red rectangle, but reports absent and assigns blue as the candidate color.
- Genuine-arrival image filled with red: reports red, but absent. A single solid-color image is ambiguous without history, so this is a limitation of the current-image contract rather than proof of inability to recognize a tower in general.

These are recognition checks only, not new navigation trials or geometric-arrival results. The visible approach failure demonstrates that visual description can contain the target's appearance while the structured target decision is wrong. This implicates semantic interpretation/output binding under this prompt and rendering. It does not establish that the task is invalid, that Gemma is blind to color, or that C5 planning fundamentally cannot work.

The renderer draws landmarks as projected colored rectangles, not detailed 3-D towers. RGB and depth both include admitted landmarks; occlusion is applied to observations. This representation may contribute to the semantic mismatch, but it was not changed. A prior rendering-legend probe also failed, so merely adding another legend sentence is not an evidence-backed fix.

## Retention and next decision

Keep the diagnostic alignment/logging fixes. Keep the experimental semantic guards and policy variants available for replay, but **do not promote any navigation variant**. Their code guards are tested; the real model still fails positive recognition and useful exploration. The five-flight budget is exhausted and no further calls are scheduled.

Before another navigation sweep, establish a passing positive/negative image-grounding contract on saved frames, with actual target point accuracy and visibility scored separately. Use a fixed small set that includes distractors, partially visible targets and close views. A stronger-model comparison, when explicitly available within free quota, would help separate model limitations from interface limitations; it must not reuse interrupted cloud flights as completed evidence. Do not weaken the task or feed scoring truth into control. The present evidence does not support a general planning conclusion for the paper.

## Reversibility and validation

Rollback checkpoint: `3147bd4`. Relevant change commits:

- `c87aff6`: current-frame grounding monitor.
- `5eb8b9d`: preserve grounding captions.
- `9d8f92a`: explicit target/exploration policy.
- `9f2fdc0`: declared color consistency.
- `f3f27d5`: original-policy guarded-monitor profile.
- `0488cef`: previous-point cue-only profile.
- `bfc2652`: correct source-frame monitor scoring.

Each change and outcome is recorded in CHANGES.md and committed separately. Defaults were preserved, so no failed experiment needs to be selected to use the prior system. Full final validation: **323 unit/contract tests pass**, focused Ruff checks pass, and diff formatting checks pass. All six replayed trajectories (baseline plus five trials) reproduce final distance exactly; source-frame matching has zero unmatched monitor events. These software checks do not establish navigation competence.

Data: `reports/paper_implementation/AUTONOMOUS_RUNS_20260911.json`, per-trial `*_TRACE_20260911.json`, `BASELINE_SOURCE_ALIGNED_20260911.json`, and `GUARDED_MONITOR_FRAME_CHECKS_20260911.json`. Image fixtures and the bounded recognition-check script are committed. Credentials were not read or staged.
