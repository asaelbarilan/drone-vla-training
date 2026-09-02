"""YAML composition with inheritance.

Architectures are expressed as controlled *mutations* of one another — C3 is C2
plus a verifier, C8 is C7 plus a shield — so the config files inherit rather
than repeat.  That is not just brevity: when C7 and C8 share a base, it is
mechanically true that they use the same VLA, which is exactly what the C7/C8
contrast needs in order to isolate the safety boundary.

OmegaConf is used when installed (giving interpolation and the standard merge
semantics); otherwise an equivalent deep merge runs on plain PyYAML, so the
repository stays usable with no optional dependencies at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from uavlab.core.config import (
    ArchitectureConfig,
    EnvironmentConfig,
    ExperimentConfig,
)

try:  # pragma: no cover - exercised by whichever branch is installed
    from omegaconf import OmegaConf

    _HAVE_OMEGACONF = True
except ImportError:  # pragma: no cover
    OmegaConf = None  # type: ignore[assignment]
    _HAVE_OMEGACONF = False

BASE_KEY = "_base_"
MAX_INHERITANCE_DEPTH = 16


class ComposeError(ValueError):
    """Raised when a config file cannot be located or composed."""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base``.

    Mappings merge; every other type replaces.  Lists deliberately replace
    rather than concatenate — appending would make it impossible to *remove* a
    component in a derived config, and removing components is half of what the
    ablations do.
    """
    out = dict(base)
    for key, value in override.items():
        existing = out.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            out[key] = deep_merge(existing, value)
        else:
            out[key] = value
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ComposeError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ComposeError(f"{path} must contain a YAML mapping, got {type(data).__name__}")
    return data


def load_raw(path: str | Path, _depth: int = 0) -> dict[str, Any]:
    """Load a YAML file and resolve its ``_base_`` chain."""
    path = Path(path).resolve()
    if _depth > MAX_INHERITANCE_DEPTH:
        raise ComposeError(f"inheritance deeper than {MAX_INHERITANCE_DEPTH} at {path}; cycle?")

    data = _read_yaml(path)
    bases = data.pop(BASE_KEY, None)
    if bases is None:
        merged: dict[str, Any] = {}
    else:
        if isinstance(bases, str):
            bases = [bases]
        merged = {}
        for base in bases:
            base_path = (path.parent / base).resolve()
            merged = deep_merge(merged, load_raw(base_path, _depth + 1))

    merged = deep_merge(merged, data)

    if _HAVE_OMEGACONF and _depth == 0:
        # Resolve ``${...}`` interpolations once, at the top of the chain.
        merged = OmegaConf.to_container(OmegaConf.create(merged), resolve=True)  # type: ignore[assignment]
    return merged


def resolve_path(name_or_path: str | Path, search_dir: Path) -> Path:
    """Accept a declared config ID, filename stem, filename or full path.

    Declared IDs are checked before legacy family-prefix matching. This keeps
    ``c2`` stable when an additional paper profile such as ``c2_spf.yaml`` is
    installed beside the original ``c2_vlm_waypoint.yaml``.
    """
    candidate = Path(name_or_path)
    if candidate.is_file():
        return candidate.resolve()
    for suffix in ("", ".yaml", ".yml"):
        probe = search_dir / f"{name_or_path}{suffix}"
        if probe.is_file():
            return probe.resolve()
    declared_matches = sorted(
        path
        for path in search_dir.glob("*.y*ml")
        if _read_yaml(path).get("id") == str(name_or_path)
    )
    if len(declared_matches) == 1:
        return declared_matches[0].resolve()
    if len(declared_matches) > 1:
        names = ", ".join(path.name for path in declared_matches)
        raise ComposeError(
            f"declared config id {name_or_path!r} is duplicated in {search_dir}: {names}"
        )
    # Allow prefix matching so "c3" finds "c3_verifier.yaml".
    matches = sorted(
        p for p in search_dir.glob("*.y*ml") if p.stem.split("_", 1)[0] == str(name_or_path)
    )
    if len(matches) == 1:
        return matches[0].resolve()
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise ComposeError(f"{name_or_path!r} is ambiguous in {search_dir}: {names}")
    available = ", ".join(sorted(p.stem for p in search_dir.glob("*.y*ml"))) or "none"
    raise ComposeError(f"no config named {name_or_path!r} in {search_dir}. Available: {available}")


def default_config_root() -> Path:
    """Locate ``configs/`` relative to the installed package or the repo."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        probe = parent / "configs"
        if (probe / "architectures").is_dir():
            return probe
    raise ComposeError("could not locate a configs/ directory; pass --config-root explicitly")


def load_architecture(
    name_or_path: str | Path, config_root: Path | None = None
) -> ArchitectureConfig:
    root = config_root or default_config_root()
    path = resolve_path(name_or_path, root / "architectures")
    raw = load_raw(path)
    raw.setdefault("id", path.stem.split("_", 1)[0])
    return ArchitectureConfig.model_validate(raw)


def load_environment(
    name_or_path: str | Path, config_root: Path | None = None
) -> EnvironmentConfig:
    root = config_root or default_config_root()
    path = resolve_path(name_or_path, root / "environments")
    raw = load_raw(path)
    raw.setdefault("id", path.stem)
    return EnvironmentConfig.model_validate(raw)


def load_experiment(name_or_path: str | Path, config_root: Path | None = None) -> ExperimentConfig:
    root = config_root or default_config_root()
    path = resolve_path(name_or_path, root / "experiments")
    raw = load_raw(path)
    raw.setdefault("id", path.stem)
    return ExperimentConfig.model_validate(raw)


def list_architectures(config_root: Path | None = None) -> list[str]:
    root = config_root or default_config_root()
    return sorted(
        p.stem for p in (root / "architectures").glob("*.y*ml") if not p.name.startswith("_")
    )


def list_environments(config_root: Path | None = None) -> list[str]:
    root = config_root or default_config_root()
    return sorted(
        p.stem for p in (root / "environments").glob("*.y*ml") if not p.name.startswith("_")
    )


def list_experiments(config_root: Path | None = None) -> list[str]:
    root = config_root or default_config_root()
    return sorted(
        p.stem for p in (root / "experiments").glob("*.y*ml") if not p.name.startswith("_")
    )
