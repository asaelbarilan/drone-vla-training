# VLM-authored planning: D-101 research protocol

Decision question: which published navigation mechanism gives the VLM authority
to construct and revise a navigation plan, instead of delegating viewpoint choice
to a classical planner? Implement the selected mechanism as an opt-in adaptation
under the paper's fixed task, Gemma backend, sensors and shared SUPER execution.

User correction supersedes D-100 as the next implementation direction. A model
that merely labels targets or approves a classically chosen route does not meet
this intent. Clarification is pending on model-proposed intermediate waypoints
versus a model-authored multi-step route through supplied candidates. Meanwhile
inspect both mechanisms; no runtime architecture is locked before selection.

Reuse D-85's validated 24-primary-work evidence ledger and 41-candidate search as
background. Extend it with explicit plan generation, spatial memory and replanning
works. The first two orientation queries were issued before this addendum; log
that chronology rather than implying prospective registration of those queries.

Search concepts: VLM navigation multi-step subgoals waypoints; VLM-authored spatial
planning; MapGPT adaptive planning; WMNav world-model feedback; aerial hierarchical
semantic planning; FineCog-Nav; STMR; NavGPT; persistent metric-goal planning.
Date coverage: foundational work through 2026-09-12. Primary sources only for
technical claims: author papers, official project pages/repositories and licenses.
Exclude generic summaries, unverified repositories, manipulation-only methods as
primary aerial implementations, and pretrained-navigation claims without weights.

Inspect full method/prompt/output and official resource status for contenders.
Record who proposes candidates, who chooses goals/order, what memory the VLM
receives, how execution feedback triggers plan revision, source observations and
privileged assumptions, training/compute dependencies, code/weights/license and
domain limits. Retain contrary/negative evidence; zero-shot does not mean geometry
or execution is supplied by the model.

Stop after a supported source choice with an exact source-to-adaptation matrix,
resource inventory and falsification tests. Reuse the existing coverage ledger,
add meaningful new methods, and validate the combined evidence schema. Do not run
new model sweeps, cloud calls or held-out seeds. Implement and test locally with
fake inference and saved sensor inputs; real-call validation must have an explicit
bounded purpose and budget. Preserve C5, sensor repair and all historical evidence.
