"""Check exact source frames/native logs in the new offline expansion viewer."""

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

visual = Path("D:/drone_vla_pilot/data/visible_yaw_pairs_20260916_v3")
external = Path("D:/drone_vla_pilot/external_samples_20260916_a")
rows = [json.loads(s) for s in (visual / "index.jsonl").read_text().splitlines()]
report = json.loads((external / "report.json").read_text())
checks = []
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1200, "height": 900})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8771/data_expansion.html")
    assert page.locator("#episode option").count() == 74
    for i, row in enumerate(rows):
        page.locator("#episode").select_option(str(i))
        assert page.locator("#instruction").inner_text() == row["instruction"]
        for frame, path in enumerate((row["images"]["mosaic"], row["after_image"])):
            page.locator("#scrub").fill(str(frame))
            raw = base64.b64decode(page.locator("#image").get_attribute("src").split(",")[1])
            assert raw == (visual / path).read_bytes()
            record = json.loads(page.locator("#record").inner_text())
            assert record["state"] == (row["state"] if frame == 0 else row["after_state"])
            if frame == 0:
                assert record["target"] == row["target"]
            checks.append({"option": i, "frame": frame, "source_match": True})
    option = 64
    for source in report["sources"]:
        for i, ep in enumerate(source["episodes"]):
            page.locator("#episode").select_option(str(option))
            log = json.loads(
                (
                    external / source["dataset"].split("/")[-1] / f"episode_{i:02d}" / "log.json"
                ).read_text()
            )
            for frame in (0, len(ep["images"]) // 2, len(ep["images"]) - 1):
                page.locator("#scrub").fill(str(frame))
                raw = base64.b64decode(page.locator("#image").get_attribute("src").split(",")[1])
                assert raw == (external / ep["images"][frame]["path"]).read_bytes()
                record = json.loads(page.locator("#record").inner_text())
                assert record["raw_log"] == log["raw_logs"][frame]
                assert record["preprocessed_log"] == log["preprocessed_logs"][frame]
                checks.append({"option": option, "frame": frame, "source_match": True})
            option += 1
    page.locator("#episode").select_option("64")
    page.locator("#play").click()
    page.wait_for_function("document.querySelector('#scrub').value !== '0'")
    page.locator("#play").click()
    page.screenshot(path="reports/vla_frd_followup_20260916/expansion_preview.png", full_page=True)
    page.set_viewport_size({"width": 640, "height": 900})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors
    browser.close()
Path("reports/vla_frd_followup_20260916/expansion_ui_check.json").write_text(
    json.dumps(dict(checks=checks, js_errors=errors, playback=True, responsive=True), indent=2)
)
print(f"PASS {len(checks)} exact source-frame/native-log checks; playback; responsive")
