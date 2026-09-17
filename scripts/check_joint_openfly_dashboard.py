"""Verify the D144 dashboard against saved predictions, with optional interim checks."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/vla_joint_openfly_20260917"
VIEW = ROOT / "reports/vla_dataset_review_20260916"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-running", action="store_true")
    args = parser.parse_args()
    reports = {
        m: json.loads((REPORT / f"{m}_training_report.json").read_text())
        for m in ("smol256", "smol500", "qwen")
    }
    complete = {m: r for m, r in reports.items() if r["status"] == "complete"}
    if not args.allow_running:
        assert len(complete) == 3, "All three final models are required"
    cases = json.loads((VIEW / "joint_openfly_cases.json").read_text())
    assert len(cases) == 100
    checked = 0
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:8771/joint_openfly.html")
        page.wait_for_function(
            "document.querySelectorAll('#case option').length === 100 && "
            "document.querySelectorAll('#outputs details pre').length >= 2"
        )
        for i, case in enumerate(cases):
            page.select_option("#case", str(i))
            provenance = json.loads(page.locator("#provenance").text_content())
            assert provenance["id"] == case["id"]
            assert provenance["image_sha256"] == case["image_sha256"]
            assert provenance["prompt"] == case["prompt"]
            page.wait_for_function(
                "Array.from(document.querySelectorAll('#images img'))"
                ".every(i => i.complete && i.naturalWidth > 0)"
            )
            assert page.locator("#images img").count() == len(case["previews"])
            shown = page.locator("#outputs details pre").all_text_contents()
            expected = [
                next(x["raw"] for x in r["after"] if x["id"] == case["id"])
                for r in complete.values()
            ]
            assert shown[: len(expected)] == expected, case["id"]
            checked += len(expected)
        for model in complete:
            page.select_option("#model", model)
            assert page.locator("#trainplot svg polyline").count() == 2
            assert page.locator("#valplot svg polyline").count() == 4
            link = page.locator("#flights a")
            assert link.get_attribute("href") == f"{model}_joint_flights.html"
            assert page.request.get("http://127.0.0.1:8771/" + link.get_attribute("href")).ok
        page.select_option("#case", "28")
        page.screenshot(path=str(REPORT / "dashboard_preview.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (
            "Mobile overflow"
        )
        assert not errors, errors
        browser.close()
    result = {
        "final": not args.allow_running,
        "completed_models": list(complete),
        "cases_with_images_and_provenance_checked": len(cases),
        "raw_predictions_checked": checked,
        "loss_series_and_flight_links": True,
        "mobile_no_overflow": True,
        "js_errors": errors,
    }
    name = "dashboard_interim_check.json" if args.allow_running else "dashboard_final_check.json"
    (REPORT / name).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
