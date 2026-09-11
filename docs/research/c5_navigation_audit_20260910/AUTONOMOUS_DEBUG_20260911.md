# Bounded autonomous navigation debugging

Authorization: up to five development flights, 2026-09-11. Model remains repaired local Gemma E2B; no cloud calls or held-out seeds. User requested separate commits and CHANGES.md entries for reversibility.

Checkpoint: 3147bd4 captures the existing development state. D-87 monitor fix: c87aff6. Default active profile remains unchanged pending evidence.

## Corrected attribution

Policy pixel-to-target bbox distance is not automatically a grounding error: the original policy asks for a navigation waypoint, which may deliberately lie in free space. The monitor's target pixel, however, explicitly identifies the requested object. Its false-stop frame visibly contains a gray obstacle; the observed point consistency proves only stable geometry. Earlier conclusions treating all 36 off-bbox policy waypoints as wrong-object predictions were too strong. The recorded scores remain correct but require this interpretation.

## Predeclared budget

At most five complete or attempted development flights in this session. Each outcome determines the next change; no automatic seed sweep and no automatic API retries. Analyze saved traces without inference where possible. Successful schema tests are not navigation evidence.

## Run ledger

1. D-87 current-frame grounding monitor, seed 1061: running. One current image replaces temporal multi-image identity/status inference. Translation planner/controller and policy unchanged. Output ceiling raised for a short evidence field. 311 unit/contract checks pass. Three pre-existing Ruff warnings in unchanged step/direction code remain; new test code is clean.
