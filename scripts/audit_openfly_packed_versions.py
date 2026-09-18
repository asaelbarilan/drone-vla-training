"""Compare the two packed training records with current raw source episodes."""

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_routes_20260919"
CACHE = Path("D:/drone_vla_pilot/data/openfly_rlds_diagnostic_20260919")


def main():
    ann = json.loads(
        Path(
            "D:/drone_vla_pilot/data/openfly_train_pilot_20260917/Annotation/train.json"
        ).read_text()
    )
    lookup = {x["image_path"]: x for x in ann}
    res = requests.get("https://huggingface.co/api/datasets/IPEC-COMMUNITY/OpenFly", timeout=30)
    res.raise_for_status()
    revision = res.json()["sha"]
    result = []
    for subset in ["vlnv1", "vlnv11"]:
        r = json.loads((OUT / (subset + "_record.json")).read_text())
        f = r["fields"]
        path = f["episode_metadata/file_path"][0].split("/uav_vln_data/")[1]
        a = lookup[path]
        dest = CACHE / (subset + "_raw.parquet")
        cap = 32 * 1024 * 1024
        if not dest.exists():
            url = f"https://huggingface.co/datasets/IPEC-COMMUNITY/OpenFly/resolve/{revision}/traj/{path}.parquet"
            with requests.get(url, stream=True, timeout=(20, 60)) as response:
                response.raise_for_status()
                assert int(response.headers.get("Content-Length", 0)) <= cap
                chunks = []
                total = 0
                for chunk in response.iter_content(1024 * 1024):
                    total += len(chunk)
                    assert total <= cap
                    chunks.append(chunk)
                dest.write_bytes(b"".join(chunks))
        raw = sorted(pq.read_table(dest).to_pylist(), key=lambda x: x["frame_index"])
        transforms = []
        for sample in raw:
            im = Image.open(io.BytesIO(sample["image"]["bytes"])).convert("RGB")
            transforms.append(
                {
                    method.name: np.asarray(im.resize((224, 224), method)).astype(np.int16)
                    for method in [
                        Image.Resampling.BILINEAR,
                        Image.Resampling.BICUBIC,
                        Image.Resampling.LANCZOS,
                        Image.Resampling.NEAREST,
                    ]
                }
            )
        matches = []
        for i, im in enumerate(f["steps/observation/image_1"]):
            pixels = np.asarray(Image.open(im["path"]).convert("RGB")).astype(np.int16)
            error, index, method = min(
                (float(np.abs(pixels - ar).mean()), j, m)
                for j, values in enumerate(transforms)
                for m, ar in values.items()
            )
            matches.append(
                dict(
                    packed_step=i,
                    nearest_raw_frame=index,
                    resize=method,
                    pixel_mae_255=error,
                    raw_image_id=raw[index]["image_id"],
                    raw_action_type=raw[index]["action_type"],
                )
            )
        result.append(
            dict(
                subset=subset,
                current_raw_revision=revision,
                raw_bytes=dest.stat().st_size,
                raw_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                trajectory=path,
                packed_action_vectors=[
                    f["steps/action"][i : i + 8] for i in range(0, len(f["steps/action"]), 8)
                ],
                current_annotation_actions=a["action"],
                current_annotation_image_ids=a["index_list"],
                image_matches=matches,
            )
        )
        print(
            json.dumps(
                dict(
                    subset=subset,
                    bytes=dest.stat().st_size,
                    max_image_mae=max(x["pixel_mae_255"] for x in matches),
                    nearest_raw_frames=[x["nearest_raw_frame"] for x in matches],
                )
            ),
            flush=True,
        )
    (OUT / "packed_vs_current_raw.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
