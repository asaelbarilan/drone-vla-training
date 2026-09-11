"""Credential-file Gemini transport with a persistent free-quota circuit breaker."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderHTTPError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Gemini returned HTTP {status}; no retry or fallback")


def configuration(env_file: Path) -> dict[str, str]:
    settings = {}
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError("Invalid .env assignment")
        settings[key.strip()] = value.strip().strip("\"'")
    for key in ("GEMINI_API_KEY_FILE", "GEMINI_MODEL", "GEMINI_FREE_TIER_CONFIRMED"):
        if key in os.environ:
            settings[key] = os.environ[key]
    return settings


def key_from_file(settings: dict[str, str]) -> str:
    value = Path(settings["GEMINI_API_KEY_FILE"]).read_text(encoding="utf-8-sig").strip()
    # Accept a bare key or an explicitly named one-line assignment.
    for prefix in ("GEMINI_API_KEY=", "GEMINI_KEY=", "GOOGLE_API_KEY="):
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()
            break
    value = value.strip("\"'")
    if not value or any(character.isspace() for character in value):
        raise ValueError("Gemini key file must contain one key or one named assignment")
    return value


def invoke(
    settings: dict[str, str],
    prompt: str,
    image: Path,
    stop_file: Path,
    *,
    schema: dict | None = None,
) -> dict:
    if settings.get("GEMINI_FREE_TIER_CONFIRMED", "false").lower() != "true":
        raise ValueError("Confirm billing is disabled before enabling Gemini API calls")
    if stop_file.exists():
        raise ValueError("Quota stop is active; no further API call was made")
    model = settings.get("GEMINI_MODEL", "gemini-3.5-flash")
    if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for character in model):
        raise ValueError("Invalid Gemini model identifier")
    mime = mimetypes.guess_type(image.name)[0]
    if mime not in {"image/png", "image/jpeg", "image/webp"}:
        raise ValueError("Use a PNG, JPEG, or WebP image")
    return invoke_images(
        settings,
        prompt,
        [{"mimeType": mime, "data": base64.b64encode(image.read_bytes()).decode()}],
        stop_file,
        schema=schema,
    )


def invoke_images(settings, prompt, images, stop_file, *, schema=None, max_tokens=256):
    if settings.get("GEMINI_FREE_TIER_CONFIRMED", "false").lower() != "true":
        raise ValueError("Confirm billing is disabled before enabling Gemini API calls")
    if stop_file.exists():
        raise ValueError("Quota stop is active; no further API call was made")
    model = settings.get("GEMINI_MODEL", "gemini-3.5-flash")
    if not model or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in model):
        raise ValueError("Invalid Gemini model identifier")
    body = {
        "contents": [{"parts": [{"text": prompt}] + [{"inlineData": image} for image in images]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingLevel": "minimal"},
        },
    }
    if schema is not None:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseJsonSchema"] = schema
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key_from_file(settings)},
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 429:
            stop_file.parent.mkdir(parents=True, exist_ok=True)
            stop_file.write_text("Stopped at Gemini quota/rate limit. No automatic retries.\n")
        raise ProviderHTTPError(exc.code) from None
    except URLError:
        raise RuntimeError("Gemini connection failed; no retry or fallback") from None
