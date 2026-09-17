# ruff: noqa: E501
"""Make three labelled source-recording clips from cached OpenFly parquet frames."""

import hashlib
import html
import io
import json
import subprocess
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

ROOT = Path("D:/drone_vla_pilot/data/openfly_train_pilot_20260917")
REPORT = Path("reports/vla_openfly_train_20260917")
VIEW = Path("reports/vla_dataset_review_20260916")
MEDIA = VIEW / "openfly_clips"
MEDIA.mkdir(exist_ok=True)
selection = json.loads((REPORT / "selection.json").read_text())
examples = [
    ("env_airsim_16", "AirSim city route"),
    ("env_gs_ecust", "Reconstructed campus route"),
    ("env_ue_bigcity", "Unreal city route"),
]
clips, cards = [], []
for environment, title in examples:
    item = next(
        x
        for x in selection["episodes"]
        if x["environment"] == environment and x["split"] == "train"
    )
    episode = item["episode"]
    source = ROOT / "traj" / (episode["image_path"] + ".parquet")
    records = sorted(pq.read_table(source).to_pylist(), key=lambda r: r["frame_index"])
    output = MEDIA / (environment + ".mp4")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        "640x480",
        "-r",
        "4",
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    hashes = []
    for record in records:
        data = record["image"]["bytes"]
        hashes.append(hashlib.sha256(data).hexdigest())
        with Image.open(io.BytesIO(data)) as source_image:
            image = source_image.convert("RGB")
            image.thumbnail((640, 480))
            canvas = Image.new("RGB", (640, 480))
            canvas.paste(image, ((640 - image.width) // 2, (480 - image.height) // 2))
            process.stdin.write(canvas.tobytes())
    process.stdin.close()
    errors = process.stderr.read().decode()
    assert process.wait(timeout=60) == 0, errors
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=nb_frames,duration,codec_name",
                "-of",
                "json",
                str(output),
            ]
        )
    )["streams"][0]
    assert int(probe["nb_frames"]) == len(records)
    clip = dict(
        title=title,
        trajectory=episode["image_path"],
        instruction=episode["gpt_instruction"],
        source=str(source),
        frames=len(records),
        display_fps=4,
        source_frame_sha256=hashes,
        video_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        probe=probe,
        path=str(output),
    )
    clips.append(clip)
    cards.append(
        f'<section><h2>{html.escape(title)}</h2><video controls preload="metadata" playsinline src="openfly_clips/{output.name}"></video><p>{html.escape(episode["gpt_instruction"])}</p><small>{len(records)} consecutive source frames · {len(records) / 4:g}s playback · official TRAIN</small></section>'
    )
page = (
    """<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>OpenFly source clips</title><style>body{background:#101c2a;color:#e5edf5;font:18px system-ui;margin:24px}main{max-width:1100px;margin:auto}section{padding:20px;background:#1c2d40;margin:20px 0;border-radius:12px}video{display:block;width:100%;max-width:800px}a{color:#79c9ff}small{color:#b9c9da}</style><main><h1>Three OpenFly dataset clips</h1><p>Recorded dataset routes from simulator/reconstructed scenes. These are expert source recordings, not predictions or flights from our trained models.</p><p>All consecutive cached frames, shown at <b>4 frames/second for inspection</b>. This playback speed is not the original physical flight timing. No interpolation or generated frames.</p><a href="openfly_training.html">Training results and frame-by-frame action viewer</a>"""
    + "".join(cards)
    + "</main></html>"
)
(VIEW / "openfly_clips.html").write_text(page, encoding="utf-8")
(REPORT / "clips_manifest.json").write_text(
    json.dumps(dict(revision=selection["revision"], clips=clips), indent=2), encoding="utf-8"
)
print(
    json.dumps(
        [dict(title=x["title"], frames=x["frames"], duration=x["probe"]["duration"]) for x in clips]
    )
)
