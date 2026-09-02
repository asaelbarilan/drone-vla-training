"""Acceptance-gate semantics that must not drift silently."""

from scripts.verify_aerialclaw_gate import typed_signature


def test_typed_signature_keeps_order_and_skill_but_not_continuous_arguments() -> None:
    first = [
        {"kind": "skill", "skill": "goto", "args": {"x": 1.0}},
        {"kind": "skill", "skill": "stop", "args": {"reason": "arrived"}},
    ]
    equivalent = [
        {"kind": "skill", "skill": "goto", "args": {"x": 1.1}},
        {"kind": "skill", "skill": "stop", "args": {"reason": "completed"}},
    ]
    different_program = [
        {"kind": "skill", "skill": "scan", "args": {}},
        *equivalent,
    ]

    assert typed_signature(first) == typed_signature(equivalent)
    assert typed_signature(first) != typed_signature(different_program)
