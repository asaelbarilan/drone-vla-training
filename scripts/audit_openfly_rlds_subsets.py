"""Inventory all 20 public RLDS subsets with capped, sparse identity sampling.

Only the first record of each first shard is sampled. This does not claim an
exhaustive route-to-subset map. No image payload is decoded or used for training.
"""

import concurrent.futures
import hashlib
import json
import struct
from pathlib import Path

import google_crc32c
import requests

from uavlab.training.openfly_codec import OpenFlyCodec
from uavlab.training.rlds_metadata import identity_features

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_execution_20260919"
TREE = json.loads((OUT / "rlds_full_tree.json").read_text())
REVISION = "aaf4a5288134d5386018392e7f1ce57bb40c4a9c"
assert TREE["revision"] == REVISION
BASE = f"https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly-rlds/resolve/{REVISION}/"


class SparseReader:
    def __init__(self, url, size, byte_cap=512 * 1024):
        self.url, self.size, self.cap = url, size, byte_cap
        self.cache = []
        self.transferred = 0
        self.requests = 0

    def __call__(self, offset, length):
        if offset < 0 or length < 1 or offset + length > self.size:
            raise ValueError("Range escapes file")
        for start, data in self.cache:
            if start <= offset and offset + length <= start + len(data):
                return data[offset - start : offset - start + length]
        stop = min(self.size, offset + max(length, 4096))
        if self.transferred + stop - offset > self.cap:
            raise ValueError("Metadata transfer cap reached")
        with requests.get(
            self.url + f"?metadata_start={offset}",
            headers={"Range": f"bytes={offset}-{stop - 1}", "Accept-Encoding": "identity"},
            stream=True,
            timeout=(15, 45),
        ) as response:
            response.raise_for_status()
            if response.status_code != 206 or response.headers.get("Content-Range") != (
                f"bytes {offset}-{stop - 1}/{self.size}"
            ):
                raise ValueError("Server ignored exact bounded range; refused full download")
            data = response.raw.read(stop - offset + 1)
            if len(data) != stop - offset:
                raise ValueError("Unexpected bounded response length")
        self.cache.append((offset, data))
        self.transferred += len(data)
        self.requests += 1
        return data[:length]


def small_json(path):
    with requests.get(BASE + path, stream=True, timeout=(15, 45)) as response:
        response.raise_for_status()
        data = response.raw.read(256 * 1024 + 1, decode_content=True)
        if len(data) > 256 * 1024:
            raise ValueError("JSON exceeds cap")
        return json.loads(data)


def inspect(subset):
    entries = [e for e in TREE["entries"] if e["path"].startswith(subset + "/")]
    info_path = next(e["path"] for e in entries if e["path"].endswith("dataset_info.json"))
    info = small_json(info_path)
    statistics = [
        {"path": e["path"], "data": small_json(e["path"])}
        for e in entries
        if "/dataset_statistics_" in e["path"]
    ]
    shard = min((e for e in entries if ".tfrecord-" in e["path"]), key=lambda e: e["path"])
    reader = SparseReader(BASE + shard["path"], shard["size"])
    header = reader(0, 12)
    length, checksum = struct.unpack("<QI", header)
    crc = google_crc32c.value(header[:8])
    masked_crc = (((crc >> 15) | (crc << 17)) + 0xA282EAD8) & 0xFFFFFFFF
    if checksum != masked_crc or not 0 < length < 64 * 1024 * 1024:
        raise ValueError("Invalid or oversized record header")
    identity = identity_features(reader, 12, length)
    return {
        "subset": subset,
        "dataset_info": info,
        "statistics": statistics,
        "sampled_shard": shard["path"],
        "sampled_record_offset": 0,
        "sampled_record_length": length,
        "identity": identity,
        "header_crc_verified": True,
        "payload_crc_verified": False,
        "sampled_range_bytes": reader.transferred,
        "range_requests": reader.requests,
    }


def summarize(rows, checkpoint):
    training = json.loads(
        Path(
            "D:/drone_vla_pilot/data/openfly_train_pilot_20260917/Annotation/train.json"
        ).read_text()
    )
    train_ids = {r["image_path"] for r in training}
    protected = set()
    for split in ("seen", "unseen"):
        path = Path(f"D:/drone_vla_pilot/data/openfly_eval_20260917/Annotation/{split}.json")
        protected.update(r["image_path"] for r in json.loads(path.read_text()))
    summaries = []
    for row in rows:
        key = row["subset"]
        codec = OpenFlyCodec(checkpoint, key)
        stats = row["statistics"][0]["data"]["action"]
        codec.require_source_statistics(stats)
        path = row["identity"]["episode_metadata/file_path"].split("/uav_vln_data/")[1]
        assert path in train_ids and path not in protected
        supported = [0, 1, 2, 3, 8, 9] + ([4, 5] if max(stats["max"][4:6]) > 0 else [])
        summaries.append(
            {
                "subset": key,
                "source_statistics_match": True,
                "metadata_route_in_train": True,
                "metadata_route_in_official_eval": False,
                "reported_max_support": supported,
                "roundtrip_failures": [
                    a for a in supported if codec.decode(codec.encode(a))["action_id"] != a
                ],
                "norm_q01": stats["q01"],
                "norm_q99": stats["q99"],
                "minimum": stats["min"],
                "maximum": stats["max"],
            }
        )
    for key in ("vlnv1", "vlnv11"):
        path = Path(f"D:/drone_vla_pilot/data/openfly_rlds_diagnostic_20260919/{key}.tfrecord")
        payload = path.read_bytes()
        size = struct.unpack("<Q", payload[:8])[0]
        identity = identity_features(
            lambda offset, n, payload=payload: payload[offset : offset + n], 12, size
        )
        assert identity == next(r["identity"] for r in rows if r["subset"] == key)
    result = {
        "subsets": summaries,
        "packed_train_episodes": sum(
            sum(map(int, r["dataset_info"]["splits"][0]["shardLengths"])) for r in rows
        ),
        "reported_dataset_bytes": sum(
            int(r["dataset_info"]["splits"][0]["numBytes"]) for r in rows
        ),
        "metadata_range_bytes": sum(r["sampled_range_bytes"] for r in rows),
        "matched_full_record_identities": 2,
        "sampled_routes_are_official_train": True,
        "official_eval_overlap": False,
        "raw_development_route_assignment": "unresolved; environment-only samples are insufficient",
    }
    (OUT / "normalization_summary.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    subsets = sorted(
        {
            e["path"].split("/")[0]
            for e in TREE["entries"]
            if e["path"].endswith("dataset_info.json")
        },
        key=lambda s: int(s[4:]),
    )
    checkpoint = json.loads(
        Path("D:/drone_vla_pilot/models/openfly-agent-7b/config.json").read_text()
    )
    rows, failures = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(inspect, s): s for s in subsets}
        for future in concurrent.futures.as_completed(futures):
            subset = futures[future]
            try:
                row = future.result()
                fields = ("min", "max", "q01", "q99")
                source_stats = [s["data"]["action"] for s in row["statistics"]]
                if not source_stats:
                    raise ValueError("Missing source statistics")
                row["matching_checkpoint_keys"] = [
                    k
                    for k, v in checkpoint["norm_stats"].items()
                    if all(all(v["action"][f] == s[f] for f in fields) for s in source_stats)
                ]
                rows.append(row)
                print(
                    json.dumps(
                        {
                            "subset": subset,
                            "identity": row["identity"],
                            "matching_keys": row["matching_checkpoint_keys"],
                            "range_bytes": row["sampled_range_bytes"],
                        }
                    ),
                    flush=True,
                )
            except Exception as error:
                failures.append(
                    {
                        "subset": subset,
                        "error_type": type(error).__name__,
                        "message": str(error)[:500],
                    }
                )
                print(json.dumps(failures[-1]), flush=True)
    rows.sort(key=lambda r: int(r["subset"][4:]))
    report = {
        "revision": REVISION,
        "subset_count": len(subsets),
        "rows": rows,
        "failures": failures,
        "route_mapping_complete": False,
        "scope": "First episode of first shard only; metadata, not full payload CRC",
        "tree_sha256": hashlib.sha256((OUT / "rlds_full_tree.json").read_bytes()).hexdigest(),
    }
    (OUT / "subset_identity_audit.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "sampled": len(rows),
                "failed": len(failures),
                "range_bytes": sum(r["sampled_range_bytes"] for r in rows),
            }
        )
    )
    if failures:
        raise SystemExit(1)
    summarize(rows, checkpoint)


if __name__ == "__main__":
    main()
