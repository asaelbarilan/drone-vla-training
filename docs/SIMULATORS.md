# Simulators: what runs where, and why

## Current state

| Adapter | Status | Needs |
|---|---|---|
| `grid3d` — deterministic in-process 3-D | **working, default** | nothing |
| `scene_replay` — same dynamics, scene from a JSON file | **working** | nothing |
| `px4_sitl` — PX4 SITL + Gazebo | stub, raises with an install hint | PX4 + Gazebo |
| `project_airsim` — vision-rich scenes | stub, raises with an install hint | Project AirSim |

Everything in this repository — every test, every sweep, every number produced
so far — runs on `grid3d`. **AirSim is not installed and is not used.**

## Why the default is not a photorealistic simulator

The environment adapter is authoritative; simulators are replaceable
implementations of it. Choosing a heavyweight simulator as the architectural
centre would have two bad consequences:

1. **Screening becomes too slow to do.** Architecture screening runs in the
   thousands of episodes. On `grid3d` a 90-second mission executes in under a
   second of wall time and needs no GPU, so a fifteen-architecture sweep across
   eight seeds finishes in about a minute.
2. **The simulator leaks into the science.** If the only way to run an
   experiment is through one renderer, that renderer's quirks become part of
   every result.

So the adapter priority is:

1. deterministic lightweight environment — architecture screening;
2. PX4 SITL + Gazebo — dynamics, control authority, recovery realism;
3. Project AirSim — vision-rich scenes;
4. dataset replay;
5. an optional high-throughput backend.

Architectures earn promotion up that list by surviving the level below. The same
architecture YAML must run at every level with only the environment config
swapped — and if it ever cannot, the adapter boundary has leaked and *that* is
the bug.

## What `grid3d` does and does not model

**Does:** 3-D kinematics with a first-order velocity lag (so control rate
genuinely matters), axis-aligned box obstacles, swept-segment collision (so a
fast vehicle cannot tunnel through a thin wall between ticks), a 24-ray
horizontal depth fan, field-of-view- and range-limited semantic detections with
occlusion, detection noise, decoy targets, scheduled occlusion, and injectable
failures (blocked path, decoy appearance, sensor dropout, wind gust).

**Does not:** aerodynamics, motor dynamics, wind fields, rendering, real
imagery, or anything a real detector would struggle with.

Fidelity is deliberately low. The job is to make *architectural* differences
visible — timing, staleness, stopping correctness, safety interventions,
recovery admission — not to model flight. Anything that survives here gets
promoted, and anything that only works here was never an architecture result.

One detail worth stating plainly: ground truth exists only in `status()`, which
scores the episode. A policy never sees it. The one exception is C0, the oracle
control ceiling, which must set `allow_privileged_observations: true` to receive
it — an explicit, greppable flag rather than a special code path.

## Note on AirSim specifically

The legacy `microsoft/AirSim` repository is archived and is **not** the target.
Project AirSim is the maintained successor and is the one the stub points at.
Legacy AirSim compatibility may still be worth an adapter later, because several
UAV datasets and papers use it — but as an adapter, never a dependency.

## Adding a real simulator

Implement `EnvironmentAdapter`: produce a valid `ObservationPacket`, consume the
canonical `ControlCommand`, report `EnvironmentStatus`. Then:

- convert ENU↔NED exactly once, at the adapter boundary, through
  `uavlab.core.frames`. No plugin may ever see NED;
- keep flight-stack message types out of every contract;
- populate `rgb`/`depth` with real frames and leave `semantic_hits` empty, so a
  real perception plugin does the detection work `grid3d` simulates;
- take simulation time from the simulator. `SimClock` becomes an observer rather
  than a driver, and `decision_age` is then measured against real simulator
  timestamps.

The contract tests in `tests/contract/` run over the registry, so a new adapter
is covered as soon as it registers itself — add its name to
`ENVIRONMENT_ADAPTERS` in `tests/contract/test_plugin_contracts.py` once it can
run without external services, or mark it `requires_sim` if it cannot.
