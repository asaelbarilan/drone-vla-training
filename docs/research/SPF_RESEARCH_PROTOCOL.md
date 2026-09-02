# See, Point, Fly evidence protocol

Search date: 2026-08-25

## Decision question

What is the smallest paper-faithful See, Point, Fly (SPF) implementation that
preserves its causal visual-semantic waypoint mechanism inside C2's typed
`WaypointGoal -> router -> SUPER -> controller` path, runs with a real local
model in the deterministic simulator, and does not import target truth,
renderer-specific rules, or paper-specific flight-control advantages?

## Fixed constraints and acceptance needs

- Implement SPF as C2, after frozen SUPER and AerialClaw and before any later
  paper family.
- Use the existing testbed contracts and local deterministic simulator first.
- Held-out seeds 1-40 remain untouched; new capability tuning uses development
  seeds above 1000 and does not reuse AerialClaw's 1020-1024 gate.
- Preserve SPF's actual model inputs, pointing/waypoint representation,
  temporal loop and stopping semantics. Normalize only surrounding simulator,
  planner and controller infrastructure.
- A model/checkpoint must be loadable under its license or the configuration
  must fail closed. A scripted stand-in cannot satisfy the paper gate.
- Predeclare a capability/mechanism gate before tuning.

## Search lanes

1. Exact title and aliases: "See, Point, Fly", "See Point Fly", SPF drone/UAV,
   visual-language navigation, point-and-fly, pixel/point waypoint prediction.
2. Official author/project pages, paper PDF, repository, releases, issues,
   datasets, checkpoints, model cards and licenses.
3. Direct aerial visual-language waypoint systems and the papers SPF compares
   against.
4. Foundational open-vocabulary grounding, referring-expression localization,
   image-goal navigation, metric depth/unprojection and waypoint prediction
   used by or competing with SPF.
5. UAV semantic-navigation datasets and benchmarks, especially those matching
   egocentric aerial imagery and language goals.
6. Recent (2023-2026) aerial VLM/VLA navigation, plus foundational works cited
   by retained systems.
7. Negative evidence: sim-to-real/viewpoint transfer, monocular range failure,
   latency/staleness, false grounding, collision/stopping failure and missing
   resource releases.

## Inclusion and exclusion

Retain primary papers and official resources that materially define SPF's
inputs, outputs, model/training, waypoint/control handoff, timing, datasets,
evaluation, failure cases, reusable weights or licensing. Retain benchmark and
negative-evidence sources needed to design a falsifiable local gate. Exclude
third-party summaries from technical claims, manipulation-only point policies
without transferable evidence, generic LLM planning papers with no visual
grounding mechanism, and systems whose only relevance is shared vocabulary.

## Required ledger and stopping rule

Screen at least 30 candidate works; retain at least 20 with meaningful
inspection, including at least 15 primary research sources, three sought direct
solutions and three sought dataset/benchmark sources. For each retained work,
record the fields required by the evidence-first research skill, using
`not_reported` rather than inference. Stop only after the exact SPF paper and
official resources are fully inspected, material alternatives are compared,
resource/license availability is checked, and the evidence ledger validates
with the skill's validator.

Architecture and gate locking occur only after the evidence matrix and resource
inventory are complete.
