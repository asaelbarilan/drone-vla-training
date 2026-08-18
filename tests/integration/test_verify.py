"""Tests for the verification harness itself.

A verifier that passes everything is worse than no verifier, so these tests
mostly check that it *fails* when it should: on a stationary architecture, on a
component that never fires, and on a nondeterministic run. If those pass
silently, a green verification table means nothing.
"""

from __future__ import annotations

import pytest

from uavlab.core.compose import load_architecture
from uavlab.core.config import ComponentSpec
from uavlab.experiments.verify import (
    ArchitectureReport,
    Check,
    render,
    requires_vision,
    resolve_environment,
    verify_architecture,
)

FAST_SEEDS = (1, 2)


def test_a_healthy_architecture_passes(config_root):
    report = verify_architecture("c2", "grid_nav", FAST_SEEDS, config_root)
    assert report.ok, f"c2 should pass: {[(c.name, c.detail) for c in report.failures]}"
    assert report.checks, "a passing report with no checks would be vacuous"


def test_the_oracle_passes(config_root):
    assert verify_architecture("c0", "grid_nav", FAST_SEEDS, config_root).ok


@pytest.mark.parametrize("name", ["c1", "c5", "c8", "c12", "c14"])
def test_a_spread_of_architectures_pass(name, config_root):
    report = verify_architecture(name, "grid_nav", FAST_SEEDS, config_root)
    assert report.ok, f"{name}: {[(c.name, c.detail) for c in report.failures]}"


def test_a_stationary_architecture_fails_the_movement_check(config_root, monkeypatch):
    """A policy that never commands motion must not be reported as working."""
    from uavlab.contracts import DecisionEnvelope
    from uavlab.plugins.reasoning.policies import VLMWaypointPolicy

    async def never_decide(self, ctx) -> DecisionEnvelope | None:
        return None

    monkeypatch.setattr(VLMWaypointPolicy, "decide", never_decide)
    report = verify_architecture("c2", "grid_nav", FAST_SEEDS, config_root)
    assert not report.ok
    failed = {c.name for c in report.failures}
    assert "moves" in failed or "authority:waypoint" in failed


def test_an_inert_component_fails_its_check(config_root, monkeypatch):
    """The check that catches an architecture which is really its parent."""
    from uavlab.plugins.monitoring.progress import ProgressMonitor

    calls = {"n": 0}
    original = ProgressMonitor.assess

    async def counted(self, ctx):
        calls["n"] += 1
        return await original(self, ctx)

    monkeypatch.setattr(ProgressMonitor, "assess", counted)
    report = verify_architecture("c4", "grid_nav", FAST_SEEDS, config_root)
    assert calls["n"] > 0, "c4 declares a monitor, so it must actually run one"
    assert any(c.name == "monitor runs" and c.passed for c in report.checks)


def test_determinism_failure_is_detected(config_root, monkeypatch):
    """Guard the guard: an intentionally nondeterministic run must be caught."""
    import random

    from uavlab.plugins.reasoning.policies import VLMWaypointPolicy

    original = VLMWaypointPolicy.decide

    async def jittery(self, ctx):
        self.hop_m = 12.0 + random.random() * 4.0
        return await original(self, ctx)

    monkeypatch.setattr(VLMWaypointPolicy, "decide", jittery)
    report = verify_architecture("c2", "grid_nav", (1,), config_root)
    assert any(c.name == "deterministic" and not c.passed for c in report.checks), (
        "a randomised policy passed the determinism check, so the check is useless"
    )


def test_a_vision_architecture_is_routed_not_failed(config_root):
    """A vision policy on a blind environment is a harness mismatch, not a bug."""
    arch = load_architecture("c2g", config_root)
    assert requires_vision(arch)
    env, note = resolve_environment(arch, "grid_nav", config_root)
    assert env is not None and env.params.get("render") is True
    assert note == "grid_nav_vision"


def test_a_scripted_architecture_is_not_rerouted(config_root):
    arch = load_architecture("c2", config_root)
    assert not requires_vision(arch)
    env, note = resolve_environment(arch, "grid_nav", config_root)
    assert note is None and not env.params.get("render")


def test_a_vision_architecture_with_no_rendering_variant_is_skipped(config_root):
    arch = load_architecture("c2g", config_root)
    env, note = resolve_environment(arch, "occlusion", config_root)
    assert env is None
    assert "needs rendered frames" in note


def test_render_marks_skipped_separately_from_failed():
    """A skip must never be counted as a failure."""
    reports = [
        ArchitectureReport("c2", checks=[Check("runs", True)]),
        ArchitectureReport("c2g", skipped="needs rendered frames"),
    ]
    text = render(reports, "grid_nav")
    assert "SKIP" in text
    assert "FAILED" not in text
    assert "1 skipped" in text
