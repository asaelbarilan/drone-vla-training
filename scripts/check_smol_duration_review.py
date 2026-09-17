"""Browser evidence check of every fixed generation probe and intervention."""

import base64
import io
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

root = Path("reports/vla_smol_duration_20260917")
data = Path("D:/drone_vla_pilot/data/local_mixed_20260917_v1")
manifest = json.loads((data / "manifest.json").read_text())
rows = {
    r["decision_id"]: r
    for r in [json.loads(s) for s in (data / "index.jsonl").read_text().splitlines()]
}
models = [m for m in ("smol256", "smol500") if (root / f"{m}_duration_report.json").exists()]
buf = io.BytesIO()
Image.new("RGB", (224, 224), (127, 127, 127)).save(buf, format="PNG")
blank = buf.getvalue()
checks = []
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1050})
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8771/smol_duration.html")
    page.get_by_text("Exact model text prompt", exact=True).click()
    assert page.locator("#model option").count() == len(models)
    assert page.locator("#sample option").count() == 28
    for model in models:
        report = json.loads((root / f"{model}_duration_report.json").read_text())
        report["before"] = report["generation_checkpoints"]["400"]
        page.locator("#model").select_option(model)
        for phase in ("before", "after", "blank_image", "blank_instruction"):
            records = (
                report[phase]
                if phase in ("before", "after")
                else [r for r in report["interventions"] if r["intervention"] == phase]
            )
            page.locator("#phase").select_option(phase)
            for r in records:
                index = manifest["generation_eval_ids"].index(r["decision_id"])
                page.locator("#sample").select_option(str(index))
                row = rows[r["decision_id"]]
                assert page.locator("#raw").inner_text() == r["raw"]
                assert json.loads(page.locator("#target").inner_text()) == r["target"]
                image = base64.b64decode(page.locator("#image").get_attribute("src").split(",")[1])
                assert image == (
                    blank
                    if phase == "blank_image"
                    else (Path(row["data_root"]) / row["images"]["mosaic"]).read_bytes()
                )
                expected_prompt = (
                    row["prompt"].replace(row["instruction"], "Perform the requested task.", 1)
                    if phase == "blank_instruction"
                    else row["prompt"]
                )
                assert page.locator("#prompt").text_content() == expected_prompt, (
                    model,
                    phase,
                    r["decision_id"],
                )
                if r["valid"]:
                    action = json.loads(page.locator("#physical").inner_text())
                    assert action["yaw_clockwise_rps"] == (r["parsed"]["yaw_cw_bin"] - 32) * 3 / 64
                    assert action["forward_mps"] == (r["parsed"]["forward_bin"] - 32) * 10 / 64
                    assert action["mission_stop"] == r["parsed"]["stop"]
                execution_file = root / f"{model}_visual_execution.json"
                if phase == "after" and row["task_group"] == "visual" and execution_file.exists():
                    execution = json.loads(execution_file.read_text())
                    segment = next(x for x in execution["segments"] if x["id"] == r["decision_id"])
                    if segment["outcome"] == "saved_prediction_executed":
                        shown = base64.b64decode(
                            page.locator("#afterImage").get_attribute("src").split(",")[1]
                        )
                        assert (
                            shown
                            == (
                                Path(execution["output_root"]) / r["decision_id"] / "after.png"
                            ).read_bytes()
                        )
                checks.append(
                    dict(
                        model=model,
                        phase=phase,
                        id=r["decision_id"],
                        exact_source_and_response=True,
                    )
                )
    page.locator("#model").select_option("smol256")
    page.locator("#phase").select_option("after")
    page.locator("#sample").select_option("0")
    page.screenshot(path=str(root / "prediction_preview.png"), full_page=True)
    page.set_viewport_size({"width": 640, "height": 900})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    page.locator("#lossSection summary").click()
    assert page.locator("#lossPlot").is_visible()
    assert (
        base64.b64decode(page.locator("#lossPlot").get_attribute("src").split(",", 1)[1])
        == (root / "duration_loss_curves.png").read_bytes()
    )
    page.locator("#taskSection summary").click()
    assert page.locator("#taskPlot").is_visible()
    assert (
        base64.b64decode(page.locator("#taskPlot").get_attribute("src").split(",", 1)[1])
        == (root / "duration_task_losses.png").read_bytes()
    )
    page.locator("#fullSection summary").click()
    assert page.locator("#fullPlot").is_visible()
    assert (
        base64.b64decode(page.locator("#fullPlot").get_attribute("src").split(",", 1)[1])
        == (root / "duration_full_loss_curves.png").read_bytes()
    )
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors
    browser.close()
(root / "prediction_ui_check.json").write_text(
    json.dumps(dict(checks=checks, js_errors=errors, responsive=True), indent=2)
)
print(f"PASS {len(checks)} source/image/prompt/response/decoded-action checks")
