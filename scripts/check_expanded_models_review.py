"""Validate every source case and recorded model prediction in D141 review."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path("reports/vla_expanded_models_20260917")
summary = json.loads((root / "summary.json").read_text())
assert len(summary["official_transfer"]) == 4
assert all(x["status"] == "complete" for x in summary["local"].values())
rows = [
    json.loads(x)
    for x in Path("D:/drone_vla_pilot/data/openfly_eval_20260917/eval.jsonl")
    .read_text()
    .splitlines()
]
reports = {
    k: json.loads((root / f"{k}_transfer_report.json").read_text())
    for k in summary["official_transfer"]
}
checks = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8771/expanded_models.html")
    assert page.locator("#case option").count() == len(rows)
    assert page.locator("#scores tr").count() == 5
    for model, report in reports.items():
        key = "decision_id" if model == "openfly" else "id"
        outputs = {x[key]: x for x in report["outputs"]}
        page.locator("#model").select_option(model)
        for i, row in enumerate(rows):
            page.locator("#case").select_option(str(i))
            src = json.loads(page.locator("#source").text_content())
            assert src == row
            displayed = json.loads(page.locator("#output").text_content())
            original = outputs[row["id"]]
            for k, value in original.items():
                assert displayed[k] == value
            checks.append(dict(model=model, id=row["id"], exact_source_and_prediction=True))
    page.locator("#case").select_option("0")
    page.locator("#model").select_option("openfly")
    page.screenshot(path=str(root / "final_preview.png"))
    page.set_viewport_size({"width": 640, "height": 900})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors
    browser.close()
(root / "ui_check.json").write_text(
    json.dumps(dict(checks=checks, js_errors=errors, responsive=True), indent=2)
)
print(f"PASS{len(checks)} exact official-source/model-output UI checks")
