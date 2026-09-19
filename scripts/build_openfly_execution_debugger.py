"""Publish recorded-frame/kinematic reconstruction diagnostics, never fake flights."""

import io
import json
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "reports/vla_dataset_review_20260916"
OUT = ROOT / "reports/vla_openfly_execution_20260919"


def main():
    report = json.loads((OUT / "expert_reconstruction.json").read_text())
    previous = json.loads((ROOT / "reports/vla_openfly_routes_20260919/routes.json").read_text())
    previews = {r["trajectory"]: [f["preview"] for f in r["frames"]] for r in previous}
    source = json.loads((OUT / "source_control.json").read_text())
    report["routes"].append(
        {
            "name": "vlnv20",
            "trajectory": source["selection"]["route"],
            "raw_frames": source["raw_frames"],
            "raw_sha256": source["raw_parquet_sha256"],
            "unknown_raw_labels": [],
            "units": "metres",
            "atomic_gate_passed": source["atomic_gate_passed"],
            "variants": {
                "raw_atomic": source["raw_atomic"],
                "original_packed": source["original_packed"],
            },
        }
    )
    for route in report["routes"]:
        name = route["name"]
        if route["trajectory"] in previews:
            route["previews"] = previews[route["trajectory"]]
        else:
            path = (
                Path("D:/drone_vla_pilot/data/openfly_rlds_execution_20260919")
                if name == "vlnv20"
                else Path("D:/drone_vla_pilot/data/openfly_rlds_diagnostic_20260919")
            ) / (name + "_raw.parquet")
            raw = sorted(pq.read_table(path).to_pylist(), key=lambda r: r["frame_index"])
            route["previews"] = []
            for i, row in enumerate(raw):
                file = VIEW / "execution_assets" / name / f"{i:04}.jpg"
                file.parent.mkdir(parents=True, exist_ok=True)
                image = Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB")
                image.thumbnail((800, 450))
                image.save(file, quality=85)
                route["previews"].append(file.relative_to(VIEW).as_posix())
        for preview in route["previews"]:
            assert (VIEW / preview).is_file()
    (VIEW / "openfly_execution.json").write_text(json.dumps(report), encoding="utf-8")
    template = ROOT / "src/uavlab/analysis/openfly_execution.html"
    (VIEW / "openfly_execution.html").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "routes": len(report["routes"]),
                "recorded_previews": sum(len(r["previews"]) for r in report["routes"]),
                "renderer_used": False,
            }
        )
    )


if __name__ == "__main__":
    main()
