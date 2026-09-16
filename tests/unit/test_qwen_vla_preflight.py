from __future__ import annotations

import json
import shutil

import pytest
from PIL import Image

from uavlab.plugins.reasoning.aerovla import AeroVLAOutput
from uavlab.training.qwen_vla_dataset import action_json, qwen_record, swift_record
from uavlab.training.qwen_vla_preflight import audit_dataset, export_portable


def write_rows(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / "source"
    (root / "images").mkdir(parents=True)
    index = []
    for split, seed in [("train", 1201), ("train", 1202), ("val", 1200)]:
        relative = f"images/s{seed}.jpg"
        Image.new("RGB", (224, 224), (seed % 255, 50, 70)).save(root / relative)
        target = AeroVLAOutput(0, 49, 49, True)
        index.append({"image": relative, "split": split, "seed": seed,
                      "target": json.loads(action_json(target)),
                      "coarse_goal_direction": "straight ahead"})
    write_rows(root / "index.jsonl", index)
    manifest = {"samples": 3, "train_samples": 2, "validation_samples": 1,
                "episodes_kept": 3, "instruction": "fly to the red tower and stop there"}
    (root / "manifest.json").write_text(json.dumps(manifest))
    for split in ("train", "val"):
        items = [r for r in index if r["split"] == split]
        write_rows(root / f"{split}.jsonl", [
            qwen_record(r["image"], manifest["instruction"], r["coarse_goal_direction"], target)
            for r in items
        ])
        write_rows(root / f"{split}_swift.jsonl", [
            swift_record(str((root / r["image"]).resolve()), manifest["instruction"],
                         r["coarse_goal_direction"], target) for r in items
        ])
    return root


def edit_rows(path, mutation):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    mutation(rows)
    write_rows(path, rows)


def test_portable_export_survives_relocation_without_changing_source(dataset, tmp_path):
    original = {p.relative_to(dataset): p.read_bytes() for p in dataset.rglob("*") if p.is_file()}
    expected = audit_dataset(dataset)
    dest = tmp_path / "export"
    export_portable(dataset, dest)
    moved = tmp_path / "moved"
    shutil.copytree(dest, moved)
    actual = audit_dataset(moved)
    assert actual["image_sha256"] == expected["image_sha256"]
    assert actual["seeds"] == expected["seeds"]
    assert not actual["training_ready"]  # file correctness is not control correctness
    assert original == {p.relative_to(dataset): p.read_bytes()
                        for p in dataset.rglob("*") if p.is_file()}
    with pytest.raises(FileExistsError):
        export_portable(dataset, dest)


def test_duplicate_swift_row_cannot_hide_missing_sample(dataset):
    edit_rows(dataset / "train_swift.jsonl", lambda r: r.__setitem__(1, r[0]))
    with pytest.raises(ValueError, match="duplicate"):
        audit_dataset(dataset)


def test_swift_prompt_mismatch_rejected(dataset):
    def corrupt(rows):
        rows[0]["messages"][0]["content"] += " extra oracle information"
    edit_rows(dataset / "train_swift.jsonl", corrupt)
    with pytest.raises(ValueError, match="prompt/target differs"):
        audit_dataset(dataset)


@pytest.mark.parametrize("seed", [1, 40, 1060, 1064, 999, 2000, True])
def test_forbidden_seed_rejected(dataset, seed):
    edit_rows(dataset / "index.jsonl", lambda rows: rows[0].__setitem__("seed", seed))
    with pytest.raises(ValueError, match="seed"):
        audit_dataset(dataset)


def test_corrupt_image_rejected(dataset):
    (dataset / "images/s1201.jpg").write_bytes(b"broken image")
    with pytest.raises(OSError):
        audit_dataset(dataset)


def test_path_escape_rejected(dataset):
    edit_rows(dataset / "index.jsonl", lambda rows: rows[0].__setitem__("image", "../escape.jpg"))
    with pytest.raises(ValueError, match="escapes"):
        audit_dataset(dataset)


def test_stale_prompt_requires_explicit_refresh_and_keeps_labels(dataset, tmp_path):
    def old_official(rows):
        rows[0]["conversations"][0]["value"] = "<image>\nold prompt"
    def old_swift(rows):
        rows[0]["messages"][0]["content"] = "<image>\nold prompt"
    edit_rows(dataset / "train.jsonl", old_official)
    edit_rows(dataset / "train_swift.jsonl", old_swift)
    assert audit_dataset(dataset)["prompt_mismatches"]["train"] == 1
    stale = export_portable(dataset, tmp_path / "stale")
    assert stale["prompt_mismatches"]["train"] == 1
    fixed = export_portable(dataset, tmp_path / "fixed", refresh_prompts=True)
    assert fixed["prompt_mismatches"]["train"] == 0
    assert (dataset / "index.jsonl").read_bytes() == (tmp_path / "fixed/index.jsonl").read_bytes()
    assert not fixed["training_ready"]


def test_manifest_count_mismatch_rejected(dataset):
    path = dataset / "manifest.json"
    value = json.loads(path.read_text())
    value["samples"] = 99
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="manifest samples"):
        audit_dataset(dataset)


def test_assistant_boolean_cannot_impersonate_integer_bin(dataset):
    def corrupt(rows):
        value = json.loads(rows[0]["conversations"][1]["value"])
        value["forward_bin"] = False  # equality alone would accept False == 0
        rows[0]["conversations"][1]["value"] = json.dumps(value)
    edit_rows(dataset / "train.jsonl", corrupt)
    with pytest.raises(RuntimeError, match="integer"):
        audit_dataset(dataset)
