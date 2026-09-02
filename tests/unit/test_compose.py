"""Resolution invariants for coexisting normalized and paper profiles."""

from __future__ import annotations

from pathlib import Path

import pytest

from uavlab.core.compose import ComposeError, resolve_path


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_declared_id_wins_over_ambiguous_family_prefix(tmp_path: Path) -> None:
    normalized = tmp_path / "c2_vlm_waypoint.yaml"
    _write(normalized, "id: c2\n")
    _write(tmp_path / "c2_spf.yaml", "id: c2_spf\n")

    assert resolve_path("c2", tmp_path) == normalized.resolve()


def test_duplicate_declared_ids_fail_explicitly(tmp_path: Path) -> None:
    _write(tmp_path / "first.yaml", "id: duplicate\n")
    _write(tmp_path / "second.yaml", "id: duplicate\n")

    with pytest.raises(ComposeError, match=r"declared config id.*duplicated"):
        resolve_path("duplicate", tmp_path)
