"""Reproducibility manifest.

Every run persists enough to be re-created or, failing that, to be honestly
labelled.  The dirty-tree flag matters as much as the commit: a result produced
from uncommitted edits is not reproducible, and recording that fact is the
difference between a caveat and a false claim.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from uavlab.core.config import ArchitectureConfig, EnvironmentConfig


def _git(args: list[str], cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_state(repo: Path | None = None) -> dict[str, Any]:
    repo = repo or Path(__file__).resolve().parents[3]
    sha = _git(["rev-parse", "HEAD"], repo)
    status = _git(["status", "--porcelain"], repo)
    return {
        "git_sha": sha,
        "git_dirty": bool(status) if status is not None else None,
        "git_dirty_files": len(status.splitlines()) if status else 0,
        "git_branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
    }


def dependency_hash() -> str:
    """Hash of the installed distribution set, as a lockfile stand-in."""
    try:
        from importlib.metadata import distributions

        names = sorted(
            f"{d.metadata['Name']}=={d.version}"
            for d in distributions()
            if d.metadata and d.metadata.get("Name")
        )
    except Exception:  # noqa: BLE001 - never fail a run over provenance
        return "unknown"
    return hashlib.sha256("\n".join(names).encode()).hexdigest()[:16]


def build_manifest(
    arch: ArchitectureConfig,
    env: EnvironmentConfig,
    *,
    seeds: list[int],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": "uavlab/manifest/1",
        **git_state(),
        "architecture_id": arch.id,
        "architecture_config_hash": arch.config_hash(),
        "architecture_config": arch.model_dump(mode="json"),
        "environment_id": env.id,
        "environment_config": env.model_dump(mode="json"),
        "seeds": seeds,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor(),
        "dependency_hash": dependency_hash(),
        # Model and prompt identity live inside the inference plugin's params,
        # which are already captured in architecture_config above. When a real
        # backend replaces the simulated one, its checkpoint hash and prompt
        # template hash must be recorded there too.
        "container_image_digest": None,
    }
    if extra:
        manifest.update(extra)
    return manifest


def write_manifest(manifest: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path
