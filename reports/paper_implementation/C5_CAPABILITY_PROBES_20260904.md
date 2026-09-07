# C5 capability probes: told the answer, it still fails — 2026-09-04

> **PRIVILEGED DIAGNOSTIC. NOT REPORTABLE AS C5 PERFORMANCE.**
> The routes below are derived from `c0`'s successful trajectories, i.e.
> simulator truth handed to the model in words. These runs answer "can the
> decision agent execute a route it is told?" — nothing else. All configs carry
> `privileged_diagnostic` in their tags.

## Three conditions, same seeds, 240 s horizon

| condition | architecture | success |
| --- | --- | ---: |
| baseline, no hint | `c5_onfly_qwen4_native_dynamics` | 1/5 |
| told the winning route, pixel output | `c5_route_hint_s*` | **0/5** |
| told the route, five-word steering output | `c5_route_direction_s*` | **0/5** |
| classical reference | `c0` | **5/5**, 63-84 s |

Being told exactly where to fly made the architecture worse, under both output
representations.

## What the model actually commanded

With the five-word contract, normalised entropy over the vocabulary
(1.0 = uses it, 0.0 = one word forever):

| seed | n | modal word | entropy | distribution |
| ---: | ---: | ---: | ---: | --- |
| 1060 | 23 | 65% | 0.40 | left 15, right 8 |
| 1061 | 185 | 89% | 0.23 | right 165, ahead 18, left 2 |
| 1062 | 239 | 99% | 0.04 | left 236, right 3 |
| 1063 | 239 | 99% | 0.03 | right 237, left 2 |
| 1064 | 239 | 79% | 0.32 | right 189, left 50 |

With the pixel contract, median `u` was 112 on four of five seeds, and the image
centre is 112.

So the model emits one answer and repeats it. The pixel contract's version of
that answer is "the middle"; the word contract's version is "left" or "right".
Changing the encoding changed the constant, not the behaviour.

## Corrections this series forced

**The direction contract's acceptance criterion was wrong.** It asked whether
bearings spread beyond +-10 degrees. Seeds 1061-1064 pass that while emitting a
single word 79-99% of the time — it detects *not-centre*, not *not-constant*.
Future contract experiments need a distributional measure.

**Two readings taken from single seeds were both reversed by later seeds.** After
seed 1060 of the route-hint series the hint looked inert; seed 1063 then showed
it eliminating the geofence deadlock outright (133 refusals to zero, stationary
60% to 3%). After seed 1060 of the direction series the contract looked like it
had fixed steering at entropy 0.40; seeds 1062-1063 came in at 0.03-0.04. In
both cases the first seed was the one that ended early with few decisions.

## Two structural limits in the contract itself

Across all 925 decisions the model chose `hard_left` **zero** times and
`hard_right` **zero** times: the effective vocabulary is the inner three words.

And the vocabulary is under-ranged for these routes. They require turns of
12-72 degrees, and 9 of 16 exceed the +-38 degree maximum a single command can
express, because the bearings are bounded by the camera half-angle.

## An unrelated defect this surfaced

Seeds 1060 and 1061 ended `agent_stopped` — the monitor declaring the mission
complete — at **32.87 m** and **8.50 m** from a 2 m goal radius. On 1060 the
monitor reported `latest_visible=True, latest_scale=large, acquisition_count=2/2`
while the vehicle had moved barely 2 m from its start. This is the acquisition
latch and is independent of the decision agent.

## What is now excluded

The path budget (D-64), the step source (D-62), the coordinate contract and the
prompt (this note and D-66) have each been separately excluded as the cause of
C5's failure. What remains is the model: Qwen3-VL 4B does not steer from vision
in this task, and cannot be talked into a route it is handed in words.

Evidence: D-64, D-65, D-66, D-67 in `docs/RESEARCH_LOG.md`; runs under
`runs/c5_long_s*`, `runs/c5_route_s*`, `runs/c5_routedir_s*`, `runs/c0_long_s*`.
