# Paper-faithful implementation protocol

Search date: 2026-08-25

## Decision question

What is the smallest faithful implementation of each selected paper's autonomy
architecture that preserves its causal mechanism, runs through the testbed's
typed decision interfaces, and can be validated first in the deterministic
local simulator?

## Fixed scope

The review is deliberately limited to the eight systems selected by the user:

1. SUPER
2. AerialClaw
3. See, Point, Fly (SPF)
4. AeroVLA
5. OnFly
6. PMR / Selective Agentic Recovery
7. CognitiveDrone-R1
8. FLIGHT

Related papers are inspected only when a selected paper depends on them or a
benchmark is required to validate the reproduced mechanism.

## Search lanes and synonyms

- Exact paper/system title, author project page, arXiv/publisher full text.
- Official GitHub repository, tagged releases, submodules, license, model and
  dataset links.
- System aliases: AerialVLA/AeroVLA; See-Point-Fly/SPF; PMR/Selective Agentic
  Recovery; CognitiveDrone R1/CognitiveDrone-R1.
- Named predecessor or benchmark used by the selected paper when required to
  understand inputs, outputs, training, or evaluation.

Date range: the selected primary paper regardless of year, plus current
official resources as of the search date.

## Inclusion and exclusion

Include primary papers and official resources that define the executed
architecture, action/decision representation, timing, safety boundary,
training recipe, checkpoint, or evaluation protocol. Exclude third-party
summaries from technical claims. Do not import paper-specific sensors,
controllers, prompts, datasets, or hardware unless they are necessary to the
claimed architectural mechanism.

## Per-paper acceptance gate

An architecture is not marked implemented until all applicable checks pass:

- The primary paper and official resources have been inspected.
- The reproduced mechanism and intentionally normalized details are recorded.
- No policy bearing a foundation-model or learned-policy name is a scripted
  stand-in in the valid configuration.
- Its declared model/checkpoint is loadable, or the configuration fails closed
  with a clear missing-resource error.
- The expected typed decision is produced: `SkillCall`, `WaypointGoal`,
  `KinematicAction`, or `ActionChunk`.
- Paper-defining timing, validation, memory, monitoring, recovery, and safety
  paths are observable in event logs.
- Contract/unit tests pass and a deterministic local-simulator capability gate
  succeeds on development seeds before held-out evaluation.
- The implementation's limitations and deviations from the paper are explicit.

## Sequential stopping rule

Work on one system at a time in the order above. Stop the current system only
when its acceptance gate passes, or when a frozen development gate produces a
documented conclusive rejection (including an unavailable external dependency).
A rejected runnable architecture remains a benchmark result; it is not tuned
until it passes. Do not edit the next architecture while the current one is
unresolved.

## SUPER-specific first gate

Inspect SUPER's official paper and repository, then reproduce the geometric
execution contract needed by this benchmark rather than merely renaming the
existing `fixed_local` planner. The local implementation must expose the
paper-defining planning stages that are meaningful without ROS or real vehicle
dynamics, reject unsafe/infeasible goals, produce collision-aware executable
motion, and establish a high oracle execution ceiling before semantic systems
are evaluated.
