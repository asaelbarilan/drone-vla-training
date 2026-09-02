# PMR fidelity record

Status: **implementation in progress (2026-08-30)**. The primary paper is
public, but it does not provide source code, learned-CVI weights, feature
normalizers, training logs, or a recovery-reasoner checkpoint. This is a
clean-room mechanism reproduction inside the shared testbed.

## Primary source

- Park et al., *Selective Agentic Recovery for UAV Autonomy with a Persistent
  Mission Runtime*, arXiv:2606.14219v1 (2026),
  <https://arxiv.org/abs/2606.14219>.

## Paper-defining mechanism

1. A competent fixed local flight policy runs continuously.
2. Persistent mission state contains mission memory, verifier state, remaining
   query budget, and executor/logging state.
3. A fixed 18D semantic runtime vector covers kinematics, progress, risk and
   planner state, query budget, battery, command success, and safety history.
4. A pre-deployment sigmoid-linear learned-CVI gate estimates whether invoking
   the reasoner has better short-horizon utility than continuing locally.
5. Admission is
   `guards AND (CVI >= 0.997 OR hard-stuck)`; guards include query budget,
   cooldown, and terminal-radius suppression.
6. The reasoner selects one predefined recovery skill. It cannot issue raw
   setpoints or flight-stack commands.
7. Returned JSON passes parsing, local verification, the safety shield,
   fallback handling, and executor mapping before affecting flight.

A rule-only no-progress trigger is an ablation, not PMR.

## Testbed placement and current implementation

PMR is C6: C3's local waypoint/verifier/SUPER execution remains active, while
reasoning is admitted only for recovery. This normalizes the paper's PPO
Discrete(32) lower policy so the benchmark changes the recovery architecture,
not both the local policy and admission rule.

The shared runtime now exposes an optional `admission` plugin. The
`pmr_cvi` implementation:

- constructs and logs the fixed 18D vector without scenario IDs, map
  templates, raw range arrays, prompt text, or simulator truth;
- loads fitted mean, scale, linear weights, bias, and threshold from a
  versioned checkpoint;
- enforces budget, cooldown, terminal-radius, battery, and hard-stuck guards;
- emits an auditable `admission` event before the existing typed recovery,
  verifier, planner, shield, and controller path;
- fails closed when no trained checkpoint is supplied.

The `pmr_recovery_reasoner` implementation now:

- calls the installed real `gpt-oss:20b` model through the shared inference
  service and requires strict JSON containing decision, reason, symbolic
  option, risk, and confidence;
- rejects coordinates, velocities, trajectories, commands, undocumented
  fields, and incompatible decision/option pairs;
- locally grounds the symbolic choice into the existing bounded skill runtime,
  then uses the common verifier, SUPER planner, shield, controller, and event
  log;
- uses a typed local hold/continue fallback on parse or backend failure and
  never places raw model output in provenance or experiment logs.

Because OnFly's local policy is visual and PMR's recovery reasoner is text-only,
`role_router` composes Qwen3-VL 4B for the policy role with GPT-OSS 20B for the
reasoner role behind the single shared inference/accounting service. The
`c3_onfly_qwen4_native_shield` comparator and
`c6_pmr_qwen4_gptoss` profile share the local policy, verifier, SUPER planner,
controller, native dynamics, and independent shield. The latter fails closed
until `artifacts/pmr_cvi/pmr_cvi_v1.json` is fitted.

No hand-written weights are accepted as learned-CVI. The existing
`bounded_reasoner` remains a scripted structural sentinel and is not a
paper-valid PMR reasoner.

Real static capability verification uses three distinct sensor-grounded states:
blocked geometry, lost target, and stalled progress with visible target. After
the symbolic operation semantics were made explicit, GPT-OSS selected
`local_repair/ascend`, `goal_alignment/scan_left`, and
`goal_resume/approach_target`; a second run reproduced all three decisions and
confidences exactly. Both reports are under `reports/paper_implementation/`.
This proves the parser and constrained semantic selection work, not that PMR
improves flight. That claim remains blocked on paired utility labels and the
trained CVI checkpoint. Changed-file Ruff is clean and the complete repository
regression passes 356/356 tests with zero failures or errors in 496.35 s.

## Locked local training split

Held-out seeds 1-40 remain untouched.

- CVI training: seeds 2000-2015 on `grid_nav` and 2000-2015 on
  `failure_recovery` (32 rollouts).
- Threshold validation: seeds 2040-2047 on each environment (16 rollouts).
- First frozen development gate: seeds 1060-1064, evaluated only after the
  checkpoint, typed real reasoner, prompt, verifier, shield, timeout, and
  logging schema are frozen.

Training labels compare invocation with local continuation over K=5 runtime
steps. The locked utility penalties follow the paper: token 0.10, latency
0.05, safety intervention 0.15, and planner failure 0.05. Ambiguous
near-zero-utility rows are excluded from binary supervision and reported.

## Acceptance gate

- The checkpoint records its exact feature order, normalization, fitted
  weights, bias, threshold, training seeds, validation seeds, and data hash.
- Static tests prove score admission, hard-stuck override, budget/cooldown
  suppression, and terminal-radius suppression.
- A real model returns only a predefined recovery skill plus reason, risk, and
  confidence; parser or backend failure falls back locally.
- Every accepted skill passes the common verifier, SUPER planner where
  applicable, shield, and executor.
- On `failure_recovery` development seeds 1060-1064, PMR succeeds on at least
  4/5 with zero collisions.
- On paired nominal `grid_nav` seeds, PMR succeeds on at least 4/5 and issues
  at most one reasoner call in total.
- C3 local-only and the PMR profile share the same perception, policy,
  verifier, planner, shield, controller, and environment configuration.

Failure is retained as a benchmark result. It is not repaired with simulator
truth, scenario identifiers, scripted recovery selection, or post-gate
threshold tuning.
