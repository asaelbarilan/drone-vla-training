"""Print one unmodified Ollama chat response for adapter diagnostics."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from uavlab.plugins.inference.ollama import OllamaInference
from uavlab.plugins.reasoning.vlm import PROMPT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("image", type=Path)
    parser.add_argument("--num-predict", type=int, default=256)
    parser.add_argument("--flight-prompt", action="store_true")
    parser.add_argument("--no-think-tag", action="store_true")
    args = parser.parse_args()

    backend = OllamaInference(model_id=args.model)
    encoded = base64.b64encode(args.image.read_bytes()).decode("ascii")
    prompt = (
        PROMPT.format(
            instruction="fly to the target tower and stop there",
            width=224,
            height=224,
            umax=223,
            vmax=223,
        )
        if args.flight_prompt
        else 'Answer only JSON: {"found": true or false}. Is the red tower visible?'
    )
    if args.no_think_tag:
        prompt += "\n/no_think"
    payload = backend._post(
        "/api/chat",
        {
            "model": args.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [encoded],
                }
            ],
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.0, "num_predict": args.num_predict, "seed": 0},
        },
    )
    print(json.dumps(payload, indent=2))
    backend.close()


if __name__ == "__main__":
    main()
