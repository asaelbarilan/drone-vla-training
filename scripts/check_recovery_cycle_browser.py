"""Visually review saved recovery replays in Edge; no live inference."""
import argparse
import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('number', type=int)
args = parser.parse_args()
out = Path(f'reports/recovery_cycle_20260915/cycle{args.number}/browser')
out.mkdir(parents=True, exist_ok=True)
errors = []
checks = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1600, 'height':1050})
    page.on('pageerror', lambda e:errors.append(str(e)))
    page.goto(f'http://127.0.0.1:8766/recovery_cycle{args.number}.html')
    page.wait_for_function('typeof run !== "undefined" && run && run.frames.length > 0')
    for i in range(2):
        page.locator('#run').select_option(str(i))
        page.locator('#follow').check()
        for t in [0, 33.95, 37.2, 39.2, 39.25, 40, 41, 45, 60, 90]:
            page.evaluate('(t)=>{pause();seek(nearest(t),true)}', t)
            page.wait_for_function('document.getElementById("drone").complete')
            row = page.evaluate('({...current(), name:run.name})')
            rgb = row.pop('rgb', None)
            checks.append(row)
            if i == 1:
                page.screenshot(path=str(out/f't{t}.png'))
                if rgb:
                    (out/f'rgb_t{t}.png').write_bytes(base64.b64decode(rgb.split(',')[1]))
        page.evaluate('()=>{pause();seek(nearest(33.95),true)}')
        before = page.evaluate('current().t')
        page.locator('#play').click()
        page.wait_for_function('(t)=>current().t > t', arg=before)
        page.evaluate('pause()')
    browser.close()
assert not errors, errors
(out/'CHECKS.json').write_text(json.dumps(dict(checks=checks, playbacks=2, errors=errors),
                                         indent=2), encoding='utf-8')
print(f'{len(checks)} seeks, 2 playbacks, no JS errors')
