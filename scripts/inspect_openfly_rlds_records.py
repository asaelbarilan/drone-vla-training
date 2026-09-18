"""Read two bounded original TRAIN records; never download a whole shard."""

import hashlib
import io
import json
import os
import struct
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import google_crc32c
import requests
from PIL import Image
from tensorflow.core.example.example_pb2 import Example

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_routes_20260919"
CACHE = Path("D:/drone_vla_pilot/data/openfly_rlds_diagnostic_20260919")
API = "https://huggingface.co/api/datasets/IPEC-COMMUNITY/OpenFly-rlds"


def crc(data):
    n = google_crc32c.value(data)
    return (((n >> 15) | (n << 17)) + 0xA282EAD8) & 0xFFFFFFFF


def bounded_range(url, start, end):
    with requests.get(
        url + f"?range_start={start}",
        headers={"Range": f"bytes={start}-{end}"},
        stream=True,
        timeout=(20, 60),
    ) as r:
        r.raise_for_status()
        assert r.status_code == 206, "Server ignored bounded range; refused full download"
        assert r.headers["Content-Range"].startswith(f"bytes {start}-{end}/")
        data = r.raw.read(end - start + 2)
        assert len(data) == end - start + 1
        return data


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    response = requests.get(API, timeout=30)
    response.raise_for_status()
    revision = response.json()["sha"]
    tree = json.loads((ROOT / "reports/vla_openfly_repair_20260918/rlds_tree.json").read_text())
    summaries = []
    for subset in ["vlnv1", "vlnv11"]:
        shard = sorted(
            x["path"]
            for x in tree
            if x["path"].startswith(subset + "/") and ".tfrecord-" in x["path"]
        )[0]
        url = f"https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly-rlds/resolve/{revision}/{shard}"
        header = bounded_range(url, 0, 11)
        length, check = struct.unpack("<QI", header)
        assert crc(header[:8]) == check
        assert 0 < length <= 16 * 1024 * 1024, f"Record exceeds cap: {length}"
        payload = bounded_range(url, 12, 12 + length + 3)
        assert crc(payload[:-4]) == struct.unpack("<I", payload[-4:])[0]
        (CACHE / (subset + ".tfrecord")).write_bytes(header + payload)
        example = Example.FromString(payload[:-4])
        fields = example.features.feature
        metadata = {}
        for key, value in fields.items():
            if value.HasField("bytes_list"):
                values = list(value.bytes_list.value)
                if "image_" in key:
                    frame_info = []
                    for i, b in enumerate(values):
                        im = Image.open(io.BytesIO(b))
                        path = CACHE / subset / key.replace("/", "_") / f"{i:04}.png"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(b)
                        frame_info.append(
                            dict(path=str(path), sha256=hashlib.sha256(b).hexdigest(), size=im.size)
                        )
                    metadata[key] = frame_info
                else:
                    metadata[key] = [b.decode("utf-8") for b in values]
            elif value.HasField("float_list"):
                metadata[key] = list(value.float_list.value)
            else:
                metadata[key] = list(value.int64_list.value)
        stats = []
        for entry in tree:
            if entry["path"].startswith(subset + "/") and "/dataset_statistics_" in entry["path"]:
                res = requests.get(
                    f"https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly-rlds/resolve/{revision}/"
                    + entry["path"],
                    timeout=30,
                )
                res.raise_for_status()
                stats.append(dict(path=entry["path"], data=res.json()))
        result = dict(
            subset=subset,
            revision=revision,
            shard=shard,
            first_record_bytes=length,
            record_sha256=hashlib.sha256(header + payload).hexdigest(),
            crc_verified=True,
            fields=metadata,
            statistics=stats,
        )
        (OUT / (subset + "_record.json")).write_text(json.dumps(result, indent=2))
        summaries.append({k: v for k, v in result.items() if k not in ["fields", "statistics"]})
        print(
            json.dumps(
                dict(subset=subset, bytes=length, keys={k: len(v) for k, v in metadata.items()})
            ),
            flush=True,
        )
    (OUT / "rlds_download.json").write_text(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
