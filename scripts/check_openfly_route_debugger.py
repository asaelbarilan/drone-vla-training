"""Check every frame/decision/input and desktop/mobile rendering of the debugger."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/vla_openfly_routes_20260919"
URL = "http://127.0.0.1:8771/openfly_routes.html"


def main():
    data = json.loads(
        (ROOT / "reports/vla_dataset_review_20260916/openfly_routes.json").read_text()
    )
    errors = []
    count = 0
    frames = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "response",
            lambda r: errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None,
        )
        page.goto(URL)
        page.wait_for_selector("#predictions tr")
        for i, route in enumerate(data["routes"]):
            page.select_option("#route", str(i))
            for f in route["frames"]:
                page.locator("#seek").evaluate(
                    '(e,value)=>{e.value=value;e.dispatchEvent(new Event("input"))}', f["index"]
                )
                assert page.locator("#camera").get_attribute("src") == f["preview"]
                frames += 1
            for j, decision in enumerate(route["decisions"]):
                page.locator(f'#timeline button[data-index="{j}"]').click()
                for variant, pred in decision["predictions"].items():
                    page.select_option("#variant", variant)
                    actual = json.loads(page.locator("#raw").text_content())
                    assert actual == pred
                    aid = pred.get("strict_decoded", {}).get("action_id", pred.get("action_id"))
                    assert page.locator("#predictions tr.active td").nth(1).text_content() == data[
                        "action_names"
                    ].get(str(aid), "INVALID vector")
                    expected = pred.get(
                        "input_previews",
                        decision["predictions"].get("prior_adjacent", {}).get("input_previews"),
                    )
                    assert (
                        page.locator("#inputs img").evaluate_all(
                            '(els)=>els.map(e=>e.getAttribute("src"))'
                        )
                        == expected
                    )
                    count += 1
        page.goto(URL + "#route=packed_vlnv1&frame=1&variant=rlds_stored_raw")
        page.wait_for_function('document.querySelector("#seek").value==="1"')
        assert page.locator("#future").text_content()
        page.screenshot(path=str(OUT / "debugger_desktop.png"), full_page=True)
        page.locator("#play").click()
        page.wait_for_function('Number(document.querySelector("#seek").value)>1')
        page.locator("#play").click()
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(OUT / "debugger_mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
        assert page.locator("img").evaluate_all("(els)=>els.every(e=>e.complete&&e.naturalWidth>0)")
        browser.close()
    assert not errors, errors
    result = dict(
        routes=len(data["routes"]),
        frames_checked=frames,
        displayed_predictions_checked=count,
        errors=errors,
        playback=True,
        deeplink=True,
        mobile=True,
    )
    (OUT / "browser_audit.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
