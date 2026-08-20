"""Command line interface.

    uavlab run       --arch c3 --env grid_nav --seed 7
    uavlab sweep     --experiment macro_screen
    uavlab replay    RUN_DIR
    uavlab analyze   RUN_DIR [RUN_DIR ...]
    uavlab validate-config CONFIG
    uavlab list

``validate-config`` is the one to reach for first when a config looks wrong: it
reports *every* grammar violation at once rather than the first, because a
half-corrected architecture is easy to run by mistake.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from uavlab.analysis.report import render_pareto, render_table, summarise
from uavlab.core.compose import (
    ComposeError,
    default_config_root,
    list_architectures,
    list_environments,
    list_experiments,
    load_architecture,
    load_environment,
    load_experiment,
    load_raw,
)
from uavlab.core.config import ArchitectureConfig, ConfigError, EpisodeSpec
from uavlab.core.orchestrator import Orchestrator
from uavlab.core.registry import CATEGORIES, REGISTRY
from uavlab.core.results import EpisodeResult
from uavlab.experiments.manifest import build_manifest, write_manifest
from uavlab.experiments.sweep import run_sweep
from uavlab.experiments.verify import render as render_verify
from uavlab.experiments.verify import verify_all

EXIT_OK = 0
EXIT_BAD_CONFIG = 2
EXIT_EPISODE_FAILED = 3


def _config_root(args: argparse.Namespace) -> Path | None:
    return Path(args.config_root) if getattr(args, "config_root", None) else None


# -- run --------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    root = _config_root(args)
    arch = load_architecture(args.arch, root)
    env = load_environment(args.env, root)
    out_dir = Path(args.out) if args.out else Path("runs") / f"{arch.id}__{env.id}__s{args.seed}"

    write_manifest(build_manifest(arch, env, seeds=[args.seed]), out_dir)

    orchestrator = Orchestrator(
        arch, env, EpisodeSpec(episode_id=out_dir.name, seed=args.seed), out_dir=out_dir
    )
    result = asyncio.run(orchestrator.run())
    (out_dir / "result.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2), encoding="utf-8"
    )

    print(f"architecture : {arch.id}  ({arch.name})")
    print(f"environment  : {env.id}  ({env.task_family.value})")
    print(f"authority    : {arch.authority.value}   supervision: {arch.semantic_supervision.value}")
    print(f"memory       : {arch.semantic_memory.value}   scheduler: {arch.scheduler.kind.value}")
    print(f"success      : {result.success}")
    print(f"termination  : {result.termination_reason.value} ({result.termination_detail})")
    print(f"sim time     : {result.sim_duration_s:.1f}s   wall: {result.wall_duration_s:.2f}s")
    if result.error:
        print(f"error        : {result.error}")
    print("\nmetrics:")
    for key in sorted(result.metrics):
        if key.startswith("router_") and args.verbose is False:
            continue
        print(f"  {key:<38} {result.metrics[key]:>12.4f}")
    print(f"\nartifacts: {out_dir}")
    return EXIT_OK if result.error is None else EXIT_EPISODE_FAILED


# -- sweep ------------------------------------------------------------------


def cmd_sweep(args: argparse.Namespace) -> int:
    root = _config_root(args)
    experiment = load_experiment(args.experiment, root)
    if args.seeds:
        experiment = experiment.model_copy(update={"seeds": tuple(args.seeds)})

    outcome = asyncio.run(
        run_sweep(
            experiment,
            config_root=root,
            out_dir=Path(args.out) if args.out else None,
            keep_episode_logs=args.keep_logs,
        )
    )
    print(render_table(outcome.cells))
    print(render_pareto(outcome.cells))
    if outcome.comparisons:
        print("\n=== Paired contrasts (by seed) ===")
        for c in outcome.comparisons:
            marker = "*" if c["significant"] else " "
            print(f" {marker} [{c['environment']}] {c['description']}")
        print("\n * = 95% bootstrap CI excludes zero.")
    if outcome.failures:
        print(f"\n{len(outcome.failures)} episode(s) errored:")
        for arch, env, seed, err in outcome.failures[:10]:
            print(f"  {arch} / {env} / seed {seed}: {err[:160]}")
    print(f"\nreport: {outcome.out_dir}")
    return EXIT_EPISODE_FAILED if outcome.failures else EXIT_OK


# -- replay -----------------------------------------------------------------


def cmd_replay(args: argparse.Namespace) -> int:
    """Re-run an episode from its manifest and check the result still matches."""
    run_dir = Path(args.run_dir)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"no manifest.json in {run_dir}", file=sys.stderr)
        return EXIT_BAD_CONFIG
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    arch = ArchitectureConfig.model_validate(manifest["architecture_config"])
    from uavlab.core.config import EnvironmentConfig

    env = EnvironmentConfig.model_validate(manifest["environment_config"])
    seed = int(manifest["seeds"][0])

    if manifest.get("git_dirty"):
        print(
            "warning: the original run was produced from a dirty working tree, "
            "so an exact replay is not guaranteed",
            file=sys.stderr,
        )

    orchestrator = Orchestrator(arch, env, EpisodeSpec(episode_id=f"replay_{run_dir.name}", seed=seed))
    result = asyncio.run(orchestrator.run())
    print(f"replayed {run_dir.name}: success={result.success} "
          f"{result.termination_reason.value} sim={result.sim_duration_s:.1f}s")

    original_path = run_dir / "result.json"
    if original_path.is_file():
        original = json.loads(original_path.read_text(encoding="utf-8"))
        drift = {
            key: (original["metrics"].get(key), result.metrics.get(key))
            for key in ("distance_to_goal_m", "flight_time_s", "collisions")
            if abs(float(original["metrics"].get(key, 0.0)) - result.metrics.get(key, 0.0)) > 1e-6
        }
        if drift:
            print("determinism drift detected:")
            for key, (was, now) in drift.items():
                print(f"  {key}: was {was}, now {now}")
            return EXIT_EPISODE_FAILED
        print("deterministic: metrics match the original run")
    return EXIT_OK


# -- analyze ----------------------------------------------------------------


def cmd_analyze(args: argparse.Namespace) -> int:
    results: list[EpisodeResult] = []
    for run_dir in args.run_dirs:
        for path in sorted(Path(run_dir).rglob("result.json")):
            results.append(EpisodeResult.model_validate_json(path.read_text(encoding="utf-8")))
    if not results:
        print("no result.json files found under the given directories", file=sys.stderr)
        return EXIT_BAD_CONFIG
    cells = summarise(results)
    print(render_table(cells))
    print(render_pareto(cells))
    print(f"\n{len(results)} episodes across {len(cells)} architecture/environment cells.")
    return EXIT_OK


# -- validate ---------------------------------------------------------------


def cmd_validate(args: argparse.Namespace) -> int:
    root = _config_root(args)
    targets = args.configs or list_architectures(root)
    failed = 0
    for target in targets:
        try:
            path = Path(target)
            if path.is_file():
                raw = load_raw(path)
                raw.setdefault("id", path.stem.split("_", 1)[0])
                arch = ArchitectureConfig.model_validate(raw)
            else:
                arch = load_architecture(target, root)
        except ConfigError as exc:
            failed += 1
            print(f"[INVALID] {target}")
            for violation in exc.violations:
                print(f"    - {violation}")
            continue
        except (ComposeError, ValueError) as exc:
            failed += 1
            print(f"[INVALID] {target}\n    - {exc}")
            continue
        missing = _missing_plugins(arch)
        if missing:
            failed += 1
            print(f"[INVALID] {target}")
            for m in missing:
                print(f"    - {m}")
            continue
        print(
            f"[  OK   ] {arch.id:<5} authority={arch.authority.value:<11} "
            f"supervision={arch.semantic_supervision.value:<19} "
            f"memory={arch.semantic_memory.value:<24} hash={arch.config_hash()}"
        )
    if failed:
        print(f"\n{failed} of {len(targets)} configuration(s) invalid.")
    return EXIT_BAD_CONFIG if failed else EXIT_OK


def _missing_plugins(arch: ArchitectureConfig) -> list[str]:
    """Catch a config that names a plugin nobody registered."""
    wanted = [
        ("perception", arch.perception.name),
        ("memory", arch.memory.name),
        ("policy", arch.policy.name),
        ("controller", arch.controller.name),
        ("inference", arch.inference.name),
    ]
    for category, spec in (
        ("verifier", arch.verifier),
        ("planner", arch.planner),
        ("shield", arch.shield),
        ("monitor", arch.monitor),
        ("recovery", arch.recovery),
    ):
        if spec is not None:
            wanted.append((category, spec.name))
    return [
        f"no plugin registered as {category}/{name} "
        f"(available: {', '.join(REGISTRY.names(category)) or 'none'})"
        for category, name in wanted
        if not REGISTRY.has(category, name)
    ]


# -- collect / train --------------------------------------------------------


def cmd_collect(args: argparse.Namespace) -> int:
    """Generate an expert dataset by flying the oracle with the camera on."""
    from uavlab.training.dataset import collect

    manifest = collect(
        Path(args.out),
        episodes=args.episodes,
        env_name=args.env,
        expert=args.expert,
        stride=args.stride,
        config_root=_config_root(args),
    )
    print()
    print(f"kept {manifest['episodes_kept']}/{manifest['episodes_requested']} episodes "
          f"({manifest['episodes_skipped_as_failures']} skipped as failures)")
    print(f"samples          : {manifest['samples']:,}")
    print(f"terminal ticks   : {manifest['terminate_positive_rate']:.1%}")
    print(f"on disk          : {manifest['frames_bytes'] / 1e9:.2f} GB")
    error = manifest["codec_error"]
    print(f"quantisation floor: {error['velocity_error_mean_mps']:.4f} m/s mean "
          f"({manifest['codec']['bins']} bins/dim) - no policy can beat this")
    print(f"\ndataset: {args.out}")
    return EXIT_OK


def cmd_families(args: argparse.Namespace) -> int:
    """Show the design space: seven families, one base each, the rest ablations."""
    from uavlab.core.config import Family, validate_family_set

    root = _config_root(args)
    archs = [load_architecture(n, root) for n in sorted(list_architectures(root))]
    by_id = {a.id: a for a in archs}

    for family in Family:
        members = [a for a in archs if a.family is family]
        base = next((a for a in members if a.ablation_of is None), None)
        print(f"\n{family.value}")
        if base is not None:
            print(f"  BASE  {base.id:<5} {base.name}")
        for arch in sorted((a for a in members if a.ablation_of), key=lambda a: a.id):
            parent = by_id.get(arch.ablation_of)
            print(f"        {arch.id:<5} {arch.name}")
            print(f"              ablation of {parent.id if parent else arch.ablation_of}")

    problems = validate_family_set(archs)
    if problems:
        print("\nSTRUCTURE VIOLATIONS:")
        for problem in problems:
            print(f"  {problem}")
        return EXIT_BAD_CONFIG
    print(f"\n{len(Family)} families, {len(archs)} configurations, structure valid.")
    return EXIT_OK


def cmd_video(args: argparse.Namespace) -> int:
    """Render one episode per architecture so the runs can be judged by eye."""
    import json as _json

    from uavlab.analysis.replay_video import render
    from uavlab.experiments.verify import resolve_environment

    root = _config_root(args)
    names = args.architectures or sorted(
        {n.split("_", 1)[0] for n in list_architectures(root)}
    )
    out_dir = Path(args.out)
    summaries = []
    for name in names:
        arch = load_architecture(name, root)
        # resolve_environment hands back the *config*, plus a note naming the
        # substitute when a vision policy had to be routed to a rendering variant.
        env, note = resolve_environment(arch, args.env, root)
        if env is None:
            print(f"  {name:<5} SKIP  ({note})")
            continue
        if args.render and not env.params.get("render"):
            # Every vehicle has a camera; the scored environments simply do not
            # pay to render frames no policy reads. Measured on c0/c4/c9/c13,
            # turning rendering on leaves the trajectory bit-identical, so the
            # video shows the same episode that was scored - now with the view.
            env = env.model_copy(
                update={"params": {**env.params, "render": True, "image_size": 224}}
            )
        summary = render(arch, env, args.seed, out_dir / f"{name}.mp4",
                         fps=args.fps, stride=args.stride)
        summary["environment"] = env.id
        summaries.append(summary)
        print(f"  {name:<5} {'SUCCESS' if summary['success'] else 'FAILED ':<8} "
              f"{summary['termination']:<14} d={summary['distance_to_goal_m']:6.1f}m  "
              f"path={summary['path_length_m']:6.1f}m  -> {summary['video']}", flush=True)

    (out_dir / "index.json").write_text(_json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"\n{len(summaries)} videos in {out_dir}")
    return EXIT_OK


def cmd_dagger(args: argparse.Namespace) -> int:
    """Roll the trained student out and label its states with the teacher."""
    from uavlab.training.dagger import aggregate

    manifest = aggregate(
        Path(args.base),
        Path(args.out),
        Path(args.checkpoint),
        episodes=args.episodes,
        env_name=args.env,
        teacher=args.teacher,
        stride=args.stride,
        start_seed=args.start_seed,
        beta=args.beta,
        device=args.device,
        config_root=_config_root(args),
    )
    print()
    print(f"rollouts         : {manifest['dagger_rollouts']} at beta={manifest['beta']} "
          f"({manifest['dagger_rollout_successes']} reached the goal)")
    print(f"new samples      : {manifest['dagger_samples']:,}")
    print(f"total samples    : {manifest['samples']:,} "
          f"(base {manifest['base_samples']:,})")
    print(f"terminal ticks   : {manifest['terminate_positive_rate']:.1%}")
    print(f"on disk          : {manifest['frames_bytes'] / 1e9:.2f} GB")
    print(f"\ndataset: {args.out}")
    return EXIT_OK


def cmd_train(args: argparse.Namespace) -> int:
    """Behaviour-clone a visuomotor policy from the expert dataset."""
    from uavlab.training.train import TrainConfig, train

    summary = train(
        Path(args.data),
        Path(args.out),
        TrainConfig(epochs=args.epochs, batch_size=args.batch_size, seed=args.seed),
    )
    best = summary["best"]
    print(f"\nparameters   : {summary['parameters']:,}")
    print(f"trained in   : {summary['wall_seconds']:.0f}s over {summary['epochs_run']} epochs")
    print(f"bin accuracy : {best.get('bin_accuracy', 0):.3f}")
    print(f"velocity err : {best.get('velocity_error_mean_mps', 0):.3f} m/s "
          f"(floor {summary['quantisation_floor']['velocity_error_mean_mps']:.3f})")
    print(f"stop recall  : {best.get('terminate_recall', 0):.2f}  "
          f"precision {best.get('terminate_precision', 0):.2f}")
    print(f"\ncheckpoint: {summary['checkpoint']}")
    print("Now fly it:  uavlab run --arch c7t --env grid_nav_vision --seed 1")
    return EXIT_OK


# -- verify -----------------------------------------------------------------


def cmd_verify(args: argparse.Namespace) -> int:
    """Check that every architecture is *functioning*, not that it performs.

    Distinct from `validate-config`, which only checks that a configuration is
    legal. This launches each architecture and asserts it moves, makes headway,
    routes decisions through the authority it declares, activates every
    component it configures, and reproduces exactly on a repeated seed.
    """
    root = _config_root(args)
    names = args.architectures or list_architectures(root)
    seeds = tuple(args.seeds) if args.seeds else (1, 2, 3)
    print(f"verifying {len(names)} architectures on {args.env} across seeds {list(seeds)}")
    reports = verify_all(
        names,
        env_name=args.env,
        seeds=seeds,
        config_root=root,
        check_determinism=not args.skip_determinism,
    )
    print(render_verify(reports, args.env))
    return EXIT_EPISODE_FAILED if any(not r.ok for r in reports) else EXIT_OK


# -- list -------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    root = _config_root(args)
    try:
        print(f"config root: {root or default_config_root()}\n")
        print("architectures:", ", ".join(list_architectures(root)))
        print("environments :", ", ".join(list_environments(root)))
        print("experiments  :", ", ".join(list_experiments(root)))
    except ComposeError as exc:
        print(exc, file=sys.stderr)
        return EXIT_BAD_CONFIG
    print("\nregistered plugins:")
    for category in CATEGORIES:
        names = REGISTRY.names(category)
        if names:
            print(f"  {category:<12} {', '.join(names)}")
    return EXIT_OK


# -- entry point ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="uavlab", description=__doc__.split("\n")[0])
    parser.add_argument("--config-root", help="directory containing architectures/, environments/")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one episode")
    run.add_argument("--arch", required=True)
    run.add_argument("--env", required=True)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--out")
    run.add_argument("--verbose", action="store_true", default=False)
    run.set_defaults(func=cmd_run)

    sweep = sub.add_parser("sweep", help="run a staged experiment")
    sweep.add_argument("--experiment", required=True)
    sweep.add_argument("--seeds", type=int, nargs="*")
    sweep.add_argument("--out")
    sweep.add_argument("--keep-logs", action="store_true")
    sweep.set_defaults(func=cmd_sweep)

    replay = sub.add_parser("replay", help="re-run a stored run and check determinism")
    replay.add_argument("run_dir")
    replay.set_defaults(func=cmd_replay)

    analyze = sub.add_parser("analyze", help="aggregate stored runs")
    analyze.add_argument("run_dirs", nargs="+")
    analyze.set_defaults(func=cmd_analyze)

    validate = sub.add_parser("validate-config", help="check architecture configs")
    validate.add_argument("configs", nargs="*")
    validate.set_defaults(func=cmd_validate)

    collect = sub.add_parser("collect", help="generate an expert dataset from the oracle")
    collect.add_argument("--episodes", type=int, default=200)
    collect.add_argument("--env", default="grid_nav_vision")
    collect.add_argument("--expert", default="c0")
    collect.add_argument("--stride", type=int, default=2)
    collect.add_argument("--out", default="data/expert_grid_nav")
    collect.set_defaults(func=cmd_collect)

    fam = sub.add_parser("families", help="show the seven families and their ablations")
    fam.set_defaults(func=cmd_families)

    vid = sub.add_parser("video", help="render an episode per architecture as mp4")
    vid.add_argument("architectures", nargs="*")
    vid.add_argument("--env", default="grid_nav")
    vid.add_argument("--seed", type=int, default=3)
    vid.add_argument("--out", default="reports/videos")
    vid.add_argument("--fps", type=int, default=15)
    vid.add_argument("--stride", type=int, default=4,
                     help="sample every Nth control tick")
    vid.add_argument("--no-render", dest="render", action="store_false",
                     help="leave the camera panel empty for non-vision configurations")
    vid.set_defaults(render=True)
    vid.set_defaults(func=cmd_video)

    dag = sub.add_parser("dagger", help="add teacher labels at states the student visits")
    dag.add_argument("--base", default="data/expert_c2_grid_nav",
                     help="dataset to append to")
    dag.add_argument("--checkpoint", default="models/bc_c2_grid_nav.pt",
                     help="student that drives the rollouts")
    dag.add_argument("--out", default="data/dagger_c2_grid_nav")
    dag.add_argument("--episodes", type=int, default=120)
    dag.add_argument("--env", default="grid_nav_vision")
    dag.add_argument("--teacher", default="c2")
    dag.add_argument("--stride", type=int, default=2)
    dag.add_argument("--start-seed", type=int, default=1300)
    dag.add_argument("--beta", type=float, default=0.5,
                     help="probability of executing the TEACHER's command on a tick")
    dag.add_argument("--device", default="cpu")
    dag.set_defaults(func=cmd_dagger)

    train_p = sub.add_parser("train", help="behaviour-clone a policy from expert data")
    train_p.add_argument("--data", default="data/expert_grid_nav")
    train_p.add_argument("--out", default="models/bc_grid_nav.pt")
    train_p.add_argument("--epochs", type=int, default=12)
    train_p.add_argument("--batch-size", type=int, default=128)
    train_p.add_argument("--seed", type=int, default=0)
    train_p.set_defaults(func=cmd_train)

    verify = sub.add_parser("verify", help="check every architecture actually functions")
    verify.add_argument("architectures", nargs="*")
    verify.add_argument("--env", default="grid_nav")
    verify.add_argument("--seeds", type=int, nargs="*")
    verify.add_argument("--skip-determinism", action="store_true",
                        help="skip the repeated-seed check (halves runtime)")
    verify.set_defaults(func=cmd_verify)

    listing = sub.add_parser("list", help="show available configs and plugins")
    listing.set_defaults(func=cmd_list)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_BAD_CONFIG
    except ComposeError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return EXIT_BAD_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
