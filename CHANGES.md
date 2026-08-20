# Build log

## Behaviour-cloned policy: pipeline works, policy does not navigate

The full path is built and runs end to end — `uavlab collect` → `uavlab train` →
a registered `learned_visuomotor` plugin → `c7t`/`c8t` configs flying in the same
runtime as every other architecture. **The trained policy itself does not
navigate**, and I now know why with evidence rather than suspicion.

| stage | state |
|---|---|
| expert collection | ✅ 16,747 samples from 156 successful episodes, 630 MB, ~5 min |
| action discretisation | ✅ 64 bins/dim, 0.067 m/s quantisation floor |
| network | ✅ 427 k parameters, 1.0 ms forward pass |
| training | ✅ 110 s on GPU, stop-head recall 1.00 / precision 0.96 |
| plugin + configs | ✅ `c7t`, `c8t` run in the normal runtime |
| **navigation** | ❌ **0/5 success. c7t collides 5/5; c8t survives but wanders** |

### Two failures found by measuring, not guessing

**1. Causal confusion — the policy learned to copy its own velocity.**

First trained policy froze at 0.12 m/s on a fixed heading for a whole episode,
while scoring r = 0.87/0.93 correlation with expert actions on held-out data.
Open-loop excellent, closed-loop inert. The cause:

| | |
|---|---|
| `corr(own velocity, expert action)` | **0.92** |
| velocity error of *simply echoing your own velocity* | 1.174 m/s |
| velocity error of the trained policy | **1.307 m/s — worse than the echo** |

Velocity is a lagged copy of the previous command, so it is a near-perfect
shortcut, and the network took it and ignored the image entirely. From a
standstill, echoing your own velocity means commanding zero forever.

This is the copycat problem (de Haan et al. 2019, Wen et al. 2020). Fixed by
withholding velocity from the policy input — attitude only. After the fix the
policy genuinely moves, and its honest error rose to 1.875 m/s, which is the
real difficulty of the task rather than the shortcut's flattering number.

**2. The label is not a function of the image, 58.7 % of the time.**

| training frames | 16,747 |
|---|---|
| frames that contain the target | 6,909 (**41.3 %**) |
| frames with **no** target visible | 9,838 (**58.7 %**) |

The oracle flies toward a goal it reads directly from ground truth — *through
walls*. On the majority of frames the student is being asked to predict a
direction that the image does not determine. That is irreducible label noise, not
an optimisation failure, and no amount of training, capacity or epochs removes it.

This is the privileged-information gap in teacher/student imitation, and it was
foreseeable: it is written down in `docs/SMALL_VLA_SEARCH.md` as the covariate-
shift risk, and I under-weighted it.

### What would actually fix it

1. **Give the student memory.** A frame stack or recurrent state lets it
   integrate where the target was last seen, which is what makes the other 58.7 %
   of states predictable. Closest to what a real VLA does.
2. **Use a non-privileged expert.** Clone something whose behaviour is a function
   of the student's observation space — the scripted `vlm_waypoint` with memory,
   rather than the oracle. The teacher becomes imitable by construction.
3. **DAgger.** Still needed for covariate shift, and cheap here because the
   oracle can label any state instantly. Does not fix (2) on its own.

Options 1 and 2 are complementary and both are real work. Not started — this is
a design decision, not a tuning knob.

### Honest status

What exists is a working *pipeline* for putting a genuinely learned policy in the
C7–C14 slot, plus two measured, documented findings about why naive behaviour
cloning from a privileged oracle fails. What does not exist is a policy that
flies. Nobody should read `c7t`/`c8t` numbers as an architecture result yet.

## All 15 architectures verified functioning

```bash
uavlab verify --seeds 1 2 3 4 5 6 7 8
```

New command, and deliberately distinct from `validate-config`: that one checks a
configuration is *legal*, this one checks the architecture actually *functions*.
"It ran without raising" has already produced one wrong claim in this project,
so each check targets a specific way an architecture can look fine and be broken:

| check | the failure it catches |
|---|---|
| `runs` | raises during the episode |
| `moves` | stationary vehicle still emits a full, meaningless metric row |
| `progress` | never gets closer to the goal — not pointed at the task at all |
| `authority:<level>` | decisions routed through the wrong path for the declared authority |
| component fires | **an architecture that is really its parent under another name** — verifier never consulted, monitor never assessed, reasoner never invoked, shield not on every command, chunks never executed |
| `deterministic` | same seed produces a different episode, invalidating paired comparison |

Checks are derived from the *config*, not a hardcoded table, so a new
architecture is covered the moment it exists.

**Result, `grid_nav`, 8 seeds — all 15 PASS every check:**

| arch | SR | dist | path | coll | | arch | SR | dist | path | coll |
|---|---|---|---|---|---|---|---|---|---|---|
| c0 | 0.88 | 3.8 | 57.2 | 0.12 | | c8 | 0.62 | 13.0 | 157.6 | 0.00 |
| c1 | 0.12 | 28.2 | 201.7 | 0.00 | | c9 | 0.75 | 7.4 | 101.8 | 0.00 |
| c2 | 0.62 | 12.6 | 224.0 | 0.00 | | c10 | 0.38 | 18.5 | 141.7 | 0.00 |
| c3 | 0.50 | 15.4 | 193.6 | 0.12 | | c11 | 0.38 | 17.8 | 105.3 | 0.00 |
| c4 | 0.75 | 8.0 | 174.4 | 0.12 | | c12 | 0.62 | 9.6 | 105.9 | 0.00 |
| c5 | 0.62 | 9.6 | 158.0 | 0.12 | | c13 | 0.62 | 9.6 | 105.9 | 0.00 |
| c6 | 0.50 | 15.4 | 193.6 | 0.12 | | c14 | 0.62 | 8.7 | 88.1 | 0.00 |
| c7 | 0.75 | 8.5 | 136.4 | 0.00 | | | | | | |

**Passing means functioning, not performing.** C1 at 0.12 and C10/C11 at 0.38
are working correctly and doing badly — which is a result to explain, not a bug
to fix. The success column is printed for information only.

### A bug the verifier found in itself, immediately

Run across *all* configs, it reported the five Gemma variants as FAILED with
`no frame behind 'stub://grid3d/rgb/1'`. That was the verifier's fault, not the
architectures': it defaulted to `grid_nav`, which does not render, and the
vision policies raised exactly the loud error they were built to raise.

Scoring that as a broken architecture would have been the same category error as
scoring a teleported drone as a recovery failure. Fixed: policies now declare
`requires_vision`, and the verifier routes them to the rendering variant of the
environment, or reports **SKIP** with a reason where none exists. A skip is
never counted as a failure.

Locked by `tests/integration/test_verify.py`, which mostly tests that the
verifier *fails* when it should — a stationary policy, a randomised policy, an
inert component. A verifier that passes everything is worse than none.

## STATUS: what works and what does not

### Works — verified by measurement

| area | evidence |
|---|---|
| Runtime kernel | 195 tests pass in ~60 s. Contracts, decision router, scheduler, staleness, event log, config grammar. |
| Determinism (scripted configs) | same seed reproduces metrics exactly; different seeds produce different scenes |
| Control ceiling | C0 meets the per-regime gate in all five regimes (was only ever checked on one) |
| `grid_nav` regime | ceiling 0.88, spread 0.38–0.75, no floor/ceiling pileup — architecture contrasts here are readable |
| Safety contrast | C7→C8 (same VLA, add shield) removes collisions, as designed |
| Renderer | real 224×224 frames; `unproject` inverts `project` to 1e-15 |
| Gemma 3 4B vision | 0.93 detection accuracy on a fixed frame set, **0 parse failures** across every run |
| Gemma latency | 4.05 s → ~1.7–2.3 s per call after fixing transport and switching endpoint |
| All 5 Gemma configs | `c2g`–`c6g` run end-to-end with no errors |

### Does not work

| problem | detail |
|---|---|
| **No Gemma config completes a mission** | 0 of 5. All time out at 17–39 m from a 2 m goal. |
| **Real-model runs are not reproducible** | c2g, seed 1, twice: **5.7 m then 17.1 m**. Measured latency varies run to run, which shifts the sim clock, which changes the trajectory. This breaks paired-by-seed comparison — the core method. |
| `object_search` regime | six architectures score exactly 0.00, including the whole single-action VLA family; ceiling marginal (0.62 SR, 0.25 collisions) |
| `failure_recovery` regime | ceiling fixed (0.75) but every non-oracle architecture sits at 0.00–0.12; C3–C6 collide 38 % |
| C1 (skill agent) | 0.00–0.12 everywhere, 88 % timeouts, unexplained |
| C10/C11 | *worse* than C8 despite being C8 plus a reasoner — needs an explanation, not a shrug |
| AerialVLA | blocked: LoRA weights with no `openvla-7b` base present |
| `ruff` / `mypy` | wired into CI, never installed or run locally |

### First Gemma run of all five configs (`grid_nav_vision`, seed 1)

| arch | outcome | dist | policy calls | mean latency | decision age | found rate |
|---|---|---|---|---|---|---|
| c2g | timeout | 17.1 m | 22 | 2.21 s | 3.50 s | 0.27 |
| c3g | timeout | 35.8 m | 21 | 2.33 s | 3.70 s | 0.43 |
| c4g | timeout | 38.8 m | 21 | 2.31 s | 3.80 s | 0.67 |
| c5g | timeout | 21.9 m | 24 | 1.98 s | 3.35 s | 0.25 |
| c6g | timeout | 34.6 m | 23 | 2.12 s | 3.15 s | 0.22 |

The arithmetic explains the timeouts without needing a bug: a 60 s episode at
~2.2 s per decision yields ~22 decisions; the target starts 35 m away; hops are
12 m; and the target is visible in roughly a third of frames. There is not
enough decision budget to converge. Whether that is a real finding about a 4B
model holding waypoint authority, or simply an under-provisioned episode
horizon, is **not yet distinguishable** — and saying which would require the
paired multi-seed screen that has not been run.

### Reproducibility — FIXED, but not the way I proposed

The plan was to quantise the charged latency. **Quantising does not work**, and
the only reason I know that is that I tested it instead of shipping it.

Same seed, `c2g`, two *separate processes* (which is how a sweep runs):

| charge mode | run 1 | run 2 | verdict |
|---|---|---|---|
| `measured` | 36.76 m | 7.16 m | diverged |
| `quantised` (250 ms) | 10.94 m | 18.53 m | **diverged** |
| `fixed` (2.2 s constant) | 9.749 m | 9.749 m | **reproducible, identical to 4 dp** |

Quantisation fails for a reason that is obvious afterwards: a call landing either
side of a bucket boundary — 1.86 s rounds down, 1.92 s rounds up — flips one
decision, and that flip cascades through every decision after it. Bucketing
reduces how *often* the coupling bites, never *whether* it does.

**Default is now `charge_mode: fixed`**, charging a constant measured once
(2.2 s median for Gemma 3 4B on this machine). Live latency is still measured
and reported as `inference_latency_s_policy`, alongside `inference_charged_s_policy`,
so the gap between realism and reproducibility is visible rather than hidden.
`measured` and `quantised` remain available for latency-realism studies where
pairing is not needed.

Locked by `tests/unit/test_latency_charging.py` (no network required), including
a test asserting the *shipped* Gemma profile is the reproducible one.

### Two wrong hypotheses on the way, both killed by measurement

Worth recording, because both were plausible and both were wrong.

1. **"The model is nondeterministic at temperature 0."** Tested directly: six
   calls, identical image and prompt — **six identical replies**, with and
   without an explicit seed. Gemma was never the problem.
2. **"Latency jitter is the only coupling."** Then `fixed` mode should have been
   reproducible immediately, and in the first test it was not. Tracing every
   decision showed the decision trace was *byte-identical* across runs — same sim
   times, same positions, same image digests, same replies — and tracing all
   1200 control ticks showed those were identical too. The apparent divergence
   was an artefact of running several modes back-to-back inside one process.
   Isolated per-process, `fixed` is exact.

The general lesson is the same one as the 2.08 s transport bug: the cheap
instinct (blame the model, reach for quantisation) was wrong both times, and a
targeted measurement was decisive both times.


Built from *A Modular Testbed for Searching Single-UAV Foundation-Model Autonomy
Architectures*. Milestones A and B of the spec are complete.

## What exists

- 86 Python files (~11k lines), 34 YAML configs, 173 tests passing in 31 s.
- All 15 architectures **C0–C14** as pure configuration — no code forks.
- 5 benchmark regimes, 7 staged experiments, CLI, sweeps, paired stats, Pareto.

## Where testing runs (the AirSim question)

Everything runs on the built-in deterministic environment `grid3d`. **AirSim is
not installed and is not used.** That is the spec's own adapter priority:

1. deterministic in-process env ← all current testing
2. PX4 SITL + Gazebo — stub, raises with an install hint
3. Project AirSim — stub, raises with an install hint

Reason: screening runs in the thousands of episodes. On `grid3d` a 90-second
mission executes in <1 s wall time with no GPU, so a 15-architecture × 8-seed
sweep finishes in about a minute. Forcing every sweep through a renderer would
make cheap screening pointlessly slow, and would bake one renderer's quirks into
every result. Details in `docs/SIMULATORS.md`.

A second *working* adapter (`scene_replay`) exists so the adapter boundary has
two implementations behind it rather than one assumption.

## Bugs found and fixed while building

These were all found by measurement, not by reasoning about the code.

| Bug | Symptom | Fix |
|---|---|---|
| Clock un-parked roles late | Episodes truncated at 0.1 s | Un-park at future-resolution time, not on coroutine resume |
| Scalar ray casting | 1.7 M distance calls/episode, 15 s per run | Vectorised the whole depth fan; 0.96 s per run |
| Memory stored any label | Drone flew confidently to a distractor and "succeeded" | `MemoryItem.label` + label-filtered recall |
| Planner/shield disagreed on "clear" | C0 wedged, 1723 safety interventions | One shared `min_clearance()`; planner reserves braking distance |
| 22.5° gaps between rays | Obstacles invisible between rays | 24 rays + windowed (not single-ray) clearance |
| Exploration circled the origin | Search never expanded | Spiral anchored to launch point, radius grows per leg |
| Exploration turned per *decision* | 10 Hz VLA swept 10× faster than 1 Hz skill agent | Heading advances on the clock — would have contaminated the authority comparison |
| `ConfigError(ValueError)` | Pydantic swallowed it; CLI never printed violations | Inherit from `Exception` |
| Pump exited with no roles registered | Silent hang | Raises immediately with the reason |

## Real models: what is possible on this machine

### Answer to "are you using an actual VLA / any vision?"

**No, to both.** Before this section's work:

- `mock_vla` / `chunk_vla` / `world_model_vla` were closed-form geometry — a unit
  vector toward a believed target, scaled by cruise speed. No network, no weights.
- `vlm_waypoint` was the same arithmetic at a different authority level.
- **Nothing rendered.** `observation.rgb` was a `SensorRef` holding a hash of the
  pose, with `shape=(224,224)` reported for an image that did not exist. That
  field is now `None`, and the uri scheme is `stub://`.
- The "detector" was the environment filtering its own landmark list by range,
  FOV and occlusion, then adding noise. `IdentityPerception` copied it through.
- `grep -rE "import (torch|cv2|transformers)" src/` returned nothing.

I also had a comment in `_action_velocity` calling the hand-written potential
field "learned reactive avoidance". Corrected — that is exactly the label that
makes a scripted baseline read as a model result.

### Renderer added

`src/uavlab/adapters/gym/render.py` — pinhole projection of the box world from
the vehicle camera, painter's algorithm, distance fog, 224×224. Crude by
intent (no texture, no lighting), but the image content is a true function of
pose and scene, so a vision model has something real to look at. It honours the
same occlusion and dropout rules as the sensor model via `visible_labels`, so a
scheduled sensor dropout is not still visible in the picture.

### Gemma 3 4B — works

Available through the local Ollama daemon as `gemma3:4b` (Q4_K_M, 3.3 GB).

Ollama's own metadata lists its capabilities as `["completion"]` with **no
vision** — that is wrong. Tested directly:

| probe | result |
|---|---|
| synthetic red rectangle, "what colour?" | `Red` — correct |
| rendered frame, target occluded by a box | `No` — correct, it *was* occluded |
| rendered frame, clear line of sight | `YES`, located `Right` — correct |

So the C2–C6 waypoint family can run on a real VLM. Worth noting the third row:
the model got the occluded case right, which means it is reading the image
rather than pattern-matching the prompt.

### AerialVLA — blocked, needs a decision

`XuPeng23__AerialVLA` is **LoRA adapter weights only** (462 MB
`adapter_model.safetensors` + `adapter_config.json`). Its config says:

```json
"base_model_name_or_path": "./openvla-7b",  "r": 64,  "lora_alpha": 128
```

Four things are missing to run it:

| need | state |
|---|---|
| OpenVLA-7B base weights | not on this machine; ~14 GB download |
| `peft` (to apply the LoRA) | not installed |
| `bitsandbytes` (4-bit, to fit the GPU) | not installed |
| VRAM | RTX 4060 Laptop; a 7B in bf16 will not fit, 4-bit ≈ 5 GB will |

Alternative already local: `euphoria-64__CoTinyVLA-Qwen3.5-0.8B` (1.7 GB raw
`student_state_dict.pt` plus an action-head config). Small enough to run
comfortably, but it ships as a bare state dict, so it needs its own loader
rather than `from_pretrained`.

Also present and vision-capable in Ollama: `qwen3-vl:2b`, `qwen3-vl:8b`,
`moondream`.

### Gemma 3 4B wired into C2–C6 — done, and it flies

Five new configurations, `c2g`–`c6g`, each inheriting its scripted counterpart
and swapping exactly two things: the policy and the inference backend.

New components:

| piece | what it does |
|---|---|
| `adapters/gym/render.py` | pinhole rasteriser; real 224×224 frames from the box world |
| `core/frame_store.py` | bounded uri→image store, so `SensorRef` resolves to pixels |
| `plugins/inference/ollama.py` | calls the local daemon, charges **measured** latency to the sim clock |
| `plugins/reasoning/vlm.py` | point-and-fly policy: Gemma returns a *pixel*, code does the geometry |
| `configs/environments/grid_nav_vision.yaml` | `grid_nav` with the camera on, identical otherwise |

**Design choice worth defending.** The model is never asked for coordinates. It
is shown the frame and asked which *pixel* to head for; `Camera.unproject` turns
that into a waypoint, and the round-trip against `project` is exact to 1e-15.
Asking a 4B model for "x=12.4, y=-8.1" would test its ability to invent
plausible numbers. Asking it to point tests visual grounding, which is what C2
actually claims to be about — and it keeps the failure modes separable: a wrong
pixel is perception, a wrong waypoint from a right pixel is a geometry bug.

**Live result, `c2g` on `grid_nav_vision`, seed 1:**

| | |
|---|---|
| parse failures | **0** — Gemma returned clean JSON on every call |
| target found | 7 of 11 frames (0.64) |
| mean policy latency | **4.83 s** per decision |
| decisions in a 60 s episode | 11 |
| median decision age | **7.45 s** |
| distance to goal | 35.7 m → **22.6 m** (it navigates) |
| outcome | timeout — real, not a bug |

The headline is the decision age. Gemma 3 4B **works** as a waypoint policy and
is **far too slow to hold waypoint authority in real time on this hardware**: the
vehicle acts on where the world was 7.5 seconds ago. The staleness bound had to
be raised from 1.5 s to 8 s for the configuration to run at all, and that gap is
a finding rather than a tuning knob — it is exactly the "authority × latency
budget" interaction the study is built to expose.

**Two bugs found by running it:**

1. `IdentityPerception` was calling the inference backend to "charge detector
   latency". Harmless against a simulated backend where latency is bookkeeping;
   against Ollama it fired an **empty prompt at Gemma, 5.1 s at a time**, burning
   half the episode budget on replies nobody read. Default is now off.
2. `import uavlab` began pulling in `http.client` via the Ollama backend. Real
   model adapters now load on first use through
   `registry.OPTIONAL_PLUGINS`, the same treatment PX4 and AirSim get, so the
   core runtime still imports nothing that touches a network.

**Tests:** 195 passing. `tests/integration/test_vlm_policy.py` covers the policy
against a stub backend — no network, no weights — including that pointing left
and right yields waypoints on opposite sides, that prose-wrapped JSON still
parses, and that a **missing frame raises** rather than silently degrading to a
blind policy that would still emit plausible waypoints.

Run it:

```bash
uavlab run --arch c2g --env grid_nav_vision --seed 1
```

### "Can you quantize Gemma?" — it already is, and that was not the problem

`gemma3:4b` as installed is **Q4_K_M** GGUF, 4.3 B params, 2.88 GB, **100 % resident
on the GPU**. There is no unquantized version in play.

So I measured where the 4.05 s per call actually went, by subtracting the
server's own reported timings from measured wall time:

| component | time | share |
|---|---|---|
| unaccounted overhead | **2.08 s** | 51 % |
| reported `load_duration` | 1.42 s | 35 % |
| prefill (prompt + image) | 0.18 s | 4 % |
| decode | 0.37 s | 9 % |

Only about **0.55 s is real GPU compute**. A perfect 2× quantisation win would
have saved 0.28 s out of 4.05 s — under 7 %.

**What the 2.08 s was.** I ran the same probe against `gemma3:4b`, `moondream`
and `qwen3-vl:2b`. The overhead was 2.08 s for *all three*, to two decimals.
A constant that does not vary with model size is not model compute — it is
transport. My backend was opening a **fresh TCP connection per call**.

Reusing one keep-alive connection:

| | new connection each call | persistent connection |
|---|---|---|
| wall per call | 4.05 s | **1.80 s** |
| unaccounted overhead | 2.08 s | **0.02 s** |

**Effect on the actual mission** (`c2g`, `grid_nav_vision`, seed 1):

| | before | after |
|---|---|---|
| mean policy latency | 4.83 s | **2.56 s** |
| decisions in a 60 s episode | 11 | **19** |
| median decision age | 7.45 s | **4.00 s** |
| final distance to goal | 22.6 m | **5.7 m** |

The drone now gets within 5.7 m of a 2 m goal radius instead of stalling at
22.6 m. Same model, same quantisation, same hardware — the entire gain was a
transport bug in code I had written an hour earlier.

**The lesson worth keeping.** My first instinct when told "4.83 s per decision"
would have been to reach for a smaller or more aggressively quantised model. That
would have cost hours and bought under 7 %. Splitting measured wall time against
the server's self-reported load/prefill/decode is what made the real cause
visible, and running three different models is what proved it was transport
rather than compute.

### Chasing the 1.4 s "load"

Characterised, partially reduced, and **not fully eliminated**. What it is:

**It is real time, not a reporting artifact.** Streaming shows time-to-first-token
of 1.49 s, matching the reported `load_duration`. The wall clock really does pass.

**It is not a model load.** Forcing a genuine reload by changing `num_ctx` costs
**5.5–7.6 s**. The recurring 1.4 s is an order of magnitude cheaper, so it is a
different thing wearing the same label.

Ruled out, each by measurement:

| hypothesis | test | result |
|---|---|---|
| the vision tower reloads per image | text-only vs image calls | **1.45 s either way** — not image-driven |
| VRAM pressure evicting the model | unloaded the other two models (6.09 → 2.88 GB held) | **1.39–1.44 s unchanged** |
| model not staying resident | `keep_alive: 30m` + `/api/ps` | resident, future `expires_at`, cost persists |
| prompt-cache invalidation | identical prompt repeated | prefill drops 0.74 → 0.05 s, load **unchanged** |
| options forcing re-init | omitted the options block entirely | unchanged |

**What it correlates with is model size:**

| model | reported load |
|---|---|
| moondream (1.8 B) | 0.19 s |
| qwen3-vl:2b (2 B) | 0.62 s |
| gemma3:4b (4.3 B) | 1.42 s |

So it is per-request setup inside Ollama 0.32.14 that scales with the model,
and it is not reachable from the client.

**The one lever that worked: `/api/chat` instead of `/api/generate`.**

Because the chat endpoint applies Gemma's chat template, this could easily have
bought speed at the cost of accuracy — and the first episode after switching
*looked* like exactly that, with found-rate falling 0.474 → 0.238. That was a
confound: a faster policy flies a different trajectory and therefore sees
different, harder frames.

Controlled A/B on **identical frames with ground-truth visibility**
(`scratchpad/ab_endpoint.py`, 14 frames):

| endpoint | accuracy | TP / TN / FP / FN | unparsed | mean wall |
|---|---|---|---|---|
| `/api/generate` | 0.93 | 13 / 0 / 1 / 0 | 0 | 2.52 s |
| `/api/chat` | 0.93 | 13 / 0 / 1 / 0 | 0 | **1.70 s** |

Byte-identical quality, 33 % faster. Switched, and `load_duration` is now
reported separately as `inference_server_setup_s_*` so it can never be read as
model compute.

**Where the per-call latency ended up:**

| stage | before | after |
|---|---|---|
| transport overhead | 2.08 s | 0.02 s |
| server setup ("load") | 1.42 s | ~1.24 s |
| prefill + decode | 0.55 s | 0.46 s |
| **total** | **4.05 s** | **~1.7 s** |

**Honest limits of this result.** The residual ~1.2 s is Ollama-internal; the
remaining levers are a smaller model or a different serving stack, not anything
in this repository. And the single-seed episode outcomes quoted through this
section (5.7 m, 37.8 m) are **noise** — one seed, and timing changes shift the
whole trajectory. The paired `c2` vs `c2g` screen over multiple seeds is what
would actually measure this, and it has not been run.

The A/B benchmark is also weak on negatives: 13 of 14 frames had the target
genuinely visible, so it measures detection but barely tests false positives.
Worth rebuilding with a balanced set before any claim about VLM precision.

### Can OpenVLA run at 1-bit?

No — and it does not need to.

**Why 1-bit is not available.** `bitsandbytes` implements 8-bit and 4-bit only;
there is no 1-bit path in it. Genuine 1-bit comes in two flavours and neither
applies:

- *BitNet b1.58* (ternary weights) is **pretrained** ternary. You cannot convert
  an existing fp16 checkpoint into one — the ternary constraint has to be present
  during training. OpenVLA is not a BitNet model.
- *Post-training binarisation* (BiLLM, OneBit, PB-LLM) is research-grade, needs
  calibration or distillation, and has no working integration for a
  Prismatic-style VLM carrying two vision encoders (DINOv2 + SigLIP).

**Why it would be a bad idea even if it were available.** OpenVLA does not
regress actions directly; it **discretises each action dimension into 256 bins
and re-purposes the least-used tokens of the Llama vocabulary** to represent
them. Binarising the embedding and LM-head weights scrambles precisely that
token→action-bin mapping. The failure mode is not a crash — it is confident,
well-formed, wrong actions. In this project that is the worst possible outcome,
because it is indistinguishable from an architecture result.

**4-bit already fits.** Measured on this machine: 8.00 GB VRAM, **6.94 GB free**.

| | estimate |
|---|---|
| OpenVLA-7B params (Llama-2 7B + DINOv2 + SigLIP) | ~7.5 B |
| NF4 weights | ~3.8 GB |
| vision encoders kept in fp16 | ~0.7 GB |
| KV cache + activations, one image, short prompt | ~1.0–1.5 GB |
| **total** | **~5.5–6 GB — fits in 6.94 GB** |

4-bit loading is the documented path for OpenVLA, so this is well-trodden rather
than experimental.

**The actual blockers are mundane:**

| blocker | detail |
|---|---|
| base weights | ~14 GB download, not present |
| disk | **34 GB free on C:, 97% full** — enough, but not comfortable |
| `peft` | not installed (needed to apply the LoRA) |
| `bitsandbytes` | not installed (needed for NF4) |
| `transformers` 4.44.2 | OpenVLA loads with `trust_remote_code=True`; version is plausible but untested here |

**Throughput consequence, worth deciding on before committing.** OpenVLA-7B at
4-bit on a 4060 Laptop will realistically give low single-digit Hz for
single-image action prediction. The C7–C14 configs currently ask for a 10 Hz
decision loop. Two implications:

1. The real model cannot hit the configured rate, which is itself a legitimate
   finding — but it must be *measured* and written into the model profile, not
   assumed.
2. Episodes stop being free. The current 360-episode audit runs in ~4 minutes on
   simulated latency; against a real 7B it becomes hours. Real-model runs should
   be a small promoted subset, not the screening sweep — which is exactly the
   staging the spec already prescribes.

## Audit: are the architectures actually working?

**No — only one of three regimes produces usable numbers.** My earlier summary
was wrong, in two specific ways.

### Correction 1: "C0 = 1.00" was one regime and a lucky seed set

I measured the control ceiling on `grid_nav` with seeds `[3,5,7,11,13,17,19,23]`
and reported 1.00. On seeds `1..8` it is **0.88**, and I had never measured it in
the other regimes at all. The spec's gate is per-environment; I applied it to the
easy one and generalised.

Now enforced properly: `test_the_oracle_is_competent_in_every_regime` runs the
gate across all five regimes.

### Correction 2: `failure_recovery` was rigged, and I did not notice

`block_path` placed its obstacle at the **midpoint between the vehicle and the
goal**. By the time it fired at t=8 s the vehicle was usually past that point, so
the box materialised on top of a drone at cruise speed:

| seed | distance from drone to box at spawn | speed |
|---|---|---|
| 3 | 0.92 m | 4.6 m/s |
| 4 | 0.46 m | 4.3 m/s |
| 5 | **−2.34 m** (inside the box) | 4.6 m/s |
| 8 | **−1.23 m** (inside the box) | 4.2 m/s |

Five of eight seeds were unavoidable or literal teleport-into-wall. The regime
was measuring vehicle teleportation, not recovery.

It hid because it hit every architecture equally, so the table still looked like
a plausible spread. The oracle is what exposed it: a configuration with perfect
semantics has no business colliding 62% of the time.

**Fixed.** Blockages now stage along the direction of travel at
`max(lead_m, stopping_distance + box_depth)`, are never placed beyond the goal,
and are skipped and counted if no fair placement exists. C0 on
`failure_recovery`: SR 0.12 → **0.75**, collisions 0.62 → **0.12**. Regression
tests in `tests/integration/test_injection_fairness.py`.

### Post-fix state, 8 seeds per cell

| arch | grid_nav | object_search | failure_recovery |
|---|---|---|---|
| C0 (ceiling) | 0.88 | 0.62 *(0.25 coll)* | 0.75 |
| C1 | 0.12 | **0.00** | 0.00 |
| C2 | 0.62 | 0.62 | 0.12 |
| C3 | 0.50 | 0.50 | 0.00 *(0.38 coll)* |
| C4 | 0.75 | 0.50 | 0.12 *(0.38 coll)* |
| C5 | 0.62 | 0.38 | 0.12 *(0.38 coll)* |
| C6 | 0.50 | 0.38 | 0.00 *(0.38 coll)* |
| C7 | 0.75 | **0.00** | 0.12 |
| C8 | 0.62 | **0.00** | 0.12 |
| C9 | 0.75 | **0.00** | 0.12 |
| C10 | 0.38 | **0.00** | 0.00 |
| C11 | 0.38 | **0.00** | 0.00 |
| C12 | 0.62 | 0.12 | 0.12 |
| C13 | 0.62 | 0.12 | 0.12 |
| C14 | 0.62 | 0.12 | 0.12 |

Verdict per regime:

- **`grid_nav` — usable.** Ceiling 0.88, spread 0.38–0.75, no floor/ceiling
  pileup. Architecture contrasts here are worth reading.
- **`object_search` — not usable.** Six architectures score exactly 0.00,
  including the entire single-action VLA family. A regime where a third of the
  set cannot score discriminates nothing. The ceiling is also marginal (0.62 SR
  with 25% collisions), so the substrate is shaky there too.
- **`failure_recovery` — not usable yet.** The ceiling is fixed, but every
  non-oracle architecture sits at 0.00–0.12, and the waypoint family (C3–C6)
  collides 38% of the time. Both need diagnosis before the regime means anything.

### What the audit *did* confirm

Every architecture's distinguishing component fires in every regime — no
component is configured-but-inert. Verifiers act, monitors emit STOP/LOST,
shields intervene, reasoners run, chunks execute, triggers admit. So the wiring
is real; the calibration is not.

### Still unexplained

- **C1 (skill agent) 0.00–0.12 everywhere**, 88% timeouts on grid_nav.
- **Whole VLA family 0.00 on `object_search`**, mostly timeouts.
- **C3–C6 38% collisions on `failure_recovery`** while C7–C9 collide 0%.
- **C10/C11 worst on grid_nav (0.38)** despite being C8 plus a reasoner —
  adding the hierarchy makes it worse, which needs an explanation rather than a
  shrug.

## Known gaps

- Real LLM/VLM/VLA adapters (Milestone D) — each replaces one plugin, nothing else.
- PX4/Gazebo and Project AirSim adapters are stubs (Milestone C).
- `ruff`/`mypy` are wired into CI but not installed locally, so they have not
  been run here.

## Teacher swapped to C2, and what it did and did not fix

`uavlab collect` no longer defaults to the oracle. The seed split is now
declared in `training/splits.py` and enforced: `EVAL_SEEDS = 1..40` is held out
and `collect()` raises if a requested range touches it. (The previous run was in
fact clean — trained on seeds 1000–1199, scored on 1–40 — but by default rather
than by rule.)

### Why C2 and not C0

C0 is handed the true goal position and flies confidently toward a target that
is off-camera 61% of the time; its label is not a function of the student's
observation, so no network can recover it. C2 decides from live detections and
carries no memory, so its action *is* a function of the current view.

Teacher scores on `grid_nav_vision`, 40 held-out seeds:

| | success | collisions | path |
|---|---|---|---|
| c0 (privileged ceiling) | 0.85 | 0.10 | 43 m |
| **c2** | **0.68** | **0.00** | 167 m |
| c5 | 0.65 | 0.05 | 123 m |
| c6 | 0.62 | 0.05 | 144 m |

C5/C6 were rejected for a second reason beyond the score: their memory is
hidden state the student does not have, which reintroduces the same privileged
-information problem in miniature.

### The result

53,543 samples from 160 of 250 flights (2.0 GB). Training improved on every
open-loop number — bin accuracy 0.230 → 0.328, velocity error 1.875 → 1.500 m/s.

**Closed-loop success is still 0/40 for both c7t and c8t.** The policy flies
78 m and ends 74 m from the goal.

### The measured reason: it cannot turn

Per-dimension mean absolute error on held-out frames, against the best possible
*constant* predictor for that dimension:

| dim | policy | best constant | |
|---|---|---|---|
| vx | 0.975 | 2.480 | learned |
| vy | 0.949 | 2.524 | learned |
| vz | 0.053 | 0.053 | tie |
| **yaw_rate** | **0.319** | **0.294** | **worse than a constant** |

So the policy reads the image for translation and has learned nothing at all
about yaw. That is fatal in closed loop specifically because the camera is
body-fixed: a policy that never turns toward the target loses it from frame,
and once lost it never comes back. 76% of the training frames already have no
target in view; a non-turning policy drives that to ~100% within seconds, which
is exactly the 74 m drift observed.

Yaw is the one channel C2 cannot teach from a single frame. Its yaw command
depends on the waypoint it committed to earlier and on its exploration clock —
hidden state, the same failure as C0, isolated to one dimension.

An earlier "imitability" measurement (heading concentration R=0.983 for C2)
looked reassuring and was near-worthless: it measured the heading of the
velocity vector, which is near-zero almost always because C2 steers by yawing
and then flying forward. Concentration of a near-constant says nothing. The
per-dimension comparison against a constant baseline is the check that has
teeth, and it is the one to run first next time.

Nobody should read c7t/c8t numbers as an architecture result yet.

## Course-aligned yaw: fixed the drift, exposed a deadlock

`learned_visuomotor` gained `yaw_mode` (default `course_aligned`): the nose is
pointed along the commanded velocity by a rule, and the network's yaw output is
ignored. `learned` is still selectable so the comparison stays runnable.

Effect on 40 held-out seeds — final distance from goal 74 m -> 28 m, path 78 m
-> 25 m. So the vehicle now heads roughly the right way. Success is still 0.00.

Also added `terminate_consecutive` (default 3), requiring the stop head to agree
across consecutive decisions. **It changed nothing — every number identical.**
The false stops are therefore systematic, not frame-level noise: the policy
enters a region where it is persistently confident it has arrived. Recorded here
because the fix that does nothing is worth knowing about.

### What the trace shows

Tracing commanded velocity through one episode (`c8t`, seed 1) is unambiguous:

```
   0.0 ( 0.0, 0.0)  cmd (4.96, 0.08)  4.96 m/s
   2.2 ( 5.9, 0.0)  cmd (0.08,-0.08)  0.12 m/s
  ...  22 seconds of the identical command ...
  25.3 (13.9,-1.8)  cmd (1.38, 0.08)  1.38 m/s
  28.6 (16.0,-1.7)  cmd (1.38, 0.08)  1.38 m/s
  38.5 (16.0,-1.7)  cmd (1.38, 0.08)  1.38 m/s   <- position frozen 15 s
```

The command is bit-identical for hundreds of consecutive decisions. The vehicle
drives into an obstacle, the shield holds it there, the view stops changing, and
because the view stops changing the policy re-emits the same command forever. A
genuine fixed point: stationary -> same image -> same command -> stationary.
Without the shield (c7t) the same behaviour is a collision, 45% of episodes.

This is compounding error in behaviour cloning, in its most literal form. The
teacher never sits pressed against a wall, so no training frame resembles this
state, so the policy's output there is arbitrary — and arbitrary happens to be
constant.

### Why obstacle avoidance did not transfer

In C2 the avoidance is done by the classical local planner downstream of the
policy. The collector records the final commanded velocity, so avoidance *is*
present in the labels — but only as a correlation the student must rediscover
from pixels, and it has not.

### Next: DAgger

The standard remedy, and it targets this failure exactly. Run the student, query
C2 for what it would have commanded at the states the student actually visited,
add those pairs, retrain. The stalled-against-a-wall states get labelled "back
off and go around" instead of being absent from the dataset. All the parts exist:
C2 is queryable at any state, and the collector already patches `step`.

Nobody should read c7t/c8t numbers as an architecture result yet.

## DAgger

`uavlab dagger` — new command, `training/dagger.py`. Rolls the trained student
out, asks C2 what it would have commanded at each state the student reached, and
appends those pairs to the base dataset.

The teacher is a full architecture (policy -> planner -> controller) with a
waypoint that is stateful across ticks, not a function from image to velocity.
So rather than reconstruct a teacher-evaluator, an ordinary C2 orchestrator runs
and the executed command is substituted inside `step`: C2 observes, reasons and
produces its command as usual — that is the label — and the vehicle then moves
according to the student. C2's memory and exploration clock therefore evolve over
student-visited states, which is what DAgger requires.

`beta` is the probability of executing the teacher's command on a tick.

### Harness check before trusting it

8 seeds at three settings, confirming the substitution actually takes effect
rather than silently doing nothing:

| beta | who drives | successes |
|---|---|---|
| 1.0 | teacher | 6/8 |
| 0.5 | mixture | 6/8 |
| 0.0 | student | 0/8 |

beta=1.0 reproduces C2's own 0.68 and beta=0.0 reproduces c7t's 0.00, so the
knob is real and connected at both ends. Worth stating because a substitution
that quietly failed would have produced a plausible dataset and a wasted
retraining run.

All ticks are kept, successes and failures alike — the states worth adding are
precisely the ones where the student went wrong, and the success filter that is
correct for plain cloning would discard exactly them.

`_append` concatenates on disk through a memmap: the base frame array is 2 GB
and `np.concatenate` would transiently need three copies.

## DAgger did not help, and the reason corrects an earlier claim

150 rollouts at beta=0.25 added 52,684 teacher-labelled samples from
student-visited states; total 106,227 (4.0 GB). Retrained.

Held-out seeds 1-40, success still 0.00 / 0.03. Final distance from goal got
*worse*: 28 m -> 50 m. Open-loop also degraded (bin accuracy 0.328 -> 0.173),
which is expected on a harder aggregated set and is not the interesting part.

To separate navigation from stopping, both checkpoints were rerun with the stop
head disabled, so `reached_goal` measures navigation alone:

| checkpoint | reached_goal | final distance |
|---|---|---|
| bc_c2 | 0.03 | 28 m |
| bc_dagger | 0.05 | 60 m |

Unchanged. DAgger bought nothing.

### The claim that was wrong

I said C2 was the right teacher because "it has no memory, so its action is a
pure function of the current frame". That is false. C2 has no memory *plugin*,
but the architecture is stateful in two ways that matter more:

* it decides at 2 Hz and controls at 20 Hz, so 9 of every 10 recorded labels
  come from the planner tracking a waypoint chosen up to half a second earlier;
* `explore_target` advances on a sim-time clock, and 76% of frames are
  exploration.

So the label was never a function of the student's observation. C2 is less
privileged than C0, not unprivileged.

That also explains why DAgger could not help. DAgger corrects the *state
distribution* — it does not make a label deterministic given the observation.
The failure here was never distribution shift alone; two frames that look
identical to the student carry different labels because C2 was flying toward
different committed waypoints. No amount of relabelling fixes that.

### What is left

Give the student memory — a frame stack or recurrent state — so it can carry the
committed direction the teacher is carrying. This was one of the two options
identified before the teacher swap, and eliminating the other one is what the
last three runs bought.

Nobody should read c7t/c8t numbers as an architecture result yet.

## Frame stack: fixed stopping, did not fix navigation

`PolicyConfig.frame_offsets = (0, 5, 15, 40)` — a *dilated* history spanning 0,
0.5, 1.5 and 4.0 seconds, not four consecutive frames. Four consecutive stored
samples span 0.3 s, which is long enough to see motion and far too short to
remember where a target was last seen.

This required something the datasets did not have. Samples from different
flights sit back to back in `frames.npy`, so an unclamped history window reads
the end of the previous flight as the start of this one. `collect()` and
`dagger.aggregate()` now write `episodes.npy`, `train()` clamps every offset to
the first sample of its own episode, and it raises rather than guessing if the
index is absent. `FrameHistory` in `policy_net.py` is the inference-time
counterpart, shared by the plugin and the DAgger rollout driver so the two
cannot drift.

Trained on the same 53,543 C2 samples as the single-frame policy:

| | single frame | frame stack |
|---|---|---|
| bin accuracy | 0.328 | 0.345 |
| velocity error | 1.500 | 1.334 m/s |
| **stop precision** | **0.44** | **0.95** |

### What it fixed

Stopping, decisively. `agent_stopped` terminations on 40 held-out seeds went
from 24/40 to 1/40. Whether the vehicle is arriving is a question about motion
over time, and a single frame genuinely cannot answer it — this is the one place
where history was obviously the right tool and it worked.

### What it did not fix

Navigation. Success 0.03. c8t now times out 39/40 at 31 m from a goal that
started 35 m away; c7t collides in 57% of episodes.

### Where that leaves the learned policy

Three interventions, each targeting a measured failure, each verified:

| | reached_goal |
|---|---|
| C0 teacher, single frame | 0.00 |
| C2 teacher, single frame | 0.03 |
| + DAgger | 0.05 |
| + frame stack | 0.03 |

Navigation has not moved. Each intervention fixed the specific defect it was
aimed at — the velocity shortcut, the non-turning yaw channel, the false stops —
and none of them was the binding constraint on reaching the goal.

C7-C14 already run with the scripted `mock_vla` in the direct-action slot, so
none of the architecture comparisons are blocked on this. The honest status is
that `c7t`/`c8t` are a working *pipeline* (collect -> train -> DAgger -> fly, all
reproducible) carrying a policy that does not yet navigate, and their numbers
must not be read as an architecture result.

## Verification of all architectures

`uavlab verify` over the full set (22 configs: C0-C14 plus the `g` and `t`
variants), three seeds each, on `grid_nav` — vision architectures routed to
`grid_nav_vision`.

**21 of 22 passed. The one failure was c2g**, on the determinism check:
final distance 28.462555 vs 28.461193 for the same seed. 1.4 mm, but the check
is right to fail it — paired-by-seed comparison is the whole method.

Chased rather than assumed. Capturing every Gemma response across two runs in
one process: 23 calls each, byte-identical. Across three separate processes:
identical to nine decimal places. So it is intermittent, and it is not the
harness — the residual variation is inside the server's GPU kernels, where
batching and memory pressure change reduction order. No client-side option
reaches it.

`sampling_seed` is now pinned and sent with every call. That is the one lever
that is ours, and it is honest about not being sufficient — the docstring says
so rather than implying the problem is solved. c2g and c3g both verify clean
after it, but "clean on a re-run" is not proof for an intermittent fault.

Why c2g specifically and not c3g-c6g: C2 maps the emitted pixel straight to a
waypoint, so nothing downstream absorbs a one-pixel difference. The verifier and
monitor in C3-C6 do absorb it.

### Reading the table

Success rates in the verify output are reported for information only — the
checks test that an architecture *functions*, not that it performs. Two things
in that table are worth following up separately: c1 still scores 0.00, and
c3g/c4g/c5g produce identical distance, path and collision figures, which is
suspicious for three architectures that differ.

## Why C1 scores near zero

Traced rather than guessed. Over a full episode C1's belief source is `none` on
every one of 37 decisions — it never once detects the target and explores blind
until the horizon. But so does C2 for long stretches, and C2 scores 0.70 on the
same seeds, so "never sees the target" is not the answer by itself.

The answer is an interaction between two things, neither of which does the
damage alone. On 20 seeds of `grid_nav_vision`:

| | success |
|---|---|
| C1 as shipped (1 Hz, scan every 3rd decision) | 0.15 |
| without the scan skill | 0.15 |
| at 2 Hz, scan unchanged | 0.20 |
| without the scan, at 2 Hz | 0.60 |

A `scan` is a whole decision spent rotating in place. At 1 Hz, one scan in every
three means a third of the mission is not spent flying anywhere — and at 1 Hz
there are only ~60 decisions in an episode to begin with. Doubling the rate
without removing the scan just buys more scans; removing the scan without
raising the rate leaves too few decisions to search with. Only both together
recover the performance.

Cost is set by scan *frequency*, not duration, which is what confirms the
reading — decisions are the scarce resource, not seconds:

| at 1 Hz | success |
|---|---|
| scan 1.0 s every 3 (shipped) | 0.15 |
| scan 0.4 s every 3 | 0.15 |
| scan 1.0 s every 6 | 0.35 |
| scan 0.4 s every 6 | 0.20 |

### What is a result and what is a bug

The 1 Hz rate is deliberate and is part of what C1 *is* — a skill agent is
expensive per call, and raising the rate would quietly turn C1 into a different
architecture. That a low call rate handicaps a task requiring search is a
genuine finding, and precisely the falsifying result `c1_llm_skills.yaml`
anticipated.

The scan frequency is not. It was chosen without reference to the decision rate,
and it currently dominates the architecture signal: C1 reads as 0.15 when the
defensible number for its own design is 0.35.

`scan_every` and `scan_duration_s` are now parameters so this is measurable
rather than arguable. Defaults are unchanged pending a decision on whether to
set `scan_every: 6` for C1.

`scan_every: 6` is now C1's default. Verified: PASS, and 0.35 success over 40
held-out seeds (was 0.15), with zero collisions. 1 Hz is untouched. 224 tests
pass.

## Why C3G, C4G and C5G report identical numbers

Because they fly identical trajectories. On seed 1 all three end at exactly
34.1546 m with a 114.9097 m path. The scripted C3/C4/C5 differ from each other
normally (0.33 / 0.67 / 0.33), so this is specific to the Gemma variants.

The components are not missing. C4G and C5G each run 15 monitor assessments, 13
of which return LOST, and each carries a different memory plugin. The event logs
show them firing. What differs between C3G and C4G is *only* cost:
`inference_calls_total` 22 vs 37, `tokens_per_minute` 557 vs 1517,
`monitor_assessments` 0 vs 15. Not one metric of motion differs.

### The cause

`VLMPointWaypoint.decide` never calls `self.believe(ctx)`. It asks Gemma; if
Gemma reports the target is not visible it goes straight to `explore_target`.
The belief chain — live detection, then the reasoner's directive, then remembered
evidence — is where memory and supervision enter a policy's behaviour, and this
policy does not consult it. So the memory plugin and the monitor's LOST calls
have nowhere to land.

C2's `vlm_waypoint` does consult it, which is why the scripted C3/C4/C5 separate
and the Gemma ones do not.

### The verification gate missed this

`uavlab verify` checks that each architecture's distinguishing component *fires*,
and by that standard C4G and C5G pass honestly: the monitor runs, the memory
updates. Firing is not the same as influencing. A component that consumes real
compute and changes no behaviour is exactly the failure the gate exists to catch,
and the check as written cannot see it.

The check needs to compare against the same architecture with the component
removed and require the trajectory to differ. That is a stronger and more
expensive test, and it is the right one.

### Consequence for the results

Any C3G/C4G/C5G comparison currently measures token cost and nothing else. The
memory and supervision contrasts for the real model are not yet testable.

## C2G's nondeterminism was a frame leak, not GPU noise

I called it intermittent GPU nondeterminism. It was not: the full sweep
reproduced the *same two values* — 28.462555063 vs 28.461193430 — so it was
deterministic and structural.

Replicating verify's exact sequence for c2g (seeds 1, 2, 3, then seed 1 twice)
showed the pattern:

```
results seed 1        d=28.462555063
results seed 2        d=36.869823639
results seed 3        d=31.826341575
determinism run A     d=28.462555063
determinism run B     d=28.461193430   <- diverges
```

Frame URIs were `frame://{id(env)}/rgb/{seq}`. `id()` is an object address that
CPython recycles as soon as the previous environment is collected, and the frame
store is process-global and was never cleared by anything. So a new episode
could resolve a reference to the *previous* episode's pixels — and the
`max(self._seq - 1, 0)` lookups at the very start of an episode are exactly
where that lands.

Fixed with a monotonic namespace per episode, which cannot be recycled, plus
`global_store().clear()` on reset. All three seed-1 runs now agree, on
28.461193430 — the value fresh processes always produced. 28.462555063 was the
contaminated one.

`test_frames_never_leak_between_episodes` asserts on the URIs rather than on a
trajectory, so it names the cause instead of reporting a number that happens to
differ. Confirmed to fail against the pre-fix code.

Why only c2g showed it: C2 maps the emitted pixel straight to a waypoint with
nothing downstream to absorb a one-frame difference. The verifier and monitor in
C3–C6 absorb it, which is why they verified clean while carrying the same bug.

**All 22 configurations now pass every structural check.**

## The Gemma believe() gap, closed

### Proving it was the cause

Reading the code showed `VLMPointWaypoint.decide` never calls `believe()`. That
is not proof, so it was tested by removal: strip the memory plugin and see
whether the trajectory moves.

| | memory changes the trajectory |
|---|---|
| c5 (scripted) | 3 of 10 seeds |
| c5g (Gemma), before | **0 of 8 seeds** |
| c5g (Gemma), after | **3 of 3 seeds** |

A first attempt at this test used one seed and showed no change for the
*scripted* c5 either — on seed 1 the target stays visible and memory is never
consulted. A component that is inert on one episode is not an inert component.

### The trap that shaped the fix

Memory stores are fed from `perception.detections` — the simulated detector.
Wiring `believe()` in as-is would have let the Gemma policy recover the
detector's sightings through memory, and c5g's "memory result" would really be a
detector result, in a configuration whose entire premise is that a real model is
the perceiver.

So the policy now remembers only what *it* concluded. `_decision_memory` records
the policy's own committed waypoint under `kind="decision"`, and `recall_target`
takes a `kinds` filter so the Gemma policy can ask for that and nothing else.

### Two bugs found on the way, both by measurement

**Memory refreshed itself.** Steering on a recalled target produced another
labelled waypoint decision, which was written back to memory with a fresh
timestamp. The policy latched: it flew 9–17 m in a 60 s episode against 113–115 m
with no memory, orbiting a position the model could no longer confirm. Adding a
`memory_trust_s` age limit changed *nothing at all* — the timestamp was never old.
The fix is that a decision marked `from_memory` is never written back, and only
then does the age limit do anything.

**The recall branch was broken at runtime while 225 tests passed.** `provenance`
is `dict[str, str]` and the marker was a bool, so every c5g episode ended in
`runtime_error` — and no test noticed, because none exercised recall. Three tests
now do, including one asserting the detector is *not* reachable through memory.

### Where it leaves c5g

| seed | with memory | without |
|---|---|---|
| 1 | 30.6 m out, 79 m flown | 34.1 m out, 115 m flown |
| 2 | 36.0 m out, 91 m flown | 22.7 m out, 113 m flown |
| 3 | 24.0 m out, 13 m flown | 24.7 m out, 55 m flown |

Mixed — better on seed 1, worse on seed 2. That is the honest outcome and it is
the point: the objective was to make the C4→C5 memory contrast *measurable* for
the real model, not to make c5g win. It is now measurable. 228 tests pass.

## Videos: judging a run by eye

`uavlab video [ARCH...] --seed N` renders one episode per architecture to mp4
(`analysis/replay_video.py`). Two panels: a plan view with obstacles, target,
distractors and the path so far, and the camera frame the policy actually saw.

Both panels are needed. The plan view shows whether the vehicle went anywhere
sensible; the camera panel separates "flew past a target that was never in
frame" (a perception result) from "flew past a target filling the frame" (a
policy result), which the plan view alone cannot distinguish.

Two deliberate choices. The scale is fixed for the whole episode rather than
fitted per frame — a rescaling view makes a straight line look curved and a
stall look like progress. And the verdict is withheld until the last few frames,
so a run can be judged on what it did rather than read in the light of its label.

Not importable from anything that scores a run. This module is for looking at.

Seed 3, all 22 configurations:

| | outcome |
|---|---|
| C0, C7–C14 | success, stopped 0.9–1.6 m from the target |
| C1 | timeout, 30 m out after a 267 m path |
| C2–C6 | timeout, 33 m out after ~366 m |
| C2G–C6G | fail; C3G collides, C4G/C5G stall at 13 m of path |
| C7T | out of bounds, 68 m from goal |
| C8T | timeout, 52 m out |

Worth noting from the table: C2–C6 are identical on this seed, as are C4G/C5G.
That is not the inert-component bug — those separate on other seeds — but it is a
reminder that a single seed cannot distinguish architectures, which is why the
scoring paths are paired across many.

## What the end maps showed: C1-C6 orbit and never acquire the target

Rendering every architecture's final plan view side by side made a pattern
visible that no summary metric had surfaced: **C1-C6 fly a large closed loop and
never approach the target**, while C0 and C7-C14 go more or less straight to it.

Measured on seed 3, same scene for both:

| | belief queries | target detected |
|---|---|---|
| c2 | 104 | **0** |
| c7 | 132 | 70 (53%) |

c2 never sees the target at all. Its verifier, monitor and memory therefore have
nothing to act on, which is the same root cause as the identical C2-C6 numbers
seen earlier — not a wiring fault, an acquisition fault.

### Why

Neither policy detects the target at t=0, so `grid_nav`'s claim that "the target
is within sensor range from the start" is true of range and false of field of
view. The two families then diverge in how they look for it:

* **C7** yaws continuously while translating — 21 deg/s in the first second —
  sweeping the 90 deg FOV across the horizon, and acquires the target early.
* **C1-C6** fly waypoint to waypoint with the nose pointed along travel. The
  exploration spiral is anchored at launch with the heading advancing on a
  clock, so the vehicle circles at roughly constant radius with the camera
  pointing tangentially — past the target rather than at it.

A 35 m target inside a 45 m sensor range is never acquired in 90 seconds. That
is a search-pattern defect, not a semantics defect, and it currently sets the
ceiling for the entire waypoint and skill family.

### Also fixed here

Every architecture now renders a camera panel. The panel was blank for the
non-vision configurations only because `grid_nav` does not pay to render frames
no policy reads — the vehicle always had a camera. Verified on c0/c4/c9/c13 that
turning rendering on leaves the trajectory bit-identical, so the video shows the
same episode that was scored. `--no-render` restores the old behaviour.

The legend moved out of the plan panel into the header, where it was covering
the target whenever the target sat in the bottom-left, and the view padding grew
from 1.15x to 1.35x so a target at the edge of the travelled area is not clipped.

## Ported drone_control's sweep. It did not fix acquisition, and the measurement says why

`plugins/reasoning/coverage.py` is a boustrophedon sweep ported from
`drone_control/src/agent/boustrophedon.py`, available as
`search_pattern: sweep`. The argument for it was already settled there by
measurement: frontier and spiral searches exist for *unknown* extent, and when
the extent is known — a stated geofence — coverage planning applies and is
provably complete where frontier is complete only in unbounded time.

Lane pitch is derived rather than chosen, and the derivation differs from the
original. drone_control treats the sensor as a disc, giving a swath of
2·R·sin(fov/2) either side of track. Here the camera is body-fixed and looks
*along* the lane, so a pass covers a forward wedge; the pitch is the wedge width
at half range, which is the conservative reading of the same geometry.

### It changed nothing that matters

| c2, grid_nav seed 3 | target acquired | final distance | path |
|---|---|---|---|
| spiral | 0 / 104 | 33.2 m | 368 m |
| sweep, 3 lanes @ 25.5 m | 0 / 104 | 36.4 m | 312 m |
| sweep, 8 lanes @ 11.1 m | 0 / 104 | 36.4 m | 307 m |
| sweep, 18 lanes @ 4.8 m | 0 / 104 | 35.4 m | 306 m |

`spiral` therefore stays the default. Flipping it to an unproven pattern would
have quietly changed every number measured so far for nothing.

### The actual blocker is occlusion, not coverage

Instrumenting the detection gate directly — range, field of view, and line of
sight, separately:

| | in range | in FOV | of those, occluded |
|---|---|---|---|
| c2 | 100% | 43% | **100%** |
| c7 | 100% | 61% | 13% |

The target is *always* within c2's sensor range and often within its field of
view. It is blocked by an obstacle every single time. c7 succeeds because it
flies toward the target and so reaches viewpoints with clear line of sight;
c2 searches from positions that never have any.

No lane pattern fixes line of sight, which is why every spacing gives the same
answer. drone_control had already framed this correctly from the other side:
the objective is **observed**, not **flown over**, which turns the problem from
coverage into the Watchman Route / TSP-with-Neighborhoods family — choose
viewpoints whose *visibility* covers the region, then tour them. That was
ranked there as option 4, "the principled optimum; needs a visibility
computation per candidate viewpoint".

That is the next thing to build, and this time the measurement above says
plainly what it has to achieve: a viewpoint set with unoccluded sight lines,
not more kilometres flown.

### Correction

I previously wrote that C1–C6's failure was a search-pattern defect and that the
camera pointed "past the target rather than at it". The field-of-view half of
that is real — 43% versus 61% — but it is not what decides the outcome.
Occlusion is, and I had not measured it before naming a cause.

## Altitude was the occlusion mechanism — and seed 3 was not representative

You were right about the mechanism. Obstacles on `grid_nav` top out at 11.1 m,
the mission permits 25 m, and the vehicle searched at **3.0 m** — below every
obstacle in the scene. It was threading between towers with the target at
z=2.9 m, so every sight line crossed one.

Adding `search_altitude_m` and flying the sweep above the obstacles, seed 3:

| | target acquired | final distance |
|---|---|---|
| sweep at 3 m (cruise) | 0 / 104 | 33.2 m |
| sweep at 14 m | 6 / 47 | 11.1 m |
| sweep at 20 m | 8 / 23 | 12.7 m |

Acquisition goes from never to a third of queries. The occlusion diagnosis and
the altitude explanation are both confirmed.

### But the conclusion I drew from it was wrong

Scored over seeds 1–8 rather than the one seed the video happened to use:

| | success | distance | collisions |
|---|---|---|---|
| c2 spiral at cruise (baseline) | **0.62** | 12.6 m | 0.00 |
| c2 sweep at 18 m | 0.00 | 30.5 m | 0.38 |
| c3 sweep at 18 m | 0.00 | 30.6 m | 0.38 |

**The baseline was never broken.** c2 succeeds on 5 of 8 seeds. Seed 3 is simply
a hard seed, and I generalised "C1–C6 orbit and never acquire the target" from
the single episode I had rendered as a video. That claim was false as stated;
it is true of seed 3 and not of the regime.

High-altitude search is also worse overall, not better: acquiring the target
from 18 m means descending onto it through the obstacle field, and c2 has no
shield, so 3 of 8 seeds end in a collision.

### What actually stands

* `search_altitude_m` and `search_pattern: sweep` exist and are measured. Both
  stay non-default because neither has earned it.
* Altitude is a genuine architectural lever — sight lines traded against
  approach time — and it now has a knob and a number attached.
* The lesson is procedural: a video is one seed. It is excellent for seeing
  *how* a run fails and worthless for deciding *how often*. I used it for the
  second and should not have.

## Seven families as structure, not prose

The design space is now data. `ArchitectureConfig` carries `family` and
`ablation_of`, every shipped config declares both, and `validate_family_set`
enforces the rule: **seven families, exactly one base each, every other member
naming what it modifies.**

```
classical_baseline       BASE c0
llm_tool_planner         BASE c1
vlm_semantic_waypointer  BASE c2   ablations: c2g
hybrid_stack             BASE c3   ablations: c3g c4 c4g c5 c5g
selective_recovery       BASE c6   ablations: c6g
direct_vla               BASE c8   ablations: c7 c7t c8t c9
fast_slow_hierarchy      BASE c12  ablations: c10 c11 c13 c14
```

Two base choices worth stating. **C8, not C7, is the direct-VLA base**: shipping
a learned policy with no safety shield is the ablation, not the default, so C7
is "remove the shield". **C12, not C10, is the hierarchy base**: a concurrent
reasoner over chunked actions is the shape CognitiveDrone and LiteVLA-H actually
describe, and C10 is "make it blocking and single-step".

`uavlab families` prints the structure and exits non-zero if it is violated.

### What the rule caught immediately

`ablation_of` inherits through `_base_`, and C8 inherits from C7. Declaring C7
an ablation of C8 therefore made C8 an ablation of *itself*, and the same for
C12 through the C10→C11→C12 chain. The bases now set `ablation_of: null`
explicitly, with a comment saying why, because a future reader would otherwise
delete it as redundant.

### Where the field is required

`family` is optional on the model and mandatory on the shipped set. Unit tests
build throwaway configs to exercise the router and scheduler; those are not
points in the design space and forcing them to name a family would be
bookkeeping with no reader. The requirement is enforced where the claim needs to
hold — over `configs/` — by `validate_family_set` and a smoke test.

`test_every_ablation_differs_from_its_base` also fails an ablation that changes
nothing, since that is a duplicate rather than an experiment. 230 tests pass.

## Baseline: the seven family bases over 20 seeds

`grid_nav`, seeds 1-20, scripted policies only. Per-episode records in
`reports/baseline_7families.json`, table in `reports/baseline_7families.md`.

| base | family | success | 95% CI | collisions | median distance when it fails | failure modes |
|---|---|---|---|---|---|---|
| c0 | classical_baseline | **0.80** | 0.60 - 0.95 | 0.15 | 21.5 m | collision 3, timeout 1 |
| c1 | llm_tool_planner | **0.45** | 0.25 - 0.65 | 0.00 | 30.2 m | timeout 11 |
| c2 | vlm_semantic_waypointer | **0.70** | 0.50 - 0.90 | 0.05 | 32.1 m | timeout 5, collision 1 |
| c3 | hybrid_stack | **0.60** | 0.40 - 0.80 | 0.05 | 29.7 m | timeout 7, collision 1 |
| c6 | selective_recovery | **0.60** | 0.40 - 0.80 | 0.05 | 29.7 m | timeout 7, collision 1 |
| c8 | direct_vla | **0.55** | 0.35 - 0.75 | 0.00 | 29.3 m | timeout 9 |
| c12 | fast_slow_hierarchy | **0.55** | 0.35 - 0.75 | 0.00 | 29.8 m | timeout 9 |

### What this does and does not say

**Nothing separates.** Every interval except c0-versus-c1 overlaps every other.
Twenty seeds cannot rank seven architectures whose true rates sit between 0.45
and 0.70, and no ablation should be read against a base until the base has more
seeds behind it. This table is a floor check, not a result.

**The ceiling is 0.80, not 1.00.** C0 reads ground truth and still collides on 3
of 20. Some of what every other architecture loses is inherited from the flight
stack rather than from its semantics, and that share is now quantified.

**Every failure is an acquisition failure.** Not one failed episode across all
140 ended within 5 m of the goal — the closest was 9.7 m, and the medians sit
near 30 m. Nothing arrives and forgets to stop. Whatever is wrong is upstream of
stopping, in finding the target at all.

I had read the opposite from an earlier column: c8's median final distance over
*all* episodes was 1.7 m, which looked like arrive-and-hover. That median mixed
successes with failures. The table now reports distance among failures only,
which is the number that carries information.

### C3 and C6 are the same architecture in practice

They produce **identical results on 18 of 20 seeds**. C6 is C3 plus a geometric
progress watcher and an event-triggered recovery reasoner, and on these seeds
that machinery almost never changes the outcome. Either the trigger rarely fires
or its detour is what the planner would have done anyway — worth separating, but
as it stands the `selective_recovery` family has no measured behaviour of its
own on `grid_nav`.

### Not changed

Nothing in the runtime, the configs or the defaults. This entry is measurement.

## The search leg was three seconds when it needed nine

Debugging from the end-map grid rather than the metrics found the largest defect
in the whole testbed. Seven bases against four seeds
(`reports/videos/base_grid.png`) showed C1–C6 tracing a *closed loop* rather
than an outward spiral, on every seed, whatever the target's position.

Instrumenting the spiral against its own commanded target, c2 on seed 3:

```
   t   commanded radius   achieved radius
 0.0                8.0               0.0
20.9               34.4              18.5
41.8               54.0              20.2
62.7               54.0              18.4
83.5               54.0              20.2
```

The search commanded points up to **54 m** from launch while the vehicle never
exceeded **21.5 m** and oscillated between 6 and 21 m for the whole episode.

### The arithmetic

`explore_turn_rad` is 50 deg and `explore_dwell_s` was a fixed 3.0 s. Consecutive
search points are a chord apart, and at the geofence radius that chord is 45.6 m
— **9.1 s of flight at the mission's 5 m/s.** Given 3 s the vehicle covered a
third of it, the heading moved on, and the next leg pulled it back. It was not
searching, it was chasing a point that outran it.

`explore_dwell_s` now defaults to 0, meaning *derive it*: chord length over
permitted speed, both taken from the mission's own constraints. It stays purely
time-based, so the fairness property holds — search coverage still cannot become
a function of decision rate — and it is identical across architectures because
it depends on nothing an architecture chooses.

### Effect, on 40 seeds never looked at during the diagnosis (101–140)

| base | family | before (seeds 1–20) | after (seeds 101–140) |
|---|---|---|---|
| c0 | classical_baseline | 0.80 | 0.88 |
| c1 | llm_tool_planner | 0.45 | 0.70 |
| c2 | vlm_semantic_waypointer | 0.70 | 0.95 |
| c3 | hybrid_stack | 0.60 | 0.97 |
| c6 | selective_recovery | 0.60 | 0.95 |
| c8 | direct_vla | 0.55 | 0.93 |
| c12 | fast_slow_hierarchy | 0.55 | 0.62 |

C0 is the control: it reads ground truth and never explores, so the fix must not
move it, and on the same seeds it does not.

### What this changes about earlier entries

Almost every earlier conclusion about C1–C6 was measured on a broken search and
should be re-read. Specifically:

* "C1–C6 orbit and never acquire the target" — the mechanism is now named. It
  was not the pattern, the field of view, or occlusion. It was a leg too short
  to fly.
* The occlusion measurement (target in range 100%, blocked 100%) was real but
  downstream: the vehicle was pinned near launch behind the obstacle cluster
  because it could not travel, not because coverage was wrong.
* The boustrophedon port failed for the same reason and would now be worth
  re-testing, since its lane ends are 42 m away and were equally unreachable.
* `search_altitude_m` was measured against a search that could not travel.

### Two things the new baseline says

**C0 is no longer a ceiling.** At 0.88 it sits below C2, C3 and C6, and its
failures are collisions rather than timeouts. It bounds the *semantics*, not the
flight stack, and calling it a control ceiling now overstates it.

**C12 is the outlier at 0.62**, with 15 timeouts, against C8's 0.93 — the
hierarchy is markedly worse than the plain shielded VLA it is built on. That is
now the largest unexplained gap in the set.

230 tests pass. `reports/baseline_7families.{json,md}` regenerated on seeds
101–140.

## A decision register, and where things belong

`docs/RESEARCH_LOG.md` is new: every design decision with a stable identifier,
its rationale, the evidence behind it, what was rejected, and a status. Thirty
entries covering experiment structure, runtime fairness, search, perception,
memory, the learned policy and tooling. `docs/README.md` states which of the four
documents a given thing belongs in.

The split that matters: **CHANGES.md is chronological, RESEARCH_LOG.md is
organised.** This file answers "what happened and when"; the register answers
"why is it like this, and what would change my mind". A reader coming to the
results needs the second and cannot navigate the first.

Three conventions worth keeping:

* `Evidence: none` is a legitimate value. It marks a decision `provisional` and
  tells a later reader exactly what to go and measure. D-03 and D-17 carry it.
* Corrections never delete. The status becomes `superseded by D-nn`, and
  withdrawn claims go in a table at the bottom — six of them so far — because a
  reader who meets an old claim elsewhere needs to find out it was withdrawn.
* Open questions are ranked, with a first step each. C12 at 0.62 against C8's
  0.93 is currently first.

## Frame-to-pose binding, pinned

Raised as a concern: the vehicle flies while a slow model thinks, so are the
image and the pose out of sync? Checked rather than assumed — they are not. The
frame and the pose come from the same observation packet, and the unprojection
produces a point in **world** coordinates from the capture pose, so a waypoint
stays valid however far the vehicle has moved by the time it executes.

`test_the_waypoint_is_unprojected_from_the_pose_that_took_the_frame` pins it,
because the failure would be silent: the same pixel read against the current pose
still yields a plausible waypoint, just the wrong one, with the error growing
with model latency and looking like a model-quality problem.

What *is* wrong in that path is depth: the waypoint is placed at a fixed hop
distance along the ray because a monocular pixel carries no range. Recorded as
D-17, status `open`, unquantified — and it sits under every waypoint-family
result.

231 tests pass.
