# Is there a small VLA we can drop into the C7–C14 slot?

**NO CODE CHANGED.** This is a search result, not an implementation.

**Short answer: no.** Every small VLA with released weights is a *manipulation*
model with a 7-DoF gripper action space. Every VLA with a *drone* action space and
released weights is a 7B OpenVLA derivative. The one model that is both small and
aerial — LiteVLA-H, 256 M, 2.2 GB — has not released weights.

## Constraints this had to satisfy

| requirement | why |
|---|---|
| ≤ ~6 GB VRAM | RTX 4060 Laptop, 8 GB total, 6.94 GB free |
| drone action space | velocity or waypoint. A gripper pose cannot fly a quadrotor |
| released weights | a paper is not a dependency |
| loadable here | `transformers` 4.44.2, or Ollama, or plain PyTorch |
| ≥ ~10 Hz | C7–C11 configure a 10 Hz decision loop |

## What exists

| model | size | action space | weights | fits 8 GB | verdict |
|---|---|---|---|---|---|
| [LiteVLA-H](https://arxiv.org/abs/2605.00884) | **256 M**, 2.2 GB FP16 | velocity / heading / waypoint ✅ | **none** | ✅ | *ideal, unobtainable* |
| [GRaD-Nav++](https://arxiv.org/abs/2506.14009) | small MoE policy | low-level control ✅ | **code only, no checkpoints** | ✅ | needs training + 3DGS scenes |
| [Exp2VLA](https://arxiv.org/abs/2607.03146) | "compact" | drone control ✅ | none found | ? | too new |
| [AerialVLA](https://github.com/XuPeng23/AerialVLA) | 7 B (OpenVLA base) | continuous UAV velocity ✅ | **LoRA only** | 17 GB bf16; ~5 GB at 4-bit | base absent: 14 GB download |
| [CognitiveDrone](https://arxiv.org/abs/2503.01378) | 7 B + 7 B | 4-D action ✅ | — | ❌ | two 7 B models |
| [DroneVLA](https://huggingface.co/datasets/yoofiannan/dronevla-dfr-episodes) | — | aerial ✅ | **dataset only** (330 episodes) | — | useful data, no model |
| [MiniVLA](https://huggingface.co/xintaozhen/MiniVLA) | 1 B (Qwen2.5-0.5B + ViT) | **7-DoF gripper** ❌ | ✅ | ✅ | wrong action space |
| CoTinyVLA *(already on disk)* | 0.9 B | **7-DoF + wrist cams** ❌ | ✅ | ✅ | wrong action space — verified below |
| [SmolVLA](https://arxiv.org/abs/2510.24795) | ~0.5 B | manipulation ❌ | ✅ | ✅ | wrong action space |

### CoTinyVLA, checked rather than assumed

You said it was for robots; the config confirms it exactly:

```json
{ "action_dim": 7, "num_wrist_images": 8, "proprio_dim": 8,
  "base_model_name_or_path": "Qwen/Qwen3.5-0.8B" }
```

7 action dimensions, **wrist cameras**, 8-D proprioception, trained on LIBERO-Plus
tabletop suites. It also declares `transformers 5.7.0`; this machine has 4.44.2.
Not adaptable without replacing the head and retraining — at which point the
backbone is the least of the work.

## The structural reason there is no drop-in

The small-VLA literature optimises for **tabletop manipulation** because that is
where the datasets are (LIBERO, Bridge, DROID). The aerial literature has the
opposite problem: drone action spaces are simple (4-DoF velocity vs 7-DoF pose)
but aerial datasets are scarce, so authors reach for the largest available
pretrained VLA and fine-tune it. Nobody has needed a *small aerial* VLA badly
enough to publish weights, except LiteVLA-H, which did not.

## Options, ranked

### 1. Behaviour-clone a small policy on this testbed — **recommended**

Generate expert trajectories from C0 (the oracle already succeeds on 0.88 of
`grid_nav`), render frames, and train a small policy mapping
(frame, instruction embedding) → velocity. Roughly 5–20 M parameters; runs at
hundreds of Hz; no download.

This is not a fallback — it is **exactly the published recipe**. Exp2VLA distils
Isaac Lab expert rollouts into a compact VLA; GRaD-Nav++ trains its policy in a
3DGS simulator with differentiable RL. Both build the policy rather than
downloading one, for the same reason we would.

- Effort: moderate (data generation is already free; training loop is new)
- Buys: a genuine *learned* visuomotor policy in the C7–C14 slot, fast enough for
  the configured 10 Hz, fully reproducible, zero external dependencies
- Honest limit: it is not a foundation model. No language generalisation beyond
  what we train. But C7–C14's axis is **authority and timing**, not language
  breadth — those are C1–C6's questions, and Gemma already answers them.

### 2. Retarget MiniVLA (1 B) to 4-DoF velocity

Replace the 7-DoF action head, fine-tune on drone data. Needs the same data as
option 1, *plus* a 2 GB download and the OpenVLA fork's `transformers` pinning.
Strictly more work than option 1 for a pretrained backbone whose pretraining is
about grippers.

### 3. OpenVLA-7B + the AerialVLA LoRA you already have, at 4-bit

The only route to a *published aerial* VLA. Needs ~14 GB download (you have 34 GB
free), `peft`, `bitsandbytes`. AerialVLA reports 0.38 s latency on a **4090**; a
4060 Laptop at 4-bit will be slower, so ~2 Hz against a configured 10 Hz — the
same authority/latency mismatch already measured for Gemma.

### 4. Gemma 3 4B emitting velocity directly

Zero new downloads, and the backend already works. But 2.2 s per call cannot
drive a 10 Hz loop. Only honest as a deliberate "a 4B VLM cannot hold action
authority" datapoint — which is a legitimate experiment, just not a VLA.

## If we behaviour-clone: data, action space, and loss

### Why not train on an open aerial dataset?

Fair challenge, and the datasets are real:

| dataset | size | availability |
|---|---|---|
| [OpenFly](https://arxiv.org/abs/2502.18041) | **100 k trajectories, 18 scenes** | open-sourced toolchain + data |
| [UAV-Flow Colosseo](https://arxiv.org/abs/2505.15725) | real-world, language-conditioned UAV control | released |
| AerialVLN / AirVLN | city-scale, game-engine built | released |
| [DroneVLA-DFR](https://huggingface.co/datasets/yoofiannan/dronevla-dfr-episodes) | 330 episodes, 18,565 decision ticks | on HuggingFace |

**They are the right training data for a real result, and they cannot be
evaluated here.** The blocker is the visual domain gap, not the data:

- Those datasets are photorealistic Unreal/3DGS city scenes. Our renderer draws
  flat-shaded grey boxes. A policy trained on one will see nothing it recognises
  in the other, in either direction.
- Evaluating a policy trained on OpenFly requires OpenFly's simulator — Unreal
  Engine based, not installed here, and the AirSim/Gazebo adapters are still
  stubs (Milestone C).
- Their action spaces also need checking before use: aerial VLN datasets often
  ship *discrete navigation actions* ("move forward 5 m, turn 15°") rather than
  the continuous velocity our `KinematicAction` contract carries. That is a
  conversion, possibly a lossy one.

So the split is:

| goal | data to use |
|---|---|
| run C7–C14 **today**, in this testbed | oracle-generated, in-domain |
| a claim about **real aerial VLA capability** | OpenFly / UAV-Flow — gated on Milestone C |

Training on our own oracle is not a shortcut around the open data; it is the
only option that can be *evaluated* before a photorealistic adapter exists. The
policy it produces is a real learned visuomotor policy for this testbed, and
explicitly not a claim about aerial autonomy in the world.

### Do we have enough data? Yes — measured, not estimated

Ten oracle episodes on `grid_nav_vision`, rendering on:

| | |
|---|---|
| samples per episode | **446** (one per 20 Hz control tick) |
| wall time per episode | 0.69 s |
| expert success rate | 8/10 |
| 1000 episodes | **446 k samples, ~12 min** |

Ample for a 5–20 M parameter network, and it costs minutes rather than a
download. Two caveats that matter more than the count:

- **Train only on successful episodes.** The two failures were timeouts running
  the full 1200 ticks, so failed episodes are *over*-represented per-sample while
  demonstrating exactly what we do not want cloned.
- **Diversity, not volume, is the limit.** Seeds vary goal bearing, obstacle
  layout and distractors, but every scene is flat-shaded boxes. The policy will
  generalise across layouts and not at all across appearance.

### Action space: already fixed by the contract

Not a design choice — it is what `KinematicAction` carries and what the
controller consumes, so the policy must emit exactly this or it cannot occupy
the C7–C14 slot:

| dim | meaning | frame |
|---|---|---|
| `vx, vy, vz` | velocity | ENU |
| `yaw_rate_rps` | yaw rate | body |

**4 continuous dimensions.** (`duration_s` is a config constant, not predicted.)

### Supervised, not RL

Behaviour cloning is supervised learning on (observation, expert action) pairs.
No reward, no exploration, no value function. RL is the alternative — GRaD-Nav++
uses differentiable RL in a 3DGS simulator — and it is far more expensive for a
result that this testbed does not need: we want a policy that *occupies the
slot*, not one that is optimal.

### What the policy's job actually is

In the slot we would be training for, **the policy is the driver**. Verified in
`plugins/control/mock.py`:

- `from_action` (C7–C14): takes the policy's velocity and passes it through,
  clamped to the speed limit. Nothing else computes a heading.
- `track` (C2–C6): the *controller* computes velocity itself, with a
  proportional law toward a carrot point on the planner's trajectory. The policy
  only chose a destination.

So a direct-VLA policy is steering at 20 Hz, and a waypoint policy is navigating.
That is the authority axis, and it is why the trained policy must emit velocity
rather than a target: emitting a target would silently make C7 into C2.

From C8 onwards the shield sits between policy and vehicle. It can slow, deflect
or stop, but it never originates a heading — so the policy is still the driver,
with a guardrail.

### DECISION: discretised, **per-dimension bins, 64 per dimension**

I first recommended a joint action codebook and **that was wrong**. Measured on
11,624 expert actions (80/20 split), held-out quantisation error:

| scheme | mean velocity error | p95 |
|---|---|---|
| joint codebook, K=128 | 0.481 m/s | 0.950 |
| joint codebook, K=1024 | 0.295 m/s | 0.650 |
| per-dimension bins, 16 | 0.281 m/s | 0.423 |
| **per-dimension bins, 64** | **0.068 m/s** | 0.102 |
| per-dimension bins, 256 | 0.016 m/s | 0.026 |

A joint codebook over a 4-D continuous space needs exponentially many prototypes
to cover it: K=128 is about 3.4 levels per dimension. Even **K=1024 is worse than
16 per-dimension bins**. It cannot represent arbitrary speed × direction
combinations — `(1,0,0,0)` and `(5,0,0,0)` both have to be codebook entries, and
so does every other pairing.

At 64 bins per dimension the error is 0.068 m/s, which over a 0.05 s control tick
is 3 mm. Negligible against a 3.8 m/s mean speed.

The cross-dimension mode-mixing worry that motivated the codebook is **real but
hypothetical**, and it is 7× cheaper in accuracy to test for it than to prevent
it up front. Use per-dimension bins and measure head-on collisions specifically;
if incoherent combinations show up, revisit then.

Expert action distribution, for the record (25 episodes, 8,428 actions): vx, vy
span ±5 m/s, vz ∈ [−2.4, 3.4], yaw ∈ ±1.5 rad/s. Vertical velocity is used in
41 % of actions and yaw in 80 %, so all four dimensions are genuinely exercised.

### Regression or discretised classification?

Both are defensible and the choice is not cosmetic:

- **Regression** (MSE on 4 dims) matches the contract directly. Simplest.
- **Discretised** (bins per dimension, cross-entropy) is what real VLAs do —
  OpenVLA uses 256 bins per dimension — *because it handles multimodal actions*.

The failure mode that decides it: if two visually similar states have opposite
correct actions — an obstacle slightly left versus slightly right — MSE averages
the two detours and flies **straight into the obstacle**. Averaging is the wrong
answer at exactly the moment it matters. Discretisation cannot average, because
argmax over bins picks one mode.

Our oracle is deterministic, so each individual state is unimodal. But
near-identical *frames* across seeds carry opposite labels, which is the same
problem wearing a disguise — and that is the case discretisation exists for.
**Going discrete.**

#### One trap in discretising: per-dimension bins still mix modes

The obvious implementation is 4 independent softmaxes, one per dimension, 256
bins each — that is what OpenVLA does. It removes averaging *within* a dimension
but not *across* them: argmax can pick `vx` from the go-left detour and `vy` from
the go-right detour, and the combination is a heading the expert never flew.
Independent per-dimension classification is not the same as multimodal-safe.

The fix is a **joint action codebook**: k-means the expert's 4-D actions into
K prototypes (K ≈ 64–256), and classify over K. One argmax selects one whole
action that some expert actually executed, so an incoherent combination is not
representable. Costs a clustering step and caps action resolution at K.

Recommendation: joint codebook, K=128, fitted on the expert set. Report
reconstruction error of the codebook on held-out expert actions first — if
quantisation error is already near the speed limit, K is too small and no amount
of training fixes it.

### The risk that actually sinks behaviour cloning

Covariate shift. A cloned policy drifts slightly off the expert's state
distribution, then finds itself in states the expert never visited and has no
idea what to do — and errors compound. This is the standard reason naive BC
fails, and it will not show up in training loss.

The standard fix is DAgger: run the *student*, and label the states it actually
visits with the expert's action. **We are unusually well placed to do this**,
because our expert is pure geometry (C0 reads the true goal and calls the same
planner), so it can label any state instantly and for free. Papers that clone a
human or an RL expert cannot do that cheaply. Plan for DAgger from the start
rather than discovering the need after the first policy wanders off.

## Deliberately out of scope

- **Quantising further to fit a 7B.** Already measured: only ~0.55 s of Gemma's
  per-call cost was GPU compute. Model size is not the bottleneck on this box.
- **Cloud VLA inference.** Would make every timing measurement a function of the
  network, and timing is half of what this testbed measures.
- **Training a large VLA from scratch.** Not a laptop-scale task.

## Papers

Downloaded to `papers/small_vla/`. See the README there.
