"""Check rendered data review against admitted source records and flight replay."""

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from uavlab.training.mixed_batches import task_class

DATA = Path("D:/drone_vla_pilot/data/local_expanded_20260917_v4")
REPORT = Path("reports/vla_local_expanded_20260917_v4")
rows = [json.loads(s) for s in (DATA / "index.jsonl").read_text().splitlines()]
rows = [r for r in rows if r["seed"] >= 1450]
indices = {0, len(rows) - 1}
for split in ("train", "val"):
    for group in ("visual", "motion", "hold", "stop"):
        indices.add(
            next(i for i, r in enumerate(rows) if r["split"] == split and task_class(r) == group)
        )
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1100, "height": 850})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8771/expanded_data.html")
    assert page.locator("#sample option").count() == len(rows)
    for i in sorted(indices):
        row = rows[i]
        page.locator("#sample").select_option(str(i))
        assert page.locator("#instruction").inner_text() == row["instruction"]
        assert json.loads(page.locator("#target").inner_text()) == row["target"]
        assert json.loads(page.locator("#state").inner_text()) == row["state"]
        src = page.locator("#image").get_attribute("src")
        assert (
            base64.b64decode(src.split(",", 1)[1])
            == (Path(row["data_root"]) / row["images"]["mosaic"]).read_bytes()
        )
    manifest = json.loads((DATA / "manifest.json").read_text())
    assert (
        json.loads(page.locator("#batches").inner_text()) == manifest["schedules"]["expanded"][:8]
    )
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.goto("http://127.0.0.1:8771/expanded_teacher_flights.html")
    assert page.evaluate("DATA.runs.length") == 20
    assert not errors, errors
    browser.close()
report = dict(
    passed=True,
    admitted_new_rows=len(rows),
    checked_examples=len(indices),
    source_checks=4 * len(indices),
    teacher_flights=20,
    responsive=True,
    page_errors=errors,
)
(REPORT / "browser_check.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report))
