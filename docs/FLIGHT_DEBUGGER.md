# Flight debugger

Open `reports/debugger/index.html` directly in Edge or Chrome. It is a portable,
self-contained replay, with no server, internet or model connection required.
The local preview is also available while its server is running at
http://127.0.0.1:8765/index.html.

## Inspect a flight together

1. Choose a saved flight and press **Play**, or scrub the timeline.
2. Select a policy or monitor decision. The top camera stays at the timeline
   cursor; **Source observation** shows the frame that informed the selected
   decision. **View capture time** moves the top views to that source instant.
3. Compare **VLM evidence** with **Execution flow**: source capture, output
   availability, acceptance/rejection, verifier changes and first control using
   that decision. Measured model latency and simulated age are different fields.
4. Use **Code** for the implementation. For newly captured runs, **Inspect
   recorded code** opens the source snapshot at the actual event-emitting line.
5. Write expected/observed behavior in the review note and download it. Send its
   run, timestamp and decision ID to Codex. The address hash also preserves the
   selected moment. Form competing explanations before changing navigation.

The map shows actual flight, heading, velocity commands and logged semantic
planner goals. Newly captured trajectories show their full path. The observer
is an elevated reconstruction of the scene, with an adjustable orbit angle.
Goal truth is a debugger-only overlay, never a policy input.

## Rebuild from saved runs — no inference

From the repository in PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m uavlab.cli debugger `
  runs/c5_guarded_monitor_20260911_s1061 `
  runs/c5_gemma_runtime_fixed_target_stop_20260907_s1061 `
  runs/c5_fix_gate_20260907_fence90_s1061 `
  --out reports/debugger/index.html
```

These are the guarded-monitor Gemma failure, repaired Gemma baseline failure,
and historical Qwen success on development seed 1061. They are context for
inspection, not a controlled model comparison. The exporter checks every logged
position, final distance and available source-frame reference before writing.
The adjacent `index.json` records validation counts and event-log hashes.

Do not use `uavlab replay` for this: that older command reruns an architecture,
including inference. `uavlab debugger` replays only saved physical commands.

## Capture exact evidence on a future authorized run

Append `--debug-capture` to a normal `uavlab run` command and use a fresh `--out`
directory. Programmatic runs use `Orchestrator(..., debug_capture=True)`.
This flag does not start anything by itself. No new navigation run is part of
the debugger delivery; the previous flight budget remains exhausted.

The run's `debug/` directory contains:

- `calls/`: prompt, response schema, requested model/role, source observation,
  start/completion time, returned payload, latency and completion/error status.
- `images/`: exact encoded request images at the plugin/backend boundary,
  including composites or history sheets actually submitted by the plugin.
- `sources/`: immutable code snapshots referenced by calls and event locations.

The event log additionally records the typed proposal and full planner path.
Failed/cancelled calls retain their request; the Events tab exposes captured
calls that never produced a decision. Backend transport headers, credentials,
and credential-file contents are outside this recorder. Backend internal
failover attempts remain represented by the backend's existing event records.

Capture is off by default and does not change the architecture configuration or
charge extra simulated latency. File writes add wall-clock overhead, so capture
runs should not be used as clean latency benchmarks. Reusing a directory with
existing call records is rejected to avoid mixing evidence from different runs.

## Evidence limits

- Old runs did not save raw prompts, outputs, exact request-image layouts or full
  paths. Those fields say **not recorded**; they are never recreated from code.
- Replayed RGB uses the current simulator/renderer. Matched positions and
  source reference IDs validate alignment, not historical pixel identity:
  the older sensor digests encode pose/reference data, not image-byte hashes.
- Source capture, output availability and first control are separate instants.
  Monitor matching uses `evidence_observation_seq`; missing IDs are counted,
  not substituted with completion-time frames. Historical inference event
  matching is explicitly labeled as a unique role/completion-time association.
- The recorder saves the actual response delivered to the plugin. It does not
  invent hidden reasoning. An explanation appears only when one was returned
  or explicitly logged.
- Historical code tabs are labeled **current checkout reference**. New captures
  provide source snapshots and actual emitter locations.
- Version one reconstructs `grid3d` runs with constant control cadence and no
  injected failures. Unsupported simulators, cadence/pose mismatches, and
  held-out development inspection of seeds 1–40 are rejected.

## Verification

```powershell
python -m pytest tests/unit tests/contract -q
# Optional browser check: requires playwright and installed Microsoft Edge.
python scripts/check_flight_debugger_ui.py --url file:///ABSOLUTE/PATH/index.html
```

The browser check uses only a generated page. It covers source-time jumps, role
filtering, flow/code tabs, run switching, terminal frames, playback, downloaded
notes and responsive layout. Unit tests cover delayed-source matching, rejected
decision routing, replay mismatch rejection, safe HTML embedding, exact capture,
cancellation, capture defaults and preservation of control/simulation timing.
