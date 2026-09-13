# AerialClaw fidelity record

Status: **accepted and frozen (2026-08-25)**. The mechanism and gate below
were fixed before changing C1; the saved gate now passes.

## Sources inspected

- Li et al., *AerialClaw: An Open-Source Framework for LLM-Driven Autonomous
  Aerial Agents*, arXiv:2606.12142v1 (2026),
  <https://arxiv.org/abs/2606.12142>. The complete five-page paper was
  inspected.
- Official source repository, <https://github.com/XDEI-Group/AerialClaw>,
  commit `e01adaa73c38fb10ec4bc5e8c0f71915cc7490a8`, inspected 2026-08-25.
- Official `AerialClaw2.0` GitHub release (commit `88e9d9f`) and the repository's
  deployment, LLM configuration, skill, perception, architecture and safety
  documentation.

The official code is MIT licensed. It releases no trained checkpoint, training
dataset or quantitative evaluation harness. The paper reports demonstrations,
not a benchmark table. Its model interface is deliberately provider-agnostic
and accepts OpenAI-compatible cloud or local models.

## Paper-defining mechanism

AerialClaw is a closed-loop **brain-skill-runtime** agent, not a one-shot plan
and not a fixed skill program. At each iteration the LLM receives the mission,
documented identity and body/capability bounds, the current semantic world
state, bounded working history, relevant experience and soft-skill strategy.
It emits an inspectable JSON decision for exactly one next hard-skill call (or
an explicit done/stuck verdict). The runtime validates the skill name and
arguments before dispatch; the next model call receives the resulting state and
execution feedback.

The paper's complete system also contains passive perception plus on-demand VLM
inspection, a four-layer memory, post-task reflection, platform adapters and a
Web console. The causal mechanism tested at C1 is the model-driven incremental
composition of validated atomic skills. A deterministic command parser is not
that mechanism.

## Official implementation audit

The official `brain/agent_loop.py` implements
`observe -> think -> act -> observe result -> reflect`, JSON parsing, one skill
per iteration, relevant soft-skill injection, action history, passive
perception, experience retrieval and explicit done/stuck outcomes.
`skills/registry.py` exposes a documented skill catalog, while
`runtime/agent_runtime.py` and `runtime/exector.py` check capability membership
and preconditions before dispatch.

The current official repository also contains
`brain/chat_mode.py::_fallback_single_action_plan`, added for simple commands
when the LLM channel is unavailable. That convenience path is intentionally
excluded: a model or parse failure must fail the experimental episode, never
be relabelled as model success. The repository's YAML safety envelope is more
complete than the enforcement visible in its executor; this benchmark uses its
already-tested common verifier, SUPER planner and safety boundary rather than
claiming the YAML alone is enforcement.

## Testbed realization

| Paper component | C1 realization | Fidelity class |
|---|---|---|
| LLM agent loop | real local LLM call each decision; JSON-schema-constrained one-step decision | reproduced |
| hard skills | typed `SkillCall` vocabulary expanded only by `SkillRuntime` | reproduced and normalized |
| soft skills | relevant Markdown strategy loaded into the prompt; never directly executed | reproduced |
| SOUL/BODY documents | packaged Markdown identity plus dynamically generated mission/body/capability document | reproduced/normalized |
| current world state | shared `ObservationPacket` and `PerceptionState`, rendered as semantic text | surrounding sensing normalized |
| working/skill memory | bounded short-context plugin plus the policy's prior decision/reflection and last routing feedback | mechanism-preserving normalization |
| post-task reflection database | disabled during scored sweeps; fixed read-only lessons may be supplied by profile | intentionally excluded from scoring |
| passive perception | shared deterministic perception stream at every decision | surrounding sensing normalized |
| active VLM skill | not used by C1 local semantic-sensor profile; later vision-rich profiles may add it as a hard skill | deferred surrounding modality |
| runtime safety/adapters | typed router, shared SUPER planner/controller and common safety contracts | surrounding infrastructure normalized |
| Web console/dynamic code/device protocol | excluded | non-causal product infrastructure |

Dynamic cross-episode skill generation and memory writes are excluded from
benchmark scoring because their behavior depends on episode order and would
leak development episodes into later seeds. This is a limitation relative to
the complete personal-agent system, not evidence that the feature is absent
from AerialClaw.

## Model and resource provenance

The current-best normalized profile uses locally installed `gpt-oss:20b`
through Ollama. The
installed manifest digest is
`17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7`.
The installed GGUF is MXFP4, 20.9B total parameters (3.6B active per token),
advertises completion/tools/thinking capability and occupies 13,793,441,244
bytes. OpenAI's model card and repository release it under Apache 2.0 plus the
gpt-oss usage policy. AerialClaw does not prescribe this model; the model is a
declared normalized backend selected because the official system is
model-agnostic and the development gate showed the smaller 2.3B probe model
systematically violated the skill protocol on occluded-target cases. The 20B
model is locally loadable without credentials and passed that controlled
capacity case with two semantic calls and a correct terminal stop.

Primary model sources: <https://openai.com/index/gpt-oss-model-card/> and
<https://github.com/openai/gpt-oss>.

The scoring profile uses greedy decoding, a pinned sampling seed and a JSON
schema. The separate low-effort reasoning channel is enabled because the
installed Harmony/Ollama path otherwise returns empty structured content. Live
latency is recorded; a frozen **8.5 s** resident-model role charge is used for
deterministic simulation timing. Missing Ollama, a missing model, empty output,
invalid JSON, an unknown skill or invalid arguments is an explicit failure.
There is no script, oracle or privileged fallback.

## Predeclared AerialClaw acceptance gate

Held-out seeds 1-40 remain untouched. Capability development uses seeds
**1020-1024**, chosen before implementation and distinct from SUPER's
1000-1019 gate.

AerialClaw/C1 is accepted only if all of the following hold:

- contract tests show a real non-empty inference result is required, malformed
  or unavailable model output fails closed, and only the mission's documented
  bounded skills can enter the router;
- mechanism tests show the dynamic BODY/skill catalog and relevant Markdown
  soft skill are present in the prompt, prior reflection plus routing feedback
  reach the next iteration, and removing the strategy or feedback measurably
  changes either the prompt/model decision or trajectory;
- event logs contain real policy inference calls, typed skill proposals,
  skill expansion, SUPER plans, decision ages and any validation rejection;
- no C1 event or policy input contains `ObservationPacket.privileged`;
- the real-model normalized profile completes at least **4/5 `grid_nav`**
  episodes and at least **2/5 `object_search`** episodes on seeds 1020-1024,
  with zero collisions and no runtime/model fallback;
- two repeated runs of `grid_nav` seed 1020 agree on success, termination,
  typed decision sequence and final distance within the testbed's documented
  real-model tolerance. Here the typed sequence is the ordered `(decision
  kind, skill)` signature. Full argument dictionaries are retained and exact
  argument equality is reported separately; continuous sensor-derived
  coordinates/tolerances and free-text stop reasons are not decision types;
- focused tests, configuration validation and the full local regression suite
  pass.

The lower object-search threshold is deliberate and was set before results:
C1's scientific falsifier is failure on visually grounded tasks. Requiring it
to equal a VLM waypointer would select away the very family limitation the
benchmark is designed to measure; requiring non-zero semantic search still
prevents a merely wired agent from passing.

## Acceptance evidence

The definitive verifier is `scripts/verify_aerialclaw_gate.py`; its
machine-readable result is
`reports/paper_implementation/aerialclaw_gate.json`.

- `grid_nav`, seeds 1020-1024: **5/5 success**, zero collisions and zero
  runtime errors;
- `object_search`, seeds 1020-1024: **5/5 success**, zero collisions and zero
  runtime errors (the predeclared requirement was 2/5);
- every episode contained real `gpt-oss:20b` inference, typed model-authored
  skills, runtime verification and shared SUPER plans;
- repeated `grid_nav` seed 1020 matched on success, termination, ordered typed
  signature, exact full arguments and final distance (delta 0.0 m);
- held-out seeds 1-40 were not used;
- C1 config validation and changed-file Ruff pass;
- focused freeze suite: **78 passed**; complete repository regression:
  **280 passed in 405.05 s**.

## Substrate defects exposed before acceptance

The gate was not made to pass by adding a target script. Development exposed
and fixed four shared execution defects: duplicate active decisions evicted
real observations from `ShortContext`; SUPER collapsed same-XY altitude goals
to a zero-length 2-D path; random simulator obstacles contradicted the declared
ground-attached column model; and the verifier confused route obstruction (a
planner responsibility) plus a no-hit range-horizon sentinel with an invalid
endpoint. The corrected SUPER gate was rerun and remained 20/20 in both of its
regimes with zero collisions and zero shield interventions.

Search remains model-authored. The soft skill supplies a frozen set of
launch-body-relative, range-fan-safe coverage options; the LLM chooses one hard
skill per turn, and no option depends on target coordinates or scoring truth.

## Development extension D-105 (2026-09-13)

The frozen text-only gate above is preserved. The opt-in aerialclaw_visual_agent
adds a requested detect_object information skill: text LLM chooses inspection;
Gemma consumes one fresh RGB frame, depth/odometry ground its object estimate;
LLM then chooses goto and the existing skill executor/SUPER runs it. No continuous
image-space motion policy is introduced. Current extension is a normalized single-
object tool, not a full upstream perception reproduction. A separately named 3%
local depth refinement handles small pixel misses only for one unambiguous surface.
Known-coordinate completion now validates the explicit public instruction/odometry.
See reports/aerialclaw_tools_20260913/REPORT.md: coordinate and visible cases pass;
search remains unvalidated after corrected strategy advice. Do not merge these
results with the frozen GPT-OSS semantic-sensor gate or interpret unmatched charges
as an architecture-only comparison.

## D-107 named inspected-search and ordered-task extensions

c1_inspected_search_gemma_dev counts requested negative-inspection views rather
than physical rotation and bounds per-scan angle. c1_ordered_requested_gemma_dev
supports two model-selected perception queries and odometry-derived visit/dwell
validation from the explicit public task. No model-produced image point directly
commands movement; only subsequent selected hard skills reach shared SUPER.
These are named development adaptations, not claims of full paper reproduction.
Final search flight failed through repeated detection; final ordered flight completed
red but never requested blue. Initial inherited-strategy failure is preserved.
See reports/targeted_contracts_20260913/REPORT.md for confounds and exact evidence.
