"""Architecture verification: is each configuration actually functioning?

"It ran without raising" is not the same as "it works", and this file exists
because that gap has already produced one wrong claim in this project. An
architecture can execute cleanly, produce a full metric vector, and still be
broken in ways that look like results:

* its distinguishing component never activates, so it is really its parent
  architecture wearing a different name;
* it never moves, so its metrics describe a stationary vehicle;
* it is not deterministic, so paired-by-seed comparison is invalid;
* its decisions are routed through the wrong authority path.

Each check below is one of those failure modes, expressed so that a failure
names the problem rather than just reporting a number.

The checks are derived from the *configuration* rather than a hardcoded table,
so a newly added architecture is covered the moment it exists.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from uavlab.core.compose import load_architecture, load_environment
from uavlab.core.config import ActionHorizon, ArchitectureConfig, Authority, EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.core.results import EpisodeResult

DETERMINISM_KEYS = ("distance_to_goal_m", "path_length_m", "decisions_proposed", "control_updates")


@dataclass(slots=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass(slots=True)
class ArchitectureReport:
    architecture_id: str
    checks: list[Check] = field(default_factory=list)
    results: list[EpisodeResult] = field(default_factory=list)
    skipped: str | None = None
    """Set when the architecture could not be run here at all, with the reason.

    Distinct from failure: an architecture needing a rendering environment is
    not broken, and scoring it as broken would be the same category error as
    scoring a teleported drone as a recovery failure."""
    environment_used: str = ""

    @property
    def ok(self) -> bool:
        return self.skipped is None and all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def mean(self, key: str) -> float:
        values = [r.metrics.get(key, 0.0) for r in self.results]
        return sum(values) / len(values) if values else 0.0


def _run(arch: ArchitectureConfig, env, seed: int) -> EpisodeResult:
    return asyncio.run(
        Orchestrator(arch, env, EpisodeSpec(episode_id=f"verify_{arch.id}_{seed}", seed=seed)).run()
    )


def _check_runs(results: list[EpisodeResult]) -> Check:
    errored = [r for r in results if r.error]
    return Check(
        "runs",
        not errored,
        "" if not errored else f"{len(errored)}/{len(results)} episodes raised: {errored[0].error[:90]}",
    )


def _check_moves(results: list[EpisodeResult]) -> Check:
    """A stationary vehicle still produces a full, entirely meaningless metric row."""
    mean_path = sum(r.metrics.get("path_length_m", 0.0) for r in results) / max(len(results), 1)
    return Check(
        "moves",
        mean_path > 5.0,
        "" if mean_path > 5.0 else f"mean path length {mean_path:.1f} m: the vehicle barely moved",
    )


def _check_makes_progress(results: list[EpisodeResult]) -> Check:
    """Ends closer to the goal than it started, on average.

    Weak by design. It is a smoke test for "this architecture is pointed at the
    task at all", not a success criterion - an architecture can legitimately
    fail the mission while still making headway.
    """
    closer = 0
    for r in results:
        start = r.status.shortest_path_m if r.status else 0.0
        if start > 0.0 and r.metrics.get("distance_to_goal_m", 1e9) < start:
            closer += 1
    ratio = closer / max(len(results), 1)
    return Check(
        "progress",
        ratio >= 0.5,
        "" if ratio >= 0.5 else f"ended closer to the goal in only {closer}/{len(results)} episodes",
    )


def _check_authority(arch: ArchitectureConfig, results: list[EpisodeResult]) -> Check:
    """Decisions were routed through the path the declared authority requires."""
    if arch.authority is Authority.WAYPOINT:
        key, what = "router_plans_requested", "no waypoint ever reached the planner"
    elif arch.authority is Authority.DIRECT_VLA:
        key, what = "router_chunk_actions_executed", "no learned action ever reached the controller"
    else:
        key, what = "decisions_executed", "no skill call was ever routed"
    total = sum(r.metrics.get(key, 0.0) for r in results)
    return Check(f"authority:{arch.authority.value}", total > 0, "" if total > 0 else what)


def _check_distinguishing_component(
    arch: ArchitectureConfig, results: list[EpisodeResult]
) -> list[Check]:
    """Each optional component present in the config must actually activate.

    This is the check that catches an architecture which is really its parent
    under another name - configured, launched, and experimentally inert.
    """
    checks: list[Check] = []

    if arch.verifier is not None:
        acted = sum(
            r.metrics.get("router_verifier_rejected", 0.0)
            + r.metrics.get("router_verifier_modified", 0.0)
            + r.metrics.get("router_plans_requested", 0.0)
            for r in results
        )
        checks.append(Check("verifier consulted", acted > 0, "" if acted > 0 else "verifier never saw a proposal"))

    if arch.monitor is not None:
        n = sum(r.metrics.get("monitor_assessments", 0.0) for r in results)
        checks.append(Check("monitor runs", n > 0, "" if n > 0 else "monitor was configured but never assessed"))

    if arch.recovery is not None:
        n = sum(
            r.metrics.get("recovery_decisions", 0.0) + r.metrics.get("reasoner_calls", 0.0)
            for r in results
        )
        checks.append(
            Check("reasoner runs", n > 0, "" if n > 0 else "reasoner was configured but never invoked")
        )

    if arch.shield is not None:
        # The shield must be *consulted* on every command. Interventions may
        # legitimately be zero in an open scene; never being asked may not.
        consulted = sum(
            r.metrics.get("router_safety_accept", 0.0)
            + r.metrics.get("router_safety_modify", 0.0)
            + r.metrics.get("router_safety_reject", 0.0)
            + r.metrics.get("router_safety_stop", 0.0)
            for r in results
        )
        issued = sum(r.metrics.get("router_commands_issued", 0.0) for r in results)
        ok = issued > 0 and consulted >= issued * 0.99
        checks.append(
            Check(
                "shield on every command",
                ok,
                "" if ok else f"shield saw {consulted:.0f} of {issued:.0f} commands",
            )
        )

    if arch.action_horizon is ActionHorizon.CHUNK:
        n = sum(r.metrics.get("router_chunk_actions_executed", 0.0) for r in results)
        checks.append(Check("chunks executed", n > 0, "" if n > 0 else "no chunk action executed"))

    if arch.semantic_memory.value != "no_memory":
        n = sum(r.metrics.get("decisions_proposed", 0.0) for r in results)
        checks.append(Check("memory wired", n > 0, "" if n > 0 else "no decision consumed memory"))

    return checks


def _check_determinism(arch: ArchitectureConfig, env, seed: int) -> Check:
    """Same seed, same episode. Paired-by-seed comparison depends on it."""
    a = _run(arch, env, seed)
    b = _run(arch, env, seed)
    diffs = [
        f"{k}: {a.metrics.get(k)} vs {b.metrics.get(k)}"
        for k in DETERMINISM_KEYS
        if abs(a.metrics.get(k, 0.0) - b.metrics.get(k, 0.0)) > 1e-6
    ]
    return Check("deterministic", not diffs, "; ".join(diffs[:2]))


def requires_vision(arch: ArchitectureConfig) -> bool:
    """Whether this architecture's policy needs rendered frames.

    Read from the plugin class, not from a list of names here, so a new vision
    policy is handled without editing this file.
    """
    from uavlab.core.registry import REGISTRY

    try:
        factory = REGISTRY._factories.get(("policy", arch.policy.name))
        if factory is None and REGISTRY.has("policy", arch.policy.name):
            REGISTRY.build("policy", arch.policy.name, {})  # triggers lazy import
            factory = REGISTRY._factories.get(("policy", arch.policy.name))
        return bool(getattr(factory, "requires_vision", False))
    except Exception:  # noqa: BLE001 - a policy that will not build fails elsewhere
        return False


def resolve_environment(arch: ArchitectureConfig, env_name: str, config_root: Path | None):
    """Pick an environment this architecture can actually run in.

    A vision policy on a non-rendering environment raises - correctly, since a
    blind vision policy would otherwise produce plausible numbers. But that is a
    harness mismatch, not a broken architecture, so route it to the rendering
    variant instead of reporting a false failure.
    """
    env = load_environment(env_name, config_root)
    if not requires_vision(arch) or env.params.get("render"):
        return env, None
    try:
        return load_environment(f"{env_name}_vision", config_root), f"{env_name}_vision"
    except Exception:  # noqa: BLE001
        return None, (
            f"needs rendered frames; {env_name} does not render and no "
            f"'{env_name}_vision' variant exists"
        )


def verify_architecture(
    name: str,
    env_name: str = "grid_nav",
    seeds: tuple[int, ...] = (1, 2, 3),
    config_root: Path | None = None,
    check_determinism: bool = True,
) -> ArchitectureReport:
    arch = load_architecture(name, config_root)
    env, note = resolve_environment(arch, env_name, config_root)
    if env is None:
        return ArchitectureReport(arch.id, checks=[], results=[], skipped=note)
    results = [_run(arch, env, s) for s in seeds]

    report = ArchitectureReport(arch.id, results=results, environment_used=note or env_name)
    report.checks.append(_check_runs(results))
    report.checks.append(_check_moves(results))
    report.checks.append(_check_makes_progress(results))
    report.checks.append(_check_authority(arch, results))
    report.checks.extend(_check_distinguishing_component(arch, results))
    if check_determinism:
        report.checks.append(_check_determinism(arch, env, seeds[0]))
    return report


def verify_all(
    names: list[str],
    env_name: str = "grid_nav",
    seeds: tuple[int, ...] = (1, 2, 3),
    config_root: Path | None = None,
    check_determinism: bool = True,
    progress: bool = True,
) -> list[ArchitectureReport]:
    reports = []
    for name in names:
        report = verify_architecture(name, env_name, seeds, config_root, check_determinism)
        reports.append(report)
        if progress:
            status = "SKIP" if report.skipped else ("PASS" if report.ok else "FAIL")
            extra = f"  ({report.environment_used})" if report.environment_used not in ("", env_name) else ""
            print(f"  {report.architecture_id:<5} {status}{extra}", flush=True)
    return reports


def render(reports: list[ArchitectureReport], env_name: str) -> str:
    lines = [f"\n=== Architecture verification on {env_name} ==="]
    header = f"{'arch':<6}{'verdict':<9}{'SR':>6}{'dist':>7}{'path':>8}{'coll':>6}  failures"
    lines.append(header)
    lines.append("-" * (len(header) + 20))
    for r in sorted(reports, key=lambda x: _sort_key(x.architecture_id)):
        if r.skipped:
            lines.append(f"{r.architecture_id:<6}{'SKIP':<9}{'':>6}{'':>7}{'':>8}{'':>6}  {r.skipped[:80]}")
            continue
        sr = sum(res.success for res in r.results) / max(len(r.results), 1)
        failures = "; ".join(f"{c.name}: {c.detail}" for c in r.failures) or "-"
        env_note = f" [{r.environment_used}]" if r.environment_used != env_name else ""
        lines.append(
            f"{r.architecture_id:<6}{'PASS' if r.ok else 'FAIL':<9}"
            f"{sr:>6.2f}{r.mean('distance_to_goal_m'):>7.1f}"
            f"{r.mean('path_length_m'):>8.1f}{r.mean('collision_rate'):>6.2f}  {(failures + env_note)[:80]}"
        )
    failed = [r.architecture_id for r in reports if not r.ok and not r.skipped]
    skipped = [r.architecture_id for r in reports if r.skipped]
    checked = len(reports) - len(skipped)
    lines.append("")
    if failed:
        lines.append(f"{len(failed)} of {checked} architectures FAILED: {', '.join(failed)}")
    else:
        lines.append(f"all {checked} architectures checked pass every structural check")
    if skipped:
        lines.append(f"{len(skipped)} skipped (could not run here): {', '.join(skipped)}")
    lines.append(
        "Note: these checks verify the architectures are FUNCTIONING, not that "
        "they are performing. Success rate is reported for information only."
    )
    return "\n".join(lines)


def _sort_key(arch_id: str) -> tuple[int, str]:
    digits = "".join(c for c in arch_id if c.isdigit())
    return (int(digits) if digits else 999, arch_id)
