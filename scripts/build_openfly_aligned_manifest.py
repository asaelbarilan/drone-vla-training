"""Create a separate motion-verified macro manifest; preserve every old split/file."""

import hashlib
import json

import pyarrow.parquet as pq
from audit_openfly_dataset_full import CACHE, DATA, EXPECTED, OUT, SELECTION, close, delta


def main():
    rows, rejected = [], []
    partitions = 0
    for item in SELECTION["episodes"]:
        e = item["episode"]
        raw = sorted(
            pq.read_table(CACHE / "traj" / (e["image_path"] + ".parquet")).to_pylist(),
            key=lambda r: r["frame_index"],
        )
        positions = {r["image_id"]: i for i, r in enumerate(raw)}
        previous_end = -1
        for j, (name, action) in enumerate(zip(e["index_list"], e["action"], strict=True)):
            old_index = positions[name]
            length = {8: 2, 9: 3, 0: 0}.get(action, 1)
            start = old_index - max(0, length - 1)
            end = start + length
            # This reconstruction must partition raw actions, not search for a
            # convenient nearby frame with a matching target label.
            assert start == previous_end + 1
            previous_end = old_index
            partitions += 1
            terminal = action == 0 and start == len(raw) - 1
            if not terminal and (
                action not in EXPECTED
                or end >= len(raw)
                or not close(delta(raw[start], raw[end]), EXPECTED[action])
            ):
                rejected.append(
                    dict(
                        trajectory=e["image_path"],
                        annotation_index=j,
                        action_id=action,
                        reason="endpoint motion mismatch",
                    )
                )
                continue
            indices = [max(0, start - 2), max(0, start - 1), start]
            files = [
                DATA / "frames" / e["image_path"] / (raw[k]["image_id"] + ".png") for k in indices
            ]
            row = dict(
                id=f"aligned:{e['image_path']}:{j}",
                trajectory=e["image_path"],
                split=item["split"],
                contract="openfly_verified_macro_v2",
                action_id=action,
                direction_id=1 if action in (8, 9) else action,
                instruction=e["gpt_instruction"],
                annotation_frame=old_index,
                frame_index=start,
                endpoint_frame=end,
                images=[str(p) for p in files],
                image_sha256=[hashlib.sha256(p.read_bytes()).hexdigest() for p in files],
                image_indices=indices,
                terminal=terminal,
                motion_verified=not terminal,
            )
            assert all(i <= start for i in indices)
            rows.append(row)
        assert previous_end == len(raw) - 1
    target = OUT / "aligned_macro_manifest.jsonl"
    target.write_text("".join(json.dumps(r) + "\n" for r in rows))
    train = {r["trajectory"] for r in rows if r["split"] == "train"}
    dev = {r["trajectory"] for r in rows if r["split"] == "val"}
    assert not train & dev
    result = dict(
        rows=len(rows),
        partitions_checked=partitions,
        rejected=rejected,
        train_routes=len(train),
        dev_routes=len(dev),
        manifest_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        status="separate verified macro manifest; existing atomic training data unchanged",
    )
    (OUT / "aligned_macro_audit.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
