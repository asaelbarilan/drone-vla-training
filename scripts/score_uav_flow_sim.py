"""D162: score UAV-Flow-Eval flights with the official nDTW, plus endpoint numbers.

nDTW is computed by the official metric.py functions, unchanged (same sampling
stride per class, same zero-position rule for Turn/Rotate, same 20-point cap on
the reference). Success rate in the papers is a human judgement; it is not
computed here. Instead every flight also gets its endpoint distance and final
yaw error against the reference end, which is the input to the automatic
success rule that a small human-labelled sample will calibrate later.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

EVAL = Path("D:/drone_vla_pilot/simulators/uav_flow_repo/UAV-Flow-Eval")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flights", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(EVAL))
    import metric

    classes = json.loads((EVAL / "classified_instr.json").read_text(encoding="utf-8"))
    rows, per_class = [], {}
    for name, files in classes.items():
        zero_pos = name in ["Turn", "Rotate"]
        step = 2 if name in ["Turn", "Move"] else 5
        scores = []
        for file in files:
            gt_path, flight_path = EVAL / "test_jsons" / file, args.flights / file
            if not flight_path.exists():
                continue
            model_vecs = metric.get_sampled_state6d_from_model_rule(
                str(flight_path), step, zero_pos
            )
            gt_vecs = metric.get_sampled_state6d_from_gt_rule(str(gt_path), step, 20, zero_pos)
            score = metric.ndtw(
                metric.dtw_distance(gt_vecs, model_vecs), metric.path_length(gt_vecs), eta=1
            )
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
            flight = json.loads(flight_path.read_text(encoding="utf-8"))
            ref_end = np.array(gt["reference_path_preprocessed"][-1], dtype=float)
            if flight:
                end = np.array(flight[-1]["state"][0], dtype=float)
                yaw = float(flight[-1]["state"][1][1])
            else:
                end, yaw = np.zeros(3), 0.0
            yaw_error = abs((yaw - ref_end[4] + 180) % 360 - 180)
            rows.append(
                dict(
                    file=file,
                    cls=name,
                    instruction=gt["instruction"],
                    ndtw=None if score is None else round(float(score), 4),
                    steps=len(flight),
                    end_distance_m=round(float(np.linalg.norm(end - ref_end[:3])) / 100, 3),
                    final_yaw_error_deg=round(yaw_error, 1),
                )
            )
            if score is not None:
                scores.append(float(score))
        per_class[name] = dict(
            tasks=len(files),
            flown=len(scores),
            mean_ndtw=round(float(np.mean(scores)), 4) if scores else None,
        )
    flown = [r["ndtw"] for r in rows if r["ndtw"] is not None]
    summary = dict(
        flights=str(args.flights),
        flown=len(flown),
        mean_ndtw=round(float(np.mean(flown)), 4) if flown else None,
        median_end_distance_m=round(float(np.median([r["end_distance_m"] for r in rows])), 3)
        if rows
        else None,
        per_class=per_class,
        note="nDTW via the official metric.py functions; success rate needs human judgement",
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dict(summary=summary, flights=rows), indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
