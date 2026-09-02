# C5 seed 1060 — visual error analysis

Date: 2026-09-02. Diagnosis only; no behaviour changed.
All 59 decision frames were recovered by replaying the stored control commands
through the deterministic environment; the replay reproduces the recorded final
distance of 32.19 m exactly. Sheet: `reports/videos/c5_s1060_error_sheet.png`.

## What the frames show

At **t=0 the goal is dead ahead (bearing +0°) and the VLM pointed almost exactly
at it.** The first decisions are not wrong. An obstacle wall stands between the
vehicle and the target, the local planner deflects around it, and the heading
then slides +29° → +97° → −64° → −138° and never returns. The target is behind
that wall for the whole episode and is visible in 0 of 59 frames.

So the early semantics were right and the vehicle lost the corridor while
detouring. That is a heading-recovery failure, not a grounding failure — and the
prompt already contains a corridor-correction rule for exactly this case
("turn toward the RIGHT side of the current image until the heading returns near
0 degrees").

## Why the rule does not work: the output channel is saturated

| | |
|---|---|
| chosen pixel `u` | median **116**, mean 116, std 27.8 — the image centre is 112 |
| chosen pixel `v` | median **114**, mean 111, std 25.6 |
| commanded bearing relative to current heading | median **7.8°**, mean 9.9° |
| decisions within ±10° of straight ahead | **59%** |
| range used, of the ±45° available | −32° … +35° |
| decisions outside the ±30° corridor | 43 of 59 |
| of those, model steered back toward the corridor | **25/43 = 58%** (chance is 50%) |

**Qwen3-VL 4B answers "the centre of the image" almost every time.** It is not
using the image-space action channel to steer. The heading is therefore set by
planner deflections around obstacles, not by the model, which is precisely why
the trajectory random-walks away from a corridor the prompt keeps asking it to
hold.

This is the same shape as the earlier Gemma 3 4B result, which emitted the centre
pixel `(100,100)` on 14 of 33 and 19 of 33 decisions.

## Consequence for prompt refinement

Prompt refinement cannot reach this behaviour. The instruction is present, is
specific, names the direction and the pixel range to prefer, and is followed at
chance. Adding coverage wording was already rejected at 0/89 and 0/89
(`C5_VIEWPOINT_PROMPT_EXPERIMENT_20260902.md`); this measurement explains *why*
that experiment failed rather than merely recording that it did.

The finding is a **model-capability result**, which is a legitimate outcome for
the paper: at 4B, given OnFly's pixel-goal schema, the model does not exercise
the action channel, so the architecture's semantic authority is nominal rather
than real.

## The one refinement still worth testing

Change the *representation*, not the wording. If the pixel channel is saturated
at the centre, ask for a choice the model can actually express — a small discrete
set of directions (hard left / left / ahead / right / hard right, plus turn
around) — and map that to a bearing. Judge it on whether commanded bearings
spread beyond ±10°, not on success.

That stays inside the paper's "VLM chooses the direction" mechanism and adds no
colour detection, simulator truth, scripted search, or weaker substrate. If the
spread does not change, the capability conclusion above is confirmed on two
independent output representations, which is a stronger result than either alone.
