# What remains before full training

The D139 experiment is a bounded pipeline/data comparison, not full VLA training.

1. **Learned action correctness.** Valid FRD JSON is necessary but insufficient.
   Pass paired image/instruction tests, braking HOLD and terminal STOP; measure
   premature STOP, stationary collapse, quantization error and saved-action replay.
   Compare actual closed-loop flights; loss alone is not the acceptance gate.
2. **Paper task coverage.** Current data supports narrow public-coordinate and
   visible-color yaw diagnostics. Add varied altitude/vertical motion, obstacles,
   initially hidden targets/search, visual state reasoning, conditional branches,
   ordered missions with observable history, recovery and continuous tracking.
   Preserve the paper's eight categories and all existing architecture baselines.
3. **Other simulator and real-flight data.** No external/real action rows are
   admitted yet. Audit licensed episode samples with synchronized sensor/state/
   command timestamps, camera calibration, native frames/units and terminal
   semantics. Do not label inferred pose differences as commanded velocities or
   invent missing cameras. Test execution adapters in each target simulator.
4. **Generalization splits and adequate coverage.** Count independent scenes,
   episodes, hours, actions and instruction families rather than storage size.
   Keep current development validation; reserve separate unseen sites, simulator
   domains and instruction compositions for transfer. Held-out seeds1-40 remain
   untouched. Add source-balanced as well as task-balanced sampling when domains
   are admitted. No fixed example count guarantees adequacy.
5. **Compute and deployment budgets.** Measure throughput and memory on the
   chosen full model/context. If cloud is needed, present the exact instance,
   compute/storage retention and maximum charge for approval before launch and
   again before training, as requested. No cloud budget is inferred from credits.
   For real-time flight, also verify onboard latency, controller rates and
   watchdog/intervention behavior; current offline simulation pauses for inference.

Go/no-go: scaling becomes justified when the small experiment learns the intended
visual/action distinctions, audited coverage spans the declared task scope, and
per-task/per-domain validation improves without critical control regressions.
Passing the current narrow pilot would not by itself justify real deployment.

Source: docs/research/VLA_DATA_EXPANSION_PLAN.md (D127),
docs/CAPABILITY_SCENARIOS.md (D103), D138 data audit, D139 frozen protocol.
