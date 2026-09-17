"""Browser verification of actual model response, image and source-time playback."""

import argparse
import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--runs", type=Path, required=True)
parser.add_argument("--url", required=True)
parser.add_argument("--out", type=Path, required=True)
args = parser.parse_args()
checks, errors = [], []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1500, "height": 1050})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(args.url, wait_until="load")
    options = page.locator("#run option").all_text_contents()
    assert len(options) == 4
    for folder in sorted(args.runs.glob("*_frd_*_s*")):
        index = next(
            i
            for i, label in enumerate(options)
            if folder.name in label
            or (
                f"seed {folder.name.rsplit('_s', 1)[1]}" in label
                and ("| trained |" if "_trained_" in folder.name else "| zero-shot |") in label
            )
        )
        page.locator("#run").select_option(index=index)
        assert not page.locator("#error").is_visible()
        records = [
            json.loads(f.read_text()) for f in sorted((folder / "debug/calls").glob("*.json"))
        ]
        assert page.locator(".decision").count() == len(records)
        for at in sorted({0, len(records) // 2, len(records) - 1}):
            page.locator(".decision").nth(at).click()
            expected = records[at]
            assert page.locator("#response").inner_text() == expected["response"]
            assert page.locator("#prompt").inner_text() == expected["prompt"]
            encoded = page.locator("#requestImages img").first.get_attribute("src")
            assert (
                base64.b64decode(encoded.split(",", 1)[1])
                == (folder / expected["image_files"][0]).read_bytes()
            )
            page.locator("#atSource").click()
            assert (
                page.locator("#time")
                .inner_text()
                .startswith(f"{expected['requested_t_sim_ns'] / 1e9:.2f} /")
            )
            assert "simulation_paused_during_inference" in page.locator("#explanation").inner_text()
            checks.append(
                {"run": folder.name, "call_index": at, "response_image_prompt_time_match": True}
            )
        page.locator("#scrub").fill(page.locator("#scrub").get_attribute("max"))
        result = json.loads((folder / "result.json").read_text())
        assert page.locator("#outcome").inner_text() == (
            "Completed" if result["success"] else result["termination_reason"]
        )
        assert (
            page.locator("#distance").inner_text()
            == f"{result['metrics']['distance_to_goal_m']:.2f} m"
        )
    page.locator("#run").select_option(index=0)
    page.locator(".decision").nth(0).click()
    page.locator("#atSource").click()
    page.screenshot(path=str(args.out / "model_preview.png"), full_page=True)
    page.locator("#scrub").fill("0")
    page.locator("#play").click()
    page.wait_for_function("!document.querySelector('#time').textContent.startsWith('0.00 /')")
    page.locator("#play").click()
    page.set_viewport_size({"width": 640, "height": 900})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors, errors
    browser.close()
(args.out / "model_ui_check.json").write_text(
    json.dumps(
        {"checks": checks, "js_errors": errors, "playback": True, "responsive": True}, indent=2
    )
)
print(f"PASS {len(checks)} exact response/image/prompt/source-time checks; four outcomes; playback")
