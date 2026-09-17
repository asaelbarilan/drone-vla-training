"""Check exact source evidence and mobile layout in the OpenFly comparison."""

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

out = Path("reports/vla_openfly_20260917")
r = json.loads((out / "training_probe.json").read_text())
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    page = b.new_page(viewport={"width": 1300, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8771/openfly_comparison.html")
    assert page.locator("article").count() == 16
    for i, row in enumerate(r["outputs"]):
        box = page.locator("article").nth(i)
        assert row["decision_id"] in box.inner_text()
        src = box.locator("img").get_attribute("src")
        assert base64.b64decode(src.split(",")[1]) == Path(row["image"]).read_bytes()
        assert json.loads(box.locator("pre").text_content()) == row
    page.screenshot(path=str(out / "comparison_preview.png"))
    page.set_viewport_size({"width": 640, "height": 900})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors
    b.close()
(out / "comparison_ui_check.json").write_text(
    json.dumps(
        dict(exact_image_prompt_native_output_checks=16, js_errors=errors, responsive=True),
        indent=2,
    )
)
print("PASS 16 exact OpenFly image/prompt/native-output checks")
