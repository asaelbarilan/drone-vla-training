"""Verify original dataset playback in a fresh headless Edge process."""

import base64
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

source = Path("../uav_arch_lab/data/qwen_vla_sft").resolve()
out = Path("reports/vla_dataset_review_20260916")
rows = [json.loads(x) for x in (source / "index.jsonl").read_text(encoding="utf-8").splitlines()]
by_seed = {}
for r in rows:
    by_seed.setdefault(r["seed"], []).append(r)
checks, errors = [], []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1150})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8771/viewer.html", wait_until="load")
    assert page.locator("#episode option").count() == 100
    for seed in (1201, 1204, 1200, 1299):
        page.locator("#episode").select_option(str(seed))
        expected = by_seed[seed]
        for index in (0, len(expected) // 2, len(expected) - 1):
            page.locator("#timeline").fill(str(index))
            r = expected[index]
            page.wait_for_function(
                "document.querySelector('#camera').complete && "
                "document.querySelector('#camera').naturalWidth===224"
            )
            assert page.locator("#source").inner_text() == r["image"]
            assert json.loads(page.locator("#target").inner_text()) == r["target"]
            assert page.locator("#hint").inner_text() == r["coarse_goal_direction"]
            encoded = page.locator("#camera").get_attribute("src").split(",", 1)[1]
            raw = base64.b64decode(encoded)
            assert raw == (source / r["image"]).read_bytes()
            identity = json.loads(page.locator("#identity").text_content())
            assert identity["sha256"] == hashlib.sha256(raw).hexdigest()
            assert identity["t_sim_ns"] == r["t_sim_ns"]
            checks.append({"seed": seed, "frame_index": index, "source": r["image"]})
    for split, count in (("train", 80), ("val", 20)):
        page.locator("#split").select_option(split)
        assert page.locator("#episode option").count() == count
        assert split in page.locator("#heading").inner_text()
    page.locator("#split").select_option("all")
    page.locator("#episode").select_option("1201")
    page.locator("#play").click()
    page.wait_for_function("Number(document.querySelector('#timeline').value)>0")
    page.locator("#play").click()
    assert page.locator("#play").inner_text() == "Play"
    page.locator("#timeline").fill("16")
    page.screenshot(path=str(out / "preview.png"), full_page=True)
    page.set_viewport_size({"width": 640, "height": 1000})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors, errors
    browser.close()
(out / "UI_CHECK.json").write_text(
    json.dumps(
        {
            "exact_frame_label_timestamp_checks": checks,
            "split_counts": {"train": 80, "val": 20},
            "playback_advanced": True,
            "mobile_overflow": False,
            "javascript_errors": errors,
            "browser": "fresh headless Edge",
            "model_calls": 0,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(
    "PASS: 12 exact source/label/timestamp checks, 80/20 split filter, "
    "playback, mobile; zero JS errors"
)
