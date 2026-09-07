# AGENTS.md — start here

Entry point for an agent picking up this repository. It says where the work
stands, what to do next, and which rules must not be broken. It deliberately
does not restate the evidence: every claim below names the decision that holds
it, in [`docs/RESEARCH_LOG.md`](docs/RESEARCH_LOG.md).

Read [`docs/README.md`](docs/README.md) first for what belongs in which file.
A new decision goes in `RESEARCH_LOG.md` with a new `D-nn`, rationale and
evidence. Corrections never delete the old entry; they mark it superseded.

## What this testbed is

A modular testbed for searching single-UAV foundation-model autonomy
architectures. Architectures are composed from configuration (`configs/`), run
against a deterministic simulator, and charged model latency on a simulated
clock. Seven families are the base; everything else is an ablation.

## Where we are — 2026-09-04

The harness works and catches its own defects. **C5 OnFly is the live front**,
and this week's work located its failure precisely.

Current five-seed development result on `grid_nav_onfly_native_long`
(240 s horizon, seeds 1060-1064):

| configuration | success |
| --- | ---: |
| `c0` classical planner, knows the goal | **5/5**, 63-84 s |
| C5 + Qwen3-VL 4B, pixel output | 1/5 |
| C5 + Qwen3-VL 4B, pixel output, told the winning route | 0/5 |
| C5 + Qwen3-VL 4B, five-word steering output, told the route | 0/5 |
| C5 + Gemma 3 4B, five-word steering output | 0/5 |

Five candidate causes have each been separately excluded by measurement:

- **Path budget** — raising the horizon 90 s to 240 s changed no outcome; the
  failures used 78-90 m of a 144 m budget (D-64).
- **Step source** — the vehicle realises under 10% of any commanded step before
  replanning, so waypoint distance barely reaches it (D-62).
- **Search and viewpoint choice** — the target is dead ahead at 35 m on every
  seed; there is nothing to search for (D-64).
- **Not knowing the route** — handed `c0`'s winning path in words, C5 does
  *worse*, 0/5 against 1/5 (D-66).
- **Output representation** — a five-word steering vocabulary scores 0/5 too,
  and the model simply repeats one word instead of one pixel (D-67).

What is left are **two model-independent defects**, both reproduced under two
different VLMs:

1. **Geofence deadlock.** The vehicle reaches ~55 m of the 60 m fence, every
   subsequent proposal lands outside it and is correctly refused, and nothing
   turns it around. It then holds position until the horizon expires. On the
   failing seeds 100% of verifier calls during the freeze are geofence refusals;
   the one success has zero across the whole episode (D-65, D-68).
2. **Acquisition latch false stops.** The monitor declares arrival at 8.5 m,
   14.2 m and 32.9 m from a 2 m goal radius, reporting
   `latest_scale=large, acquisition_count=2/2` — on seed 1060 while the vehicle
   had moved barely 2 m from its start (D-67, D-68).

A third finding is real but **not** currently binding: Qwen3-VL 4B does not
steer. Mean normalised entropy over the five-word vocabulary is 0.21 against
Gemma's 0.60, with no overlap between the two sets, and Qwen never selected
`hard_left` or `hard_right` in 925 decisions. Gemma steers three times better
and still scores 0/5, so fixing steering alone would not have changed a single
outcome (D-68).

## What to do next, in order

1. **Fix the geofence deadlock.** It blocks four of five seeds under both
   models. The fix is a fallback when every proposal is refused for the fence —
   an architecture decision, so record it as a `D-nn` before implementing.
   Success criterion: no episode ends frozen with 100% geofence refusals.
2. **Fix the acquisition latch.** Four false stops so far. A stop declared at
   32.9 m with `latest_scale=large` means the scale evidence is not constraining
   anything. Success criterion: no `agent_stopped` outside the goal radius.
3. **Re-run the five-seed gate** on `grid_nav_onfly_native_dynamics` (the frozen
   90 s profile) after 1 and 2, and compare against
   `reports/paper_implementation/C5_RETAINED_FIVE_SEED_RESULTS_20260901.md`.
4. **Only then** revisit steering and model choice.

Everything else open is in [`TODO.md`](TODO.md), ordered by what it blocks.

## Rules that must not be broken

- **Held-out seeds 1-40 are never trained on and never tuned against.**
  Development uses 1060-1064; training collection uses 1000+. This is enforced
  in `src/uavlab/training/splits.py` — do not work around it.
- **Do not hide the remaining search boundary** with colour detection,
  simulator truth, scripted target search, or a weaker SUPER substrate. This is
  the standing instruction that makes the negative results meaningful.
- **Privileged diagnostics are never reportable.** Configs tagged
  `privileged_diagnostic` (`c5_route_hint_s*`, `c5_route_direction_s*`) feed the
  model a route derived from `c0`'s successful trajectory, i.e. simulator truth.
  They answer "can the agent execute a route it is told?" and nothing else.
  Their numbers must not appear in any results table.
- **One seed is not a result.** Three readings this week were reversed by later
  seeds, and in each case the misleading seed was the one that ended early with
  few decisions. Check the sample size before concluding.
- **Verify a contract experiment distributionally.** The direction contract's
  original acceptance criterion asked whether bearings spread beyond +-10
  degrees, which a model emitting one fixed word passes. Use entropy or modal
  share (D-67).

## Running things

```bash
export PYTHONPATH=src
python -m uavlab.cli run --arch c5_onfly_qwen4_native_dynamics \
  --env grid_nav_onfly_native_long --seed 1060 --out runs/probe
python -m uavlab.cli verify c5          # does the architecture function
python -m pytest tests -q               # full suite, ~10 min
```

Two tests are sensitive to machine load rather than broken —
`tests/integration/test_verify.py::[c1]` (drives real `gpt-oss:20b`) and
`tests/smoke/test_all_architectures.py::test_the_core_runtime_imports_no_heavy_dependency`.
Both pass in isolation; run the suite on an idle machine before believing a red
result (D-63).

Model runs need the GPU to themselves. The profiles load a 4B VLM for both
policy and monitor on an 8.2 GB card; check nothing else holds it first:

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

## Uncommitted state

Nothing from this session is committed. `git status` shows the new configs,
the long-horizon environment, two reports under `reports/paper_implementation/`,
two notes under `docs/research/`, and the `step_from_model` and `route_hint`
parameters in `src/uavlab/plugins/reasoning/onfly.py` — both default off, both
unit-tested, neither changing any shipped profile.
