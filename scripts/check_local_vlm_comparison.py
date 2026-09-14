"""Offline scorer regression and browser QA for D-114; no inference."""

import json

from local_vlm_comparison import OUT, SOURCE, parse, read, score
from playwright.sync_api import sync_playwright

f = read(OUT / "FREEZE.json")
old = read(SOURCE / "RESULTS.json")
for row in old:
    case = next(c for c in f["cases"] if c["id"] == row["case"])
    record = read(SOURCE / (row["case"] + "_" + row["variant"] + ".json"))
    answer, channel = parse(record["reply"], f["variants"][row["variant"]])
    result = score(answer, case, row["variant"])
    assert result["passed"] == row["passed"]
    if "iou" in row:
        assert abs(result["iou"] - row["iou"]) < 1e-12
positive = f["cases"][0]
assert positive["id"] == "visible_target"
exact = dict(evidence="red tower", visible=True, box=[345, 323, 381, 439])
assert score(exact, positive, "bbox")["passed"]
assert not score(dict(exact, box=[600, 600, 700, 700]), positive, "bbox")["passed"]
assert not score(dict(evidence="none", visible=False, box=[0, 0, 0, 0]), positive, "bbox")["passed"]
for box in ([500, 500, 400, 400], [0, 0, 0, 0]):
    try:
        score(dict(exact, box=box), positive, "bbox")
        raise AssertionError("Invalid box was accepted")
    except ValueError:
        pass
answer, channel = parse(
    {"message": {"content": "", "thinking": json.dumps(exact)}}, f["variants"]["bbox"]
)
assert channel == "thinking" and answer == exact
errors = []
folder = OUT / "browser"
folder.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 1050})
    page.on("pageerror", lambda e: errors.append(str(e)))
    response = page.goto("http://127.0.0.1:8766/local_vlm_comparison.html")
    assert response.status == 200
    assert page.locator("#summary tr").count() == 8
    assert page.locator("#model option").count() == 8
    for model in ["gemma", *[m["id"] for m in f["models"]]]:
        page.select_option("#model", model)
        assert page.locator("svg image").count() == 6
        page.locator("article details summary").first.click()
        assert page.locator("article details").first.get_attribute("open") is not None
        assert page.locator("article").count() == 6
    page.select_option("#model", "m3")
    page.screenshot(path=str(folder / "comparison.png"), full_page=True)
    page.locator("#visible_target").screenshot(path=str(folder / "qwen2b_visible.png"))
    page.click("#toggle")
    assert page.locator("body").get_attribute("class") == "hide"
    page.locator("#visible_target").screenshot(path=str(folder / "exact_inputs.png"))
    assert not errors, errors
    browser.close()
(folder / "CHECKS.json").write_text(
    json.dumps(
        dict(
            models=8,
            image_panels_checked=48,
            source_score_regressions=6,
            negative_scoring_checks=True,
            thinking_channel=True,
            overlay_toggle=True,
            prompt_expansion=True,
            errors=errors,
        ),
        indent=2,
    ),
    encoding="utf-8",
)
print("PASS: historical scores, invalid/off-target boxes, channel parsing, 8 selectors, 48 panels")
