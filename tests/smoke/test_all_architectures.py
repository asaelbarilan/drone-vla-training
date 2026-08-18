"""Smoke tests: every shipped configuration launches and logs correctly.

This suite does not check *results*.  Its job is to catch the failure that
would otherwise be found halfway through an overnight sweep: a configuration
that no longer builds, a plugin that was renamed, a log that lost a field.
"""

from __future__ import annotations

import pytest

from uavlab.contracts import EventType
from uavlab.core.compose import list_architectures, list_environments, list_experiments
from uavlab.core.registry import REGISTRY

from tests.conftest import ALL_ARCHITECTURES, run_one


def test_the_full_c0_c14_set_is_present(config_root):
    ids = {name.split("_", 1)[0] for name in list_architectures(config_root)}
    missing = set(ALL_ARCHITECTURES) - ids
    assert not missing, f"missing architectures: {sorted(missing)}"
    # Anything beyond the canonical fifteen must be a declared real-model
    # variant, not a stray config that drifted into the set. Suffixes:
    #   g = Gemma 3 4B vision policy,  t = trained (behaviour-cloned) policy
    extra = ids - set(ALL_ARCHITECTURES)
    undeclared = {e for e in extra if not e.endswith(("g", "t"))}
    assert not undeclared, f"undeclared extra architectures: {sorted(undeclared)}"


CANONICAL_REGIMES = {
    "grid_nav", "object_search", "failure_recovery", "fine_maneuver", "occlusion",
}


def test_all_five_benchmark_regimes_are_present(config_root):
    assert CANONICAL_REGIMES <= set(list_environments(config_root))


def test_every_regime_declares_a_distinct_task_family(env_factory, config_root):
    """Each canonical regime tests something different.

    Vision variants are excluded: `grid_nav_vision` is deliberately the same
    regime as `grid_nav` with the camera switched on, so that a real-model run
    is comparable against the scripted baselines on identical scenes.
    """
    families = [env_factory(name).task_family for name in sorted(CANONICAL_REGIMES)]
    assert len(set(families)) == len(families), "two regimes share a task family"


def test_the_staged_experiments_are_present(config_root):
    experiments = set(list_experiments(config_root))
    for required in ("macro_screen", "safety_screen", "timing_recovery", "memory_horizon"):
        assert required in experiments, f"missing staged experiment {required}"


@pytest.mark.parametrize("name", ALL_ARCHITECTURES)
def test_architecture_launches_and_produces_a_well_formed_log(name, arch_factory, env_factory):
    arch = arch_factory(name)
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 12.0})
    result, orchestrator = run_one(arch, env, seed=1)

    assert result.error is None, f"{name} errored: {result.error}"
    assert result.architecture_id == arch.id
    assert result.sim_duration_s > 0.0

    log = orchestrator.log
    assert log.count(EventType.EPISODE_START) == 1
    assert log.count(EventType.EPISODE_END) == 1
    assert log.count(EventType.CONTROL) > 0
    assert log.count(EventType.OBSERVATION) >= 0
    for event in log.events:
        assert event.t_sim_ns >= 0 and event.t_wall_ns >= 0
        assert event.episode_id == result.episode_id
    assert [e.seq for e in log.events] == list(range(len(log.events)))


@pytest.mark.parametrize("name", ALL_ARCHITECTURES)
def test_every_metric_is_finite(name, arch_factory, env_factory):
    """A NaN or infinity in the metrics would poison every downstream mean."""
    import math

    arch = arch_factory(name)
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 12.0})
    result, _ = run_one(arch, env, seed=1)
    for key, value in result.metrics.items():
        assert isinstance(value, (int, float)), f"{name}: {key} is not numeric"
        assert not math.isnan(value), f"{name}: {key} is NaN"
        assert math.isfinite(value) or value == -1.0, f"{name}: {key} is {value}"


@pytest.mark.parametrize("env_name", ["grid_nav", "object_search", "failure_recovery",
                                      "fine_maneuver", "occlusion"])
def test_every_regime_runs(env_name, arch_factory, env_factory):
    arch = arch_factory("c0")
    env = env_factory(env_name).model_copy(update={"max_episode_s": 15.0})
    result, _ = run_one(arch, env, seed=1)
    assert result.error is None, f"{env_name} errored: {result.error}"


def test_failure_injection_actually_fires(arch_factory, env_factory):
    """The recovery regime is only meaningful if its failures happen."""
    arch = arch_factory("c0")
    env = env_factory("failure_recovery").model_copy(update={"max_episode_s": 30.0})
    _, orchestrator = run_one(arch, env, seed=1)
    assert any(inj.fired for inj in orchestrator.env.injections), (
        "no injected failure fired in the failure_recovery regime"
    )


def test_the_event_log_writes_to_disk(arch_factory, env_factory, tmp_path):
    arch = arch_factory("c2")
    env = env_factory("grid_nav").model_copy(update={"max_episode_s": 10.0})
    run_one(arch, env, seed=1, out_dir=tmp_path)
    jsonl = tmp_path / "events.jsonl"
    assert jsonl.is_file() and jsonl.stat().st_size > 0
    import json

    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    first = json.loads(lines[0])
    assert first["event_type"] == "episode_start"
    assert "t_sim_ns" in first and "t_wall_ns" in first


def test_the_core_runtime_imports_no_heavy_dependency():
    """Acceptance criterion: core tests need no ROS, CUDA or network.

    Run in a subprocess deliberately.  Checking ``sys.modules`` inside the
    pytest session would measure whatever the plugins and the analysis extras
    happened to import, not what ``import uavlab`` costs — and would pass or
    fail for reasons having nothing to do with this repository.
    """
    import subprocess
    import sys
    import textwrap

    probe = textwrap.dedent(
        """
        import sys, json
        import uavlab
        from uavlab.core.orchestrator import run_episode  # the full runtime path
        # stdlib `socket` is excluded: asyncio imports it unconditionally, and
        # importing it is not using the network. `http.client` stays, because
        # nothing in the core runtime has any reason to reach for it.
        forbidden = {"rclpy", "torch", "cv2", "airsim", "gz", "mavsdk",
                     "requests", "urllib3", "http.client", "aiohttp", "httpx"}
        print(json.dumps(sorted(forbidden & set(sys.modules))))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, f"importing uavlab failed:\n{completed.stderr}"
    import json

    loaded = json.loads(completed.stdout.strip().splitlines()[-1])
    assert not loaded, f"importing uavlab pulled in heavy dependencies: {loaded}"


def test_optional_simulator_adapters_fail_with_an_actionable_message():
    """A missing simulator must say what is missing, not raise an obscure error."""
    from uavlab.adapters import load_adapter

    load_adapter("project_airsim")
    with pytest.raises(NotImplementedError, match="not installed"):
        REGISTRY.build("environment", "project_airsim", {})


def test_cli_validate_config_accepts_every_shipped_architecture():
    from uavlab.cli import main

    assert main(["validate-config"]) == 0


def test_cli_list_runs():
    from uavlab.cli import main

    assert main(["list"]) == 0
