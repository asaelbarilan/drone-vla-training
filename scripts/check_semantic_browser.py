from pathlib import Path
import json
from playwright.sync_api import sync_playwright
out=Path('reports/recovery_cycle_20260915/semantic_probe')
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True)
 page=b.new_page(viewport={'width':1450,'height':950},device_scale_factor=1)
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 response=page.goto('http://127.0.0.1:8766/semantic_progress.html')
 assert response.status==200
 assert page.locator('article').count()==6
 for card in page.locator('article').all():
  card.locator('summary').first.click()
  assert card.locator('img').evaluate_all('(xs)=>xs.every(x=>x.complete&&x.naturalWidth>0)')
 assert page.locator('.fail').count()==2
 assert not errors
 page.screenshot(path=str(out/'DASHBOARD.png'),full_page=True)
 (out/'BROWSER.json').write_text(json.dumps({'cards':6,'expanded_first_details':6,
    'broken_images':0,'page_errors':errors,'identity_failures_displayed':2},indent=2))
 b.close()
print('Six cards and details verified; no image or browser errors')
