"""Read public resource metadata only; never fetch weights or datasets."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DEST = Path(__file__).resolve().parent
PROJECTS = {
 'openfly':'https://shailab-ipec.github.io/openfly/',
 'cognitive':'https://cognitivedrone.github.io/', 'racevla':'https://racevla.github.io/',
 'autofly':'https://xiaolousun.github.io/AutoFly',
 'flight':'https://buaa-colalab.github.io/FLIGHT/',
 'worldvln':'https://embodiedcity.github.io/WorldVLN/',
 'uavtrack':'https://flying-intelligence.github.io/',
 'gradnav':'https://qianzhong-chen.github.io/gradnavpp.github.io/',
 'uavflow':'https://prince687028.github.io/UAV-Flow',
 'huge':'https://jingyu198.github.io/HUGE_Bench/'
}
REPOS = ['shailab-ipec/OpenFly','SHAILAB-IPEC/OpenFly-Platform',
 'SerValera/docker_CognitiveDrone_DataCollector','SerValera/RaceVLA',
 'xiaolousun/AutoFly-VLA','XuPeng23/AeroVLA','buaa-colalab/FLIGHT',
 'EmbodiedCity/WorldVLN.code','chenjinyubuaa/AerialVLA','buaa-colalab/UAV-Flow',
 'valyentinee/IndoorUAV-Agent','Qianzhong-Chen/grad_nav']
HF = [('model','IPEC-COMMUNITY/openfly-agent-7b'),('dataset','IPEC-COMMUNITY/OpenFly'),
 ('dataset','IPEC-COMMUNITY/OpenFly-rlds'),('dataset','ArtemLykov/cognitiveDrone_dataset'),
 ('model','SerValera2/RaceVLA_models'),('dataset','SerValera2/RaceVLA_dataset'),
 ('model','xlsun/AutoFly'),('model','XuPeng23/AerialVLA'),
 ('dataset','jujujulien/FLIGHT'),('dataset','UPB-RAT-VLA/Exp2VLA-MultiObject-v1'),
 ('dataset','wangxiangyu0814/UAV-Flow'),('model','EmbodiedCity/WorldVLN'),('model','wangxiangyu0814/OpenVLA-UAV')]

def inspect_project(kv):
 key,url=kv; result={'kind':'project','id':key,'url':url}
 try:
  r=requests.get(url,timeout=30);result['status']=r.status_code
  soup=BeautifulSoup(r.text,'html.parser')
  result['resource_links']=list(dict.fromkeys(urljoin(r.url,a['href']) for a in soup.select('a[href]') if any(s in a['href'] for s in ['github.com','huggingface.co','huggingface.com','drive.google','pan.baidu'])))
 except requests.RequestException as e: result['error']=str(e)
 return result

def inspect_repo(name):
 url='https://api.github.com/repos/'+name; result={'kind':'repository','id':name,'url':'https://github.com/'+name}
 try:
  r=requests.get(url,timeout=30);d=r.json();result.update(status=r.status_code,license=(d.get('license') or {}).get('spdx_id'),branch=d.get('default_branch'),pushed_at=d.get('pushed_at'))
  if r.ok:
   t=requests.get('https://raw.githubusercontent.com/'+name+'/'+d['default_branch']+'/README.md',timeout=30)
   import re
   result['readme_resource_links']=list(dict.fromkeys(re.findall(r'https?://(?:huggingface.co|drive.google.com|github.com)/[^\s)<>]+',t.text)))
   result['readme_download_mentions']=[l for l in t.text.splitlines() if any(w in l.lower() for w in ['weight','checkpoint','dataset','license'])][:20]
 except requests.RequestException as e:result['error']=str(e)
 return result

def inspect_hf(item):
 kind,name=item;u='https://huggingface.co/api/'+('models/' if kind=='model' else 'datasets/')+name
 result={'kind':kind,'id':name,'url':u}
 try:
  r=requests.get(u,timeout=30);d=r.json();result.update(status=r.status_code,sha=d.get('sha'),license=(d.get('cardData') or {}).get('license'),gated=d.get('gated'),file_count=len(d.get('siblings',[])),file_sample=[f['rfilename'] for f in d.get('siblings',[])][:20],last_modified=d.get('lastModified'))
 except requests.RequestException as e:result['error']=str(e)
 return result

if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=5) as ex:
  rows=list(ex.map(inspect_project,PROJECTS.items()))+list(ex.map(inspect_repo,REPOS))+list(ex.map(inspect_hf,HF))
 (DEST/'resource_checks.json').write_text(json.dumps({'checked':'2026-09-19','scope':'Metadata and README checks, no model execution or data downloads; missing license is unresolved, not permission.','resources':rows},indent=2),encoding='utf-8')
 for r in rows:
  print(r['kind'],r['id'],r.get('status'),r.get('license'),r.get('resource_links',r.get('readme_resource_links',[])))
