"""Offline check of PNG encoding and actual Ollama request construction; zero calls."""

import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from uavlab.interfaces import InferenceRequest
from uavlab.plugins.inference.ollama import OllamaInference
from uavlab.plugins.reasoning.onfly import _encode_png


async def main():
    manifest = json.loads(
        Path("runs/c5_clutter_stable_20260914_s1061/manifest.json").read_text(encoding="utf-8")
    )
    backend = OllamaInference(**manifest["architecture_config"]["inference"]["params"])
    captured = []

    def intercept(path, body):
        captured.append((path, json.loads(json.dumps(body))))
        return {"message": {"content": "{}"}, "eval_count": 0}

    backend._post = intercept
    rows = []
    for filename in (
        "runs/c5_clutter_stable_20260914_s1061/debug/images/call-000004-0.png",
        "runs/c5_hover_stable_20260914_s1062/debug/images/call-000023-1.png",
    ):
        p = Path(filename)
        raw = p.read_bytes()
        img = Image.open(io.BytesIO(raw))
        array = np.asarray(img)
        encoded = _encode_png(img)
        assert np.array_equal(np.asarray(Image.open(io.BytesIO(base64.b64decode(encoded)))), array)
        # Replay the captured request's exact PNG bytes into the actual backend.
        await backend.invoke(
            InferenceRequest(
                model_id="gemma4:e2b",
                role="policy",
                prompt_hash="offline-wire-check",
                prompt="offline",
                images=(base64.b64encode(raw).decode(),),
                image_count=1,
            )
        )
        endpoint, body = captured[-1]
        wire = base64.b64decode(body["messages"][0]["images"][0], validate=True)
        assert wire == raw
        decoded = Image.open(io.BytesIO(wire))
        assert decoded.mode == "RGB"
        assert np.array_equal(np.asarray(decoded), array)
        rows.append(
            dict(
                source=filename,
                format=decoded.format,
                mode=decoded.mode,
                size=list(decoded.size),
                center_rgb=list(decoded.getpixel((112, 112))),
                png_sha256=hashlib.sha256(raw).hexdigest(),
                exact_png_bytes_preserved=True,
                policy_encode_preserves_rgb_pixels=True,
                endpoint=endpoint,
            )
        )
    assert rows[1]["center_rgb"][0] > rows[1]["center_rgb"][2] + 100
    backend.close()
    out = dict(
        checks=rows,
        network_calls=0,
        scope=(
            "Actual client construction with intercepted transport; "
            "does not inspect Ollama internal preprocessing"
        ),
    )
    Path("reports/clutter_stable_20260914/IMAGE_TRANSPORT.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
