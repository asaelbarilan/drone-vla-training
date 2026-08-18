"""How measured model latency is charged to the simulation clock.

This is a methodology guard, not a performance one. Architectures are compared
paired by seed, which requires that the same seed produce the same episode. A
real model's latency varies call to call, and charging that variation to the
simulation clock couples the whole trajectory to wall-clock jitter.

Measured on this repository, same seed, two separate processes:

===============  =========================================
mode             final distance to goal
===============  =========================================
``measured``     36.8 m, then 7.2 m
``quantised``    10.9 m, then 18.5 m
``fixed``        identical to four decimals
===============  =========================================

Quantising sounds sufficient and is not: a call landing either side of a bucket
boundary flips one decision, and that flip cascades. These tests pin the
behaviour so the default cannot drift back.

No network and no model server: the charging policy is pure arithmetic, so it is
tested as arithmetic.
"""

from __future__ import annotations

import pytest

from uavlab.core.registry import REGISTRY

S = 1_000_000_000


def backend(**params):
    return REGISTRY.build("inference", "ollama", params)


def test_the_default_is_the_reproducible_mode():
    """Anything else silently breaks paired-by-seed comparison."""
    assert backend().charge_mode == "fixed"


def test_fixed_mode_ignores_measured_jitter_entirely():
    b = backend(charge_mode="fixed", fixed_latency_s={"policy": 2.2})
    charged = {b._charge_for("policy", int(m * S)) for m in (0.5, 1.7, 2.31, 9.9)}
    assert charged == {int(2.2 * S)}, "fixed mode must be independent of measurement"


def test_fixed_mode_falls_back_for_an_unlisted_role():
    b = backend(charge_mode="fixed", fixed_latency_s={"policy": 2.2}, fallback_latency_s=1.5)
    assert b._charge_for("monitor", int(9.0 * S)) == int(1.5 * S)


def test_measured_mode_passes_the_measurement_through():
    b = backend(charge_mode="measured")
    assert b._charge_for("policy", int(1.73 * S)) == int(1.73 * S)


@pytest.mark.parametrize(
    ("measured", "expected"),
    [(1.70, 1.75), (1.73, 1.75), (1.86, 1.75), (1.92, 2.00), (2.09, 2.00)],
)
def test_quantised_mode_rounds_to_the_bucket(measured, expected):
    b = backend(charge_mode="quantised", latency_quantum_s=0.25)
    assert b._charge_for("policy", int(measured * S)) == pytest.approx(int(expected * S), abs=S // 100)


def test_quantising_does_not_actually_remove_divergence():
    """The reason `quantised` is not the default, as an executable statement.

    Two calls 60 ms apart in real time land in different buckets, so the
    simulation clock still sees a difference and the trajectory still diverges.
    """
    b = backend(charge_mode="quantised", latency_quantum_s=0.25)
    assert b._charge_for("policy", int(1.86 * S)) != b._charge_for("policy", int(1.92 * S))


def test_a_real_call_is_never_charged_as_free():
    """A slow model must never look instantaneous to the vehicle."""
    b = backend(charge_mode="quantised", latency_quantum_s=0.25)
    assert b._charge_for("policy", 1) > 0
    assert b._charge_for("policy", int(0.01 * S)) >= int(0.25 * S)


def test_an_unknown_charge_mode_is_rejected_at_construction():
    with pytest.raises(ValueError, match="charge_mode"):
        backend(charge_mode="whatever")


def test_measured_latency_is_still_reported_in_every_mode():
    """Reproducibility must not cost us the real cost of the model."""
    for mode in ("fixed", "quantised", "measured"):
        b = backend(charge_mode=mode, fixed_latency_s={"policy": 2.2})
        b._latency_ns["policy"] = int(3.5 * S)
        b._charged_ns["policy"] = int(2.2 * S)
        b._calls["policy"] = 1
        stats = b.stats()
        assert stats["inference_latency_s_policy"] == pytest.approx(3.5), (
            f"{mode} lost the measured latency"
        )
        assert stats["inference_charged_s_policy"] == pytest.approx(2.2)


def test_the_shipped_gemma_profile_is_reproducible(config_root):
    """The profile people will actually run must not be the irreproducible one."""
    from uavlab.core.compose import load_architecture

    arch = load_architecture("c2g", config_root)
    params = arch.inference.params
    assert params.get("charge_mode") == "fixed", (
        "the shipped Gemma profile must charge a constant, or paired-by-seed "
        "comparison across its architectures is invalid"
    )
    assert params.get("fixed_latency_s", {}).get("policy", 0) > 0
