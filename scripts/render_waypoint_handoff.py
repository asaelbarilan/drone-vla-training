"""Export D-97 source-pixel, depth-patch and waypoint inspection without replay."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    out = Path("reports/waypoint_handoff_audit_20260912")
    data = json.loads((out / "trace.json").read_text(encoding="utf-8"))
    data["images"] = {
        row["source_seq"]: "data:image/png;base64,"
        + base64.b64encode((out / row["rgb_file"]).read_bytes()).decode("ascii")
        for row in data["decisions"]
    }
    template = Path("scripts/waypoint_handoff_template.html").read_text(encoding="utf-8")
    html = template.replace(
        "__DATA__", json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")
    )
    (out / "index.html").write_text(html, encoding="utf-8")
    preview = Path("reports/debugger/waypoint_handoff.html")
    preview.write_text(html, encoding="utf-8")
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)
    small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
    times = (24, 26, 27, 30, 32, 36, 39, 41, 42, 43, 44, 45, 46, 47, 48, 49)
    chosen = [r for r in data["decisions"] if r["available_s"] in times]
    canvas = Image.new("RGB", (1120, 1320), (9, 18, 28))
    draw = ImageDraw.Draw(canvas)
    for i, row in enumerate(chosen):
        left, top = (i % 4) * 280, (i // 4) * 330
        im = (
            Image.open(out / row["rgb_file"])
            .convert("RGB")
            .resize((252, 252), Image.Resampling.NEAREST)
        )
        mark = ImageDraw.Draw(im)
        u, v = [a * 252 / 224 for a in row["pixel"]]
        mark.ellipse([u - 8, v - 8, u + 8, v + 8], outline="yellow", width=2)
        for width, color in ((3, "black"), (1, "yellow")):
            mark.line([u - 12, v, u + 12, v], fill=color, width=width)
            mark.line([u, v - 12, u, v + 12], fill=color, width=width)
        canvas.paste(im, (left + 14, top + 28))
        draw.text(
            (left + 12, top + 3),
            f"Available {row['available_s']:.0f}s | source {row['source_s']:.2f}s",
            font=font,
            fill="#d9e8f4",
        )
        raw, ray = row["raw_patch_median_m"], row["exact_ray_box_depth_m"]
        depth_label = f"{raw:.2f} m" if raw is not None else "missing"
        ray_label = f"{ray:.2f} m" if ray is not None else "no box hit"
        draw.text(
            (left + 12, top + 284),
            f"Depth {depth_label} | ray {ray_label}",
            font=small,
            fill="#8edce0",
        )
        draw.text(
            (left + 12, top + 306),
            row["owner"]["kind"] + " " + str(row["owner"].get("index", "")),
            font=small,
            fill="#aac0d4",
        )
    canvas.save(out / "contact_sheet.png")
    canvas.save("reports/debugger/waypoint_contact_sheet.png")
    # The portable report keeps its comparison links valid outside the preview server.
    html = html.replace(
        'href="super_passage_4160.html"', 'href="../super_passage_probe_20260912/index.html"'
    )
    html = html.replace('href="waypoint_contact_sheet.png"', 'href="contact_sheet.png"')
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"Exported {len(data['decisions'])} source frames: {preview}")


if __name__ == "__main__":
    main()
