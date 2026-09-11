"""Small free-tier Gemini image probe; credentials stay in a local key file."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uavlab.plugins.inference.gemini_client import (  # noqa: E402
    configuration,
    invoke,
    key_from_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--image", type=Path)
    parser.add_argument(
        "--prompt", default="Describe the visible objects and their colors concisely."
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "reports/paper_implementation/gemini_probe.json"
    )
    args = parser.parse_args()
    settings = configuration(args.env_file)
    if args.check_config:
        key_from_file(settings)
        print(
            json.dumps(
                {
                    "key_file_readable": True,
                    "model": settings.get("GEMINI_MODEL"),
                    "free_tier_confirmed": settings.get("GEMINI_FREE_TIER_CONFIRMED") == "true",
                }
            )
        )
        return
    if args.image is None:
        parser.error("--image is required for an API call")
    result = invoke(settings, args.prompt, args.image, ROOT / ".local/gemini_quota_stop")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "model": result.get("modelVersion")}))


if __name__ == "__main__":
    main()
