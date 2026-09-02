"""Composition invariants for the declared OnFly native-dynamics profile."""

from pathlib import Path

from uavlab.core.compose import load_architecture, load_environment


def test_native_dynamics_are_explicit_and_normalized_profile_is_unchanged() -> None:
    config_root = Path(__file__).parents[2] / "configs"
    normalized_env = load_environment("grid_nav_onfly", config_root)
    native_env = load_environment("grid_nav_onfly_native_dynamics", config_root)
    native_arch = load_architecture("c5_onfly_qwen4_native_dynamics", config_root)

    assert normalized_env.params["constraints"]["max_speed_mps"] == 5.0
    assert native_env.params["max_speed_mps"] == 0.6
    assert native_env.params["accel_tau_s"] == 1.0
    assert native_env.params["constraints"]["max_speed_mps"] == 0.6
    assert native_env.params["constraints"]["max_accel_mps2"] == 0.6
    assert native_arch.profile_of == "c5"
    assert native_arch.controller.params["max_yaw_rate_rps"] == 0.4
    assert native_arch.planner is not None
    assert native_arch.planner.params["max_acc_mps2"] == 0.6
    assert native_arch.monitor is not None
    assert native_arch.monitor.params["layout"] == "history_sheet_plus_latest"
    assert native_arch.monitor.params["acquisition_confirmations"] == 2
    assert native_arch.monitor.params["lost_yaw_rate_rps"] == 0.4
