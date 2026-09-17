# ruff: noqa: E501
"""Verify all official-TRAIN source rows and playback against the frozen index."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def main():
    rows = [
        json.loads(x)
        for x in Path("D:/drone_vla_pilot/data/openfly_train_pilot_20260917/index.jsonl")
        .read_text()
        .splitlines()
    ]
    out = Path("reports/vla_openfly_train_20260917")
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1400, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto("http://127.0.0.1:8771/openfly_training.html")
        assert await page.locator("#trajectory option").count() == 22
        for row in rows:
            await page.select_option("#trajectory", row["trajectory"])
            await page.locator("#step").evaluate(
                '(e,i)=>{e.value=i;e.dispatchEvent(new Event("input"))}', row["index"]
            )
            assert json.loads(await page.locator("#source").text_content()) == row
            await page.wait_for_function(
                "document.querySelector('#frame').complete && document.querySelector('#frame').naturalWidth>0"
            )
        await page.select_option("#trajectory", rows[0]["trajectory"])
        await page.locator("#play").click()
        await page.wait_for_timeout(800)
        assert await page.locator("#step").input_value() != "0"
        await page.locator("#play").click()
        await page.screenshot(path=str(out / "source_viewer.png"), full_page=True)
        assert not errors, errors
        await browser.close()
    (out / "viewer_audit.json").write_text(
        json.dumps(
            dict(
                source_rows_verified=len(rows),
                trajectories=22,
                playback_verified=True,
                browser_errors=errors,
            ),
            indent=2,
        )
    )
    print("429 source rows,22 trajectories and playback verified")


if __name__ == "__main__":
    asyncio.run(main())
