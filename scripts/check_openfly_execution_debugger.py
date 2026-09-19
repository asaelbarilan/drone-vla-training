"""Test only the local audit page in a disposable, headless browser profile."""

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_execution_20260919"
URL = "http://127.0.0.1:8771/openfly_execution.html"


def main():
    evidence = json.loads(
        (ROOT / "reports/vla_dataset_review_20260916/openfly_execution.json").read_text()
    )
    failures, checks = [], 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1360, "height": 1100})
            page.on("pageerror", lambda e: failures.append(str(e)))
            page.on(
                "response",
                lambda r: failures.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 else None,
            )
            page.goto(URL)
            page.locator("#route option").nth(4).wait_for(state="attached")
            page.locator("summary").click()
            for i, route in enumerate(evidence["routes"]):
                page.locator("#route").select_option(str(i))
                for version, variant in route["variants"].items():
                    page.locator("#variant").select_option(version)
                    for step in variant["steps"]:
                        page.locator("#step").evaluate(
                            "(el,value)=>{el.value=value;el.dispatchEvent(new Event('input'))}",
                            step["step"],
                        )
                        page.wait_for_function(
                            "document.querySelector('#frame').complete && "
                            "document.querySelector('#frame').naturalWidth > 0"
                        )
                        displayed = json.loads(page.locator("#details").inner_text())
                        assert displayed["step"] == step
                        assert displayed["trajectory"] == route["trajectory"]
                        assert not displayed["renderer_used"]
                        assert str(step["raw_frame"]) in page.locator("#frameLabel").inner_text()
                        assert not re.search(r"NaN|Infinity", page.locator("#map").inner_html())
                        checks += 1
            page.locator("#route").select_option("0")
            page.locator("#variant").select_option("corrected_macro")
            page.locator("#next").click()
            assert page.locator("#step").input_value() == "1"
            page.locator("#previous").click()
            assert page.locator("#step").input_value() == "0"
            page.locator("#play").click()
            page.wait_for_function("Number(document.querySelector('#step').value)>0")
            page.locator("#play").click()
            assert page.locator("#play").inner_text() == "Play recorded steps"
            page.locator("summary").click()
            page.screenshot(path=str(OUT / "debugger_desktop.png"), full_page=True)
            page.goto(URL + "#route=vlnv11&variant=raw_atomic&step=24")
            page.wait_for_function("document.querySelector('#step').value==='24'")
            assert "UNRECOGNIZED" in page.locator("#action").inner_text()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(OUT / "debugger_mobile.png"), full_page=True)
            assert not failures, failures
        finally:
            browser.close()
    result = {
        "displayed_steps_checked": checks,
        "errors": failures,
        "playback_and_buttons": True,
        "deep_link_unknown_label": True,
        "mobile_no_horizontal_overflow": True,
        "browser": "isolated headless Chromium; no user profile",
    }
    (OUT / "debugger_checks.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
