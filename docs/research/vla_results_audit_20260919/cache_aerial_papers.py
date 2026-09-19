import concurrent.futures,json,hashlib,re
from pathlib import Path
import fitz,requests
ROOT=Path('.local/drone_vla_papers_20260919')
ROOT.mkdir(parents=True,exist_ok=True)
PAPERS = {
    "openfly": "2502.18041v7",
    "cognitive": "2503.01378v1",
    "racevla": "2503.02572v1",
    "autofly": "2602.09657v1",
    "aerialvla": "2603.14363v1",
    "spatialfly": "2603.21046v2",
    "longfly": "2512.22010v1",
    "flight": "2606.06836v1",
    "worldvln": "2605.15964v1",
    "imagineuav": "2606.01205v2",
    "exp2vla": "2607.03146v1",
    "fsdvln": "2607.08359v1",
    "uavtrack": "2604.02241v2",
    "litevla": "2605.00884v2",
    "aerialvla_dialogue": "https://ojs.aaai.org/index.php/AAAI/article/download/38878/42840",
    "uavflow": "2505.15725v2",
    "indooruav": "2512.19024v1",
    "aerialvln": "2308.06735v1",
    "onfly": "2603.10682v1",
    "vlfly": "2506.10756v1",
    "gradnav": "2506.14009v2",
    "seepointfly": "2509.22653v1",
    "fly0": "2602.15875v2",
    "traveluav": "2410.07087v2",
    "cosflytrack": "2605.17776v2",
    "uavvla": "2501.05014v2",
    "semanticdecision": "2608.09564v1",
    "vlaan": "2512.15258v2",
    "huge": "2603.19822v4",
    "singer": "2509.18610v1",
    "airvla": "2606.12859v1"
}
def fetch(kv):
 k,v=kv; url=v if v.startswith('https:') else 'https://arxiv.org/pdf/'+v
 try:
  r=requests.get(url,timeout=75);r.raise_for_status()
  if not r.content.startswith(b'%PDF'):return {'id':k,'url':url,'status':'not_pdf'}
  p=ROOT/(k+'.pdf');p.write_bytes(r.content);d=fitz.open(p)
  t='\n'.join('\n=== PAGE '+str(i+1)+' ===\n'+pg.get_text(sort=True) for i,pg in enumerate(d))
  (ROOT/(k+'.txt')).write_text(t,encoding='utf-8')
  links=sorted(set(l['uri'] for pg in d for l in pg.get_links() if 'uri' in l and any(x in l['uri'] for x in ['github','huggingface','project'])))
  ver=re.search(r'arXiv:\s*(\d{4}\.\d{4,5}v\d+)',t)
  return {'id':k,'url':url,'version':ver.group(1) if ver else None,'pages':len(d),'sha256':hashlib.sha256(r.content).hexdigest(),'metadata':d.metadata,'links':links}
 except Exception as e:return {'id':k,'url':url,'error':str(e)}
if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:out=list(pool.map(fetch,PAPERS.items()))
    (ROOT/'manifest.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    for x in out: print(x['id'],x.get('version'),x.get('pages',x.get('error',x.get('status'))))
