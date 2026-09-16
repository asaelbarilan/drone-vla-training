"""Bounded anonymous audit of five complete train-flight previews per known source.

These are HF viewer assets, not admitted action training data or original-shard
checksums. No coordinate/control interpretation is guessed from numeric values.
"""

import argparse
import hashlib
import io
import json
import time
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PIL import Image

SOURCES = ["wangxiangyu0814/UAV-Flow", "wangxiangyu0814/UAV-Flow-Sim"]
MAX_ROWS = 1000
MAX_IMAGE_BYTES = 100 * 1024 * 1024


def main(out):
    out.mkdir(parents=True, exist_ok=False)
    session = requests.Session()
    downloaded = 0
    reports = []
    for source in SOURCES:
        meta = session.get(f"https://huggingface.co/api/datasets/{source}", timeout=30)
        meta.raise_for_status()
        meta = meta.json()
        folder = out / source.rsplit("/", 1)[-1]
        folder.mkdir()
        groups = {}
        order = []
        closed = set()
        previous = None
        request_bytes = 0
        for offset in range(0, MAX_ROWS, 100):
            response = session.get(
                "https://datasets-server.huggingface.co/rows",
                params={
                    "dataset": source,
                    "config": "default",
                    "split": "train",
                    "offset": offset,
                    "length": 100,
                },
                timeout=40,
            )
            response.raise_for_status()
            request_bytes += len(response.content)
            payload = response.json()
            if not payload.get("rows"):
                break
            for wrapper in payload["rows"]:
                if wrapper.get("truncated_cells"):
                    raise ValueError("truncated preview cells")
                row = wrapper["row"]
                identity = row["id"]
                if previous is not None and identity != previous:
                    closed.add(previous)
                previous = identity
                if identity not in groups:
                    groups[identity] = []
                    order.append(identity)
                groups[identity].append(row)
            if len(closed) >= 5:
                break
        chosen = [i for i in order if i in closed][:5]
        if len(chosen) != 5:
            raise ValueError(f"{source}: fewer than five bounded complete groups")
        episodes = []
        for episode_index, identity in enumerate(chosen):
            rows = groups[identity]
            indices = [r["frame_idx"] for r in rows]
            log = json.loads(rows[0]["log"])
            assert all(json.loads(r["log"]) == log for r in rows)
            assert indices == list(range(len(rows))), "missing/out-of-order image frames"
            assert len(rows) == len(log["raw_logs"]) == len(log["preprocessed_logs"]), (
                "pose/image count mismatch"
            )
            ep = folder / f"episode_{episode_index:02d}"
            ep.mkdir()
            (ep / "log.json").write_text(json.dumps(log, indent=2))
            images = []
            revisions = set()
            for row in rows:
                url = row["image"]["src"]
                host = urlsplit(url).hostname
                assert host == "datasets-server.huggingface.co"
                path = urlsplit(url).path
                if "/--/" in path:
                    revisions.add(path.split("/--/")[1])
                response = session.get(url, timeout=25)
                response.raise_for_status()
                downloaded += len(response.content)
                if downloaded > MAX_IMAGE_BYTES:
                    raise ValueError("100MiB image budget exceeded")
                image = Image.open(io.BytesIO(response.content))
                image.load()
                assert image.size == (256, 256)
                target = ep / f"{row['frame_idx']:05d}.jpg"
                target.write_bytes(response.content)
                images.append(
                    {
                        "frame_idx": row["frame_idx"],
                        "path": target.relative_to(out).as_posix(),
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                        "bytes": len(response.content),
                        "size": list(image.size),
                        "mode": image.mode,
                    }
                )
            widths = sorted({len(v) for v in log["raw_logs"]})
            deltas = None
            if widths == [7]:
                values = [v[-1] for v in log["raw_logs"]]
                dt = [b - a for a, b in pairwise(values)]
                deltas = {
                    "last_column_strictly_increasing": all(x > 0 for x in dt),
                    "min_delta": min(dt),
                    "max_delta": max(dt),
                    "units_semantics": "not inferred; must verify source contract",
                }
            episode = {
                "id": identity,
                "frames": len(rows),
                "frame_indices_contiguous": True,
                "raw_log_rows": len(log["raw_logs"]),
                "raw_log_widths": widths,
                "preprocessed_log_widths": sorted({len(v) for v in log["preprocessed_logs"]}),
                "instruction": log.get("instruction"),
                "asset_revisions": sorted(revisions),
                "last_column_deltas": deltas,
                "images": images,
            }
            episodes.append(episode)
            print(
                json.dumps(
                    {
                        "source": source,
                        "episode": identity,
                        "frames": len(rows),
                        "downloaded_image_bytes": downloaded,
                    }
                ),
                flush=True,
            )
        result = {
            "dataset": source,
            "repository_sha_at_audit": meta.get("sha"),
            "declared_card_license": meta.get("cardData", {}).get("license"),
            "source_split": "train",
            "source_kind": "real UAV candidate"
            if source.endswith("/UAV-Flow")
            else "external simulator candidate",
            "row_api_response_bytes": request_bytes,
            "episodes": episodes,
            "admitted_to_training": False,
            "missing_admission_evidence": [
                "explicit data license",
                "camera calibration/extrinsics",
                "coordinate units/frame/angular conventions",
                "commands versus achieved poses",
                "terminal/intervention/failure semantics",
                "cross-source/site split audit",
            ],
            "asset_provenance": "HF viewer JPEG assets; not original parquet byte verification",
        }
        reports.append(result)
        (out / "report.json").write_text(
            json.dumps({"sources": reports, "downloaded_image_bytes": downloaded}, indent=2)
        )
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    try:
        main(args.out)
    except Exception as exc:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "failure.json").write_text(
            json.dumps(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "elapsed_seconds": time.monotonic() - started,
                },
                indent=2,
            )
        )
        raise
