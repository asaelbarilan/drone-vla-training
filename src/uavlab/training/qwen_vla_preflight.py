"""Strict, CPU-only audit and portable export for the historical Qwen dataset.

This does not certify the teacher's physical semantics or authorize training.
Historical files and architecture profiles are never edited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path, PureWindowsPath

from uavlab.plugins.reasoning.aerovla import parse_aerovla_output
from uavlab.training.qwen_vla_dataset import (
    _read_jsonl,
    action_json,
    qwen_record,
    swift_record,
)
from uavlab.training.splits import TRAIN_SEEDS

PILOT_EVALUATION_SEEDS = frozenset(range(1060, 1065))


def _image_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or PureWindowsPath(relative).is_absolute():
        raise ValueError("index image must be a relative path")
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError(f"image escapes dataset: {relative}")
    if not result.is_file():
        raise ValueError(f"missing image: {relative}")
    return result


def audit_dataset(root: Path) -> dict:
    """Reject corrupt/leaked data; report prompt and coverage blockers separately."""
    from PIL import Image

    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    index = _read_jsonl(root / "index.jsonl")
    if not index:
        raise ValueError("empty index")
    by_image = {}
    by_path = {}
    hashes = {}
    content_splits: dict[str, set[str]] = {}
    seeds = {"train": set(), "val": set()}
    terminals = {"train": set(), "val": set()}
    land_counts = Counter()
    action_counts = Counter()
    image_bytes = 0
    for row in index:
        relative, split, seed = row["image"], row["split"], row["seed"]
        if type(seed) is not int or seed not in TRAIN_SEEDS:
            raise ValueError(f"seed leakage: {seed}")
        if seed in PILOT_EVALUATION_SEEDS:
            raise ValueError(f"pilot evaluation seed in collection: {seed}")
        if split not in seeds:
            raise ValueError(f"unknown split: {split}")
        file = _image_path(root, relative)
        if relative in by_image or file in by_path:
            raise ValueError(f"duplicate index image: {relative}")
        with Image.open(file) as im:
            if im.size != (224, 224) or im.mode != "RGB":
                raise ValueError(f"expected 224x224 RGB: {relative}")
            im.verify()
        target = parse_aerovla_output(json.dumps(row["target"]))
        # Unlike the permissive native-text inference parser, training targets
        # must be JSON, and land must be an actual bool.
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        hashes[relative] = digest
        content_splits.setdefault(digest, set()).add(split)
        image_bytes += file.stat().st_size
        by_image[relative] = row
        by_path[file] = relative
        seeds[split].add(seed)
        action_counts[action_json(target)] += 1
        land_counts[split] += int(target.land)
        if target.land:
            terminals[split].add(seed)

    if not all(seeds.values()) or seeds["train"] & seeds["val"]:
        raise ValueError("empty or overlapping seed splits")
    prompt_mismatches = Counter()
    counts = {}
    for split in seeds:
        expected_images = {r["image"] for r in index if r["split"] == split}
        official = _read_jsonl(root / f"{split}.jsonl")
        swift = _read_jsonl(root / f"{split}_swift.jsonl")
        canonical = {}
        for row in official:
            relative = row["image"]
            if relative not in expected_images or relative in canonical:
                raise ValueError(f"duplicate, unknown or cross-split annotation: {relative}")
            item = by_image[relative]
            turns = row["conversations"]
            if len(turns) != 2 or turns[0].get("from") != "human":
                raise ValueError(f"invalid conversation: {relative}")
            if turns[1].get("from") != "gpt":
                raise ValueError(f"invalid assistant: {relative}")
            if turns[0]["value"].count("<image>") != 1:
                raise ValueError(f"invalid image-token count: {relative}")
            target = parse_aerovla_output(json.dumps(item["target"]))
            parse_aerovla_output(turns[1]["value"])
            if json.loads(turns[1]["value"]) != json.loads(action_json(target)):
                raise ValueError(f"target differs from index: {relative}")
            expected = qwen_record(
                relative, manifest["instruction"], item["coarse_goal_direction"], target
            )
            prompt_mismatches[split] += int(turns[0] != expected["conversations"][0])
            canonical[relative] = row
        if set(canonical) != expected_images:
            raise ValueError(f"incomplete official coverage: {split}")
        seen = set()
        for row in swift:
            images = row["images"]
            if len(images) != 1 or not isinstance(images[0], str):
                raise ValueError("invalid ms-swift images")
            file = Path(images[0])
            if not file.is_absolute():
                if PureWindowsPath(images[0]).is_absolute():
                    raise ValueError("Windows ms-swift path on another OS; export before transfer")
                if manifest.get("swift_image_root") != "dataset":
                    raise ValueError("relative ms-swift path requires explicit dataset root")
                file = root / file
            relative = by_path.get(file.resolve())
            if relative not in expected_images or relative in seen:
                raise ValueError("duplicate, unknown or cross-split ms-swift image")
            seen.add(relative)
            turns = canonical[relative]["conversations"]
            expected_messages = [
                {"role": "user", "content": turns[0]["value"]},
                {"role": "assistant", "content": turns[1]["value"]},
            ]
            if row["messages"] != expected_messages:
                raise ValueError(f"ms-swift prompt/target differs: {relative}")
        if seen != expected_images:
            raise ValueError(f"incomplete ms-swift coverage: {split}")
        counts[split] = len(expected_images)
    for field, count in [
        ("samples", len(index)), ("train_samples", counts["train"]),
        ("validation_samples", counts["val"]),
        ("episodes_kept", len(seeds["train"] | seeds["val"])),
    ]:
        if manifest.get(field) != count:
            raise ValueError(f"manifest {field} differs from index")

    blockers = []
    if sum(prompt_mismatches.values()):
        blockers.append("saved_prompt_differs_from_current_deployment")
    if len(index) < 10000:
        blockers.append("below_original_10000_sample_gate")
    if sum(map(len, seeds.values())) < 100:
        blockers.append("below_original_100_episode_gate")
    if any(terminals[s] != seeds[s] for s in seeds):
        blockers.append("successful_episodes_missing_terminal_labels")
    largest_fraction = max(action_counts.values()) / len(index)
    if largest_fraction > 0.5:
        blockers.append("modal_action_above_50_percent")
    blockers.extend([
        "teacher_action_execution_equivalence_not_certified",
        "terminal_label_observability_not_certified",
        "single_instruction_single_simulator_domain",
    ])
    return {
        "structurally_valid": True, "training_ready": False,
        "samples": len(index), "samples_by_split": counts,
        "seeds": {s: sorted(v) for s, v in seeds.items()},
        "land_samples": dict(land_counts),
        "episodes_missing_land": {s: sorted(seeds[s] - terminals[s]) for s in seeds},
        "prompt_mismatches": dict(prompt_mismatches),
        "unique_actions": len(action_counts), "largest_action_fraction": largest_fraction,
        "identical_image_hashes_across_splits": sum(len(s) > 1 for s in content_splits.values()),
        "image_bytes": image_bytes, "image_sha256": hashes, "blockers": blockers,
        "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
    }


def export_portable(source: Path, destination: Path, *, refresh_prompts: bool = False) -> dict:
    """Copy only audited dataset files; use paths relative to dataset working directory.

    Refreshing prompts is explicit and recorded. It never changes action labels
    or clears the physical/observability gates.
    """
    report = audit_dataset(source)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.mkdir(parents=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    index = _read_jsonl(source / "index.jsonl")
    by_image = {r["image"]: r for r in index}
    for relative in by_image:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    shutil.copyfile(source / "index.jsonl", destination / "index.jsonl")
    for split in ("train", "val"):
        rows = _read_jsonl(source / f"{split}.jsonl")
        native = []
        for i, row in enumerate(rows):
            item = by_image[row["image"]]
            target = parse_aerovla_output(json.dumps(item["target"]))
            if refresh_prompts:
                row = qwen_record(
                    row["image"], manifest["instruction"], item["coarse_goal_direction"], target
                )
                rows[i] = row
            swift = swift_record(
                row["image"], manifest["instruction"], item["coarse_goal_direction"], target
            )
            swift["messages"][0]["content"] = row["conversations"][0]["value"]
            native.append(swift)
        for name, values in [(split, rows), (f"{split}_swift", native)]:
            (destination / f"{name}.jsonl").write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in values), encoding="utf-8"
            )
    manifest.update({
        "swift_image_root": "dataset",
        "export_source_manifest_sha256": report["manifest_sha256"],
        "prompts_refreshed": refresh_prompts,
        "training_ready": False,
        "export_note": "Run trainer with dataset directory as cwd; labels remain uncertified.",
    })
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    result = audit_dataset(destination)
    if result["image_sha256"] != report["image_sha256"]:
        raise ValueError("export image content changed")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--refresh-prompts", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.refresh_prompts and not args.export:
        parser.error("--refresh-prompts requires --export")
    result = (
        export_portable(args.source, args.export, refresh_prompts=args.refresh_prompts)
        if args.export else audit_dataset(args.source)
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "image_sha256"}, indent=2))


if __name__ == "__main__":
    main()
