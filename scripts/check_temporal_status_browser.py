from pathlib import Path
import json
from playwright.sync_api import sync_playwright
out=Path('reports/recovery_cycle_20260915/status_probe')
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 page=b.new_page(viewport={'width':1500,'height':950})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 assert page.goto('http://127.0.0.1:8766/temporal_status.html').status==200
 assert page.locator('article').count()==3
 for card in page.locator('article').all():
  for summary in card.locator('summary').all():summary.click()
 assert page.locator('img').evaluate_all('(xs)=>xs.every(x=>x.complete&&x.naturalWidth>0)')
 assert not errors
 page.screenshot(path=str(out/'DASHBOARD.png'),full_page=True)
 (out/'BROWSER.json').write_text(json.dumps({'cards':3,'details_expanded':6,'page_errors':errors,'broken_images':0}))
 b.close()
