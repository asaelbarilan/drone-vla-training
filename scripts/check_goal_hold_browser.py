import json
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('reports/recovery_cycle_20260915/goal_hold_component')
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 page=b.new_page(viewport={'width':1550,'height':1000})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 assert page.goto('http://127.0.0.1:8766/goal_hold.html').status==200
 n=page.evaluate('frames.length')
 for i in range(n):
  page.locator('#cursor').fill(str(i));page.locator('#cursor').dispatch_event('input')
  page.wait_for_function('document.getElementById("camera").complete')
  assert page.evaluate('currentFrame.t')==51+i
  if i in [0,n-1]:page.screenshot(path=str(out/f'DASHBOARD_{i}.png'),full_page=True)
 assert not errors
 (out/'BROWSER.json').write_text(json.dumps({'frames_checked':n,'errors':errors},indent=2))
 b.close()
print('Verified',n,'camera and map seeks')
