"""The conditional architecture grammar.

Every test here is a configuration that *must not run*.  An incoherent
architecture that executes anyway produces a plausible number, and a plausible
number from an incoherent architecture is exactly the kind of result that
survives into a paper.
"""

from __future__ import annotations

import pytest

from uavlab.core.config import (
    ActionHorizon,
    ArchitectureConfig,
    Authority,
    ComponentSpec,
    ConfigError,
    MemoryMode,
    SchedulerKind,
    SchedulerSpec,
    Supervision,
)


def build(**overrides) -> ArchitectureConfig:
    base = {
        "id": "test",
        "authority": Authority.WAYPOINT,
        "policy": ComponentSpec(name="vlm_waypoint"),
        "planner": ComponentSpec(name="fixed_local"),
    }
    base.update(overrides)
    return ArchitectureConfig(**base)


def violations_of(**overrides) -> list[str]:
    with pytest.raises(ConfigError) as exc:
        build(**overrides)
    return exc.value.violations


def test_the_baseline_is_valid():
    assert build().authority is Authority.WAYPOINT


def test_action_chunk_with_skill_authority_is_rejected():
    """A skill call is not a learned action sequence."""
    text = " ".join(
        violations_of(
            authority=Authority.SKILL,
            policy=ComponentSpec(name="scripted_skill"),
            action_horizon=ActionHorizon.CHUNK,
            chunk_length=4,
        )
    )
    assert "action_horizon" in text and "skill" in text


def test_waypoint_authority_needs_a_downstream_conversion():
    text = " ".join(violations_of(planner=None))
    assert "no downstream conversion" in text


def test_planner_removal_is_allowed_when_declared_as_an_ablation():
    """OnFly's planner-removal experiment must remain expressible, but declared."""
    arch = build(planner=None, unsafe_ablation=True)
    assert arch.planner is None and arch.unsafe_ablation is True


def test_direct_vla_requires_an_action_horizon():
    text = " ".join(
        violations_of(
            authority=Authority.DIRECT_VLA,
            policy=ComponentSpec(name="mock_vla"),
            planner=None,
        )
    )
    assert "requires action_horizon" in text


def test_direct_vla_must_not_have_a_planner():
    """A VLA routed through a position planner is a waypoint architecture."""
    text = " ".join(
        violations_of(
            authority=Authority.DIRECT_VLA,
            action_horizon=ActionHorizon.SINGLE,
            policy=ComponentSpec(name="mock_vla"),
        )
    )
    assert "silently turn this into a waypoint architecture" in text


def test_chunk_length_must_match_the_action_horizon():
    assert "chunk_length >= 2" in " ".join(
        violations_of(
            authority=Authority.DIRECT_VLA,
            action_horizon=ActionHorizon.CHUNK,
            chunk_length=1,
            policy=ComponentSpec(name="chunk_vla"),
            planner=None,
        )
    )
    assert "chunk_length == 1" in " ".join(
        violations_of(
            authority=Authority.DIRECT_VLA,
            action_horizon=ActionHorizon.SINGLE,
            chunk_length=4,
            policy=ComponentSpec(name="mock_vla"),
            planner=None,
        )
    )


def test_monitor_frequency_without_a_monitor_is_rejected():
    text = " ".join(violations_of(scheduler=SchedulerSpec(monitor_hz=1.0)))
    assert "no monitor component exists" in text


def test_monitor_without_declared_supervision_is_rejected():
    text = " ".join(
        violations_of(
            monitor=ComponentSpec(name="progress"),
            scheduler=SchedulerSpec(monitor_hz=0.5),
        )
    )
    assert "semantic_supervision=none but monitor" in text


def test_memory_for_a_component_that_does_not_exist_is_rejected():
    text = " ".join(
        violations_of(
            semantic_memory=MemoryMode.SHORT_CONTEXT,
            memory=ComponentSpec(name="short_context"),
            memory_consumers=("policy", "monitor"),
        )
    )
    assert "no monitor component to consume it" in text


def test_declared_memory_must_match_the_wired_plugin():
    text = " ".join(violations_of(semantic_memory=MemoryMode.SHORT_CONTEXT))
    assert "no memory plugin is wired" in text
    text = " ".join(violations_of(memory=ComponentSpec(name="short_context")))
    assert "the declared architecture and the wired component disagree" in text


def test_async_supervision_requires_an_async_scheduler():
    """Otherwise the 'asynchronous' claim would be untestable."""
    text = " ".join(
        violations_of(
            semantic_supervision=Supervision.ASYNC_REASONER,
            recovery=ComponentSpec(name="hierarchical_reasoner"),
            scheduler=SchedulerSpec(kind=SchedulerKind.PERIODIC, reasoner_hz=0.5),
        )
    )
    assert "async_multi_rate or hybrid" in text


def test_triggered_supervision_requires_a_trigger():
    text = " ".join(
        violations_of(
            semantic_supervision=Supervision.TRIGGERED_REASONER,
            recovery=ComponentSpec(name="bounded_reasoner"),
            scheduler=SchedulerSpec(kind=SchedulerKind.EVENT_TRIGGERED),
        )
    )
    assert "requires a trigger name" in text


def test_control_rate_below_decision_rate_is_rejected():
    text = " ".join(violations_of(scheduler=SchedulerSpec(control_hz=1.0, decision_hz=5.0)))
    assert "below decision_hz" in text


def test_all_violations_are_reported_at_once():
    """Fixing configs one error at a time invites running a half-corrected one."""
    violations = violations_of(
        planner=None,
        scheduler=SchedulerSpec(control_hz=1.0, decision_hz=5.0, monitor_hz=2.0),
    )
    assert len(violations) >= 3


def test_config_hash_is_stable_and_sensitive():
    a, b = build(), build()
    assert a.config_hash() == b.config_hash()
    assert build(scheduler=SchedulerSpec(decision_hz=4.0)).config_hash() != a.config_hash()


def test_shipped_architectures_all_validate(arch_factory):
    """The fifteen configurations must load, not merely exist."""
    for i in range(15):
        arch = arch_factory(f"c{i}")
        assert arch.id == f"c{i}"
        assert arch.config_hash()
