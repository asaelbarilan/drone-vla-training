# C5 Gemma navigation investigation

Navigation remains unresolved. The next priority is the local Gemma vision
runtime, before another architecture flight sweep (D-76).

## Controlled waypoint-cue experiment

All five baseline replays match recorded final distance exactly. With a
previous waypoint cue, 405/418 decisions echo it within one pixel. Removing
only that cue reduces echo to 17/430, but still scores 0/5 with no collisions
or false stops. Cue removal is not promoted to the active profile.

| Seed | Baseline final distance (m) | Without cue (m) | Without cue outcome |
|---|---:|---:|---|
|1060|57.46|54.98|timeout|
|1061|20.66|43.93|timeout|
|1062|30.35|34.35|timeout|
|1063|32.87|27.40|timeout|
|1064|47.83|54.96|timeout|

## Vision runtime evidence

The exact close-view input below contains a large red rectangle. Gemma answers
absent and produces unrelated scene descriptions. These are real model calls,
not mocked responses.

![Exact model input](GEMMA_CLOSE_VIEW_INPUT_20260907.png)

The local runtime logs show the same F16-to-F32 vision patch conversion that
an [open upstream fix](https://github.com/ollama/ollama/pull/16879) identifies
as breaking unified Gemma E2B/E4B vision on Windows. The corresponding
[issue](https://github.com/ollama/ollama/issues/16532) remains open. This is a
likely runtime cause requiring a before/after recognition control, not yet a
verified local repair. Changing prompts, fixed crops, enlargement and the
API endpoint did not restore the tested recognition case.

## Reproduction and continuation

- Offline replay: `python scripts/analyze_onfly_run.py <run_dir> --output <json>`
- Matched flights: `tmp/run_gemma4_fresh_view_20260907.py` (completed; refuses overwrite).
- Grounding probes: `tmp/probe_gemma_*_20260907.py`; exact requests and responses
  are saved in the accompanying probe JSON files.
- Validate a same-model vision runtime repair with clearly visible and absent
  controls before repeating navigation. Preserve the shared valley server.

288 unit/contract tests pass. Changed-file Ruff and whitespace checks pass.
All models used in the new flights and probes are Gemma 4 E2B. Shared-server
latency is not an isolated performance benchmark. No held-out seeds were used.
