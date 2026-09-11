"""Browser interaction smoke check; only reads an already exported debugger.

Requires optional playwright and installed Edge. No model or simulator calls.
"""
import argparse
import json

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--screenshot", default="reports/debugger/preview.png")
    args = parser.parse_args()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1050})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.url, wait_until="load")
        assert not page.locator("#error").is_visible()
        assert page.locator("#drone").evaluate("e=>e.complete&&e.naturalWidth>0")
        page.locator("#filter").select_option("monitor")
        page.locator(".decision").first.click()
        assert "Monitor" in page.locator("#selection").inner_text()
        assert "available 1.20 s" in page.locator("#selection").inner_text()
        assert "1.20 /" in page.locator("#time").inner_text()
        assert "at 0.00 s" in page.locator("#sourceCaption").inner_text()
        page.locator("#atSource").click()
        assert "0.00 /" in page.locator("#time").inner_text()
        page.locator('[data-tab="flow"]').click()
        assert "Inference completed" in page.locator("#flowSteps").inner_text()
        page.locator('[data-tab="sourcecode"]').click()
        assert "OnFlyMonitor.assess" in page.locator("#codePath").inner_text()
        page.locator("#run").select_option(index=2)
        assert page.locator("#outcome").inner_text() == "Completed"
        page.locator("#scrub").fill(page.locator("#scrub").get_attribute("max"))
        assert page.locator("#distance").inner_text() == "0.52 m"
        page.locator("#run").select_option(index=0)
        page.locator("#play").click()
        page.wait_for_function("!document.querySelector('#time').textContent.startsWith('0.00 /')")
        page.locator("#play").click()
        page.locator("#note").fill("Expected forward motion; inspect this capture.")
        with page.expect_download() as info:
            page.locator("#saveNote").click()
        note = json.loads(info.value.path().read_text())
        assert note["run"] == "c5_guarded_monitor_20260911_s1061"
        assert note["note"].startswith("Expected forward")
        page.locator("#note").fill("")
        page.locator("#filter").select_option("all")
        page.locator("#scrub").fill("800")
        page.locator('[data-tab="evidence"]').click()
        page.screenshot(path=args.screenshot, full_page=True)
        page.set_viewport_size({"width": 640, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        assert not errors, errors
        browser.close()
    print("PASS: source-time alignment, role filter, flow/code tabs, run switching, "
          "terminal frame, playback, note download, responsive layout; no JS errors")


if __name__ == "__main__":
    main()
