# Documentation map

Four documents, four distinct jobs. Putting a decision in the wrong one is how a
research repository becomes unreadable, so the boundaries are stated here.

| file | job | read it when |
|---|---|---|
| [`RESEARCH_LOG.md`](RESEARCH_LOG.md) | **The decision register.** Every design decision with its rationale, evidence, rejected alternatives and status. Organised by area, stable IDs (`D-01`…), never reordered. | You want to know *why* the testbed is the way it is, or you need to cite a decision in the paper |
| [`ARCHITECTURE_FAMILIES.md`](ARCHITECTURE_FAMILIES.md) | **The design space.** One baseline, five autonomy families, their subfamilies and ablations, plus the nearest published work. | You want to know what an architecture *contains*, or how it maps to a paper |
| [`../CHANGES.md`](../CHANGES.md) | **The chronological record.** What was done, when, and what the measurement said at the time — including the wrong turns. | You want the narrative, or to find when something changed |
| [`../TODO.md`](../TODO.md) | **What is undone.** Open work ordered by what it blocks, each item naming the decision it comes from and its first step. | You are picking up work, or you want to know what the results do not yet cover |
| [`SMALL_VLA_SEARCH.md`](SMALL_VLA_SEARCH.md) | A literature search and its negative result. | You are wondering whether a small aerial VLA can be dropped in |

An item leaves `TODO.md` when it becomes a decision with evidence in
`RESEARCH_LOG.md`. The two are meant to be read together: the log says what is
settled, the TODO says what the settled parts do not yet cover.

## Where a new decision goes

Anything that changes how the testbed behaves, or that rules out an option, gets
an entry in `RESEARCH_LOG.md` with a new `D-nn`. It needs a **rationale** and an
**evidence** line, and `Evidence: none` is an acceptable and useful answer —
it marks the decision as `provisional` and tells a later reader exactly what to
go and measure.

Corrections do not delete the old entry. The status becomes
`superseded by D-nn`, and if a claim was published anywhere it also goes in the
"Superseded and corrected claims" table at the bottom, because a reader who
meets the old claim elsewhere needs to be able to find out that it was withdrawn.
