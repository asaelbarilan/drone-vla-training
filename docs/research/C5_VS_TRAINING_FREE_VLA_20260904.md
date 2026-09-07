# C5 OnFly vs the training-free VLAs (SPF, VLFly)

C5 and the C7/C8 training track are separate questions. This note is only about
C5: two published systems reach real-world performance with no training at all,
and one of them is C5's mechanism with a single structural difference.

## They are the same architecture

See, Point, Fly asks a pre-trained VLM for a pixel in the image, unprojects it
through a pinhole model to a body-frame displacement, and repeats closed-loop.
That is C5 OnFly. The convergence is worth stating plainly: C5 was not derived
from SPF, and the fact that an independent group published the same design and
got real hardware results is evidence the substrate is sound.

## The one difference, and it is the one that matters

The two systems disagree about **who decides how far to fly**.

SPF asks the VLM for `(u, v, d_VLM)` — a pixel *and* a discretised distance —
and turns the distance into a step with

    d_adj = max(d_min, s * (d_VLM / L)^p)

No depth sensor is involved. `d_VLM` is the VLM's *intended travel distance*,
not a measurement.

C5 asks the VLM only for `(u, v)` and derives the distance from the depth image
(`onfly.py:509`):

    depth_m = min(max_depth_m, sensed_depth_at(u, v))     # max_depth_m = 7.0
    gated   = depth_m * exp(-0.5 * (theta / (sigma * half_fov))^2)
    range   = max(0, gated - goal_standoff_m)

## Why this is exactly the seed-1060 failure

Two consequences follow from those three lines, and neither is a tuning problem.

**C5 cannot fly past what it can already see.** The travel distance is bounded
above by the sensed depth along the chosen ray. The first surface on that ray is
a hard ceiling on the hop. The standing complaint about C5 — that the value is
past the obstacles and not where it can already see — is not a prompt weakness.
It is a closed-form property of `range <= sensed_depth`.

**Looking sideways is penalised.** `bearing_gated_range` multiplies the range by
a Gaussian in the image bearing, so a pixel chosen off-axis yields a shorter hop
than the same pixel chosen ahead. Exploration requires looking away from the
current heading, so the architecture shortens precisely the movements that would
gather new information. A prompt asking the model to explore is fighting the
geometry underneath it.

This also explains why the D-55 viewpoint prompt failed. It changed which pixel
the model chose; it could not change the fact that the hop is capped by the
depth at that pixel.

## Is swapping this "hiding the boundary"?

No — it moves in the opposite direction. SPF uses **no depth sensor**, so
adopting `d_VLM` removes a privileged input rather than adding one. C5 currently
enjoys synchronised metric depth that SPF does without. The change makes the
substrate weaker and the task harder, which is the right direction under the
standing constraint.

## VLFly is a different lesson

VLFly (LLaMA + CLIP + ViNT, training-free, real Tello Edu at 7-10 Hz) does not
share C5's mechanism. It retrieves a *goal image* with CLIP and plans waypoints
toward it, emitting continuous linear and angular velocity. The transferable
idea is the goal-image retrieval, which is a way of representing "what I am
looking for" that survives the target being out of frame. Worth recording, not
worth adopting yet.

## Proposed experiment

Add `d_VLM` to C5's existing JSON schema as a third field and select the step
with SPF's adaptive curve instead of the sensed depth, leaving the prompt, the
pixel contract and everything else fixed. That isolates the single variable and
is a clean ablation of C5 rather than a new architecture. Run it on the retained
five seeds, 1060 included, against the frozen C5 numbers.

## Implementation status — 2026-09-04

Built and unit-tested; **not yet evaluated**.

`OnFlyDecisionAgent` takes `step_from_model`, default `False`. With it off,
nothing about C5 changes and every frozen number stays reproducible. With it on,
the decision schema carries a third field `d` in `1..step_levels` and the step
comes from SPF's curve instead of the depth image.

`step_scale_m` is 7.0 — deliberately equal to C5's own `max_depth_m`. The first
draft used 9.0, which would have confounded two variables at once (*who* decides
the step, and *how far* a step may be) and would additionally have tripped the
inherited `max_waypoint_distance_m: 10.0` at image edges, where the 3-D ray is
longer than its camera-forward component. At 7.0 the maximum reach is identical
to the frozen profile and only the source of the distance differs. The ladder is
1.4, 2.8, 4.2, 5.6, 7.0 m.

The sensed depth and bearing gate are still computed and written to provenance
alongside the executed range, so a single run carries both step sources and they
can be compared directly:

| field | meaning |
| --- | --- |
| `sampled_depth_m` | depth at the chosen pixel, capped at `max_depth_m` |
| `gated_range_m` | what C5 *would* have flown |
| `executable_range_m` | what was actually flown |
| `step_source` | `depth` or `model` |
| `model_step_level` | the `d` the model named, or `0` |

Five unit tests in `tests/unit/test_onfly.py` cover the curve and its floor,
schema presence and absence, the fact that one pixel yields two ranges purely
from `d`, the unchanged default, and fail-closed on a missing `d`.

### Why no numbers yet

The evaluation needs the GPU alone: the profile loads Qwen3-VL 4B for both the
policy and the monitor on an 8.2 GB card. At the time of writing `nvidia-smi`
reported 99% utilisation and 7.8 GB held by UE4Editor, `valley_operator_experiment.py`
and a loaded llama-server — a separate experiment already in progress. A second
4B profile would have fought for the remaining ~370 MB, and a result measured
under that contention would not be worth having. Run
`scripts/run_c5_spf_step_seeds.sh` once the card is free; it runs all five seeds
and writes a per-seed analysis JSON in the same format as the frozen baseline.

### The comparison to make

Against `C5_RETAINED_FIVE_SEED_RESULTS_20260901.md`: 1/5 success, seed 1060 at
43.206 m final with 0/89 visible decision frames. The hypothesis predicts more
visible decision frames, not necessarily more successes — if the drone can
commit past an occluder it should *see* the target more often, and acquisition
is the step that currently never happens on 1060, 1062 and 1063.

Guard against the null result that looks like a pass: if the model names `d=1`
on nearly every decision, the ablation reduces to a fixed 1.4 m hop and proves
nothing. Check the `model_step_level` histogram before reading anything into the
distances.

## Correction — the experiment above should not be run as specified

Two measurements taken before spending GPU time invalidate the plan in this
note. Both are recorded in full as D-62 and D-64.

**The step length barely reaches the vehicle.** Between consecutive decisions
the drone travels a mean of 0.517 m against a mean commanded range of 5.315 m —
9.7% of the step, with the decision interval at 1.000 s and top speed 0.6 m/s.
The verifier accepted 89 of 89 proposals. Swapping the *source* of the distance
therefore changes almost nothing; only the waypoint's direction survives
replanning. The transferable difference from SPF is that SPF **executes** the
step it names, which is a scheduler property, not a policy parameter.

**And the benchmark does not pose a search problem.** The target is dead ahead
at 35 m on all five retained seeds — the seed varies the obstacles, not the
bearing. The path budget is 54 m against a 35 m straight-line distance, so 19 m
of slack covers every detour. Outcome tracks the number of occluders on the
direct ray: one occluder succeeds, two or three never acquire, and the only seed
with a clear ray is the only one that sees the target at all.

So the whole framing of this note — C5 cannot look past what it can see — was
answering a question these seeds do not ask. The implementation is kept because
the commitment experiment will need a model-named step, but it is not the fix,
and it should not be run against this benchmark expecting a signal.
