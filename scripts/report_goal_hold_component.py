"""Interactive evidence viewer for the bounded accepted-goal execution fixture."""
import base64
import json
import math
from pathlib import Path

from scripts.probe_recovery_context import read, write
from scripts.probe_goal_hold_component import OUT, ROOT

r=read(OUT/'RESULT.json')
g=r['goal']['target']
events=[json.loads(x) for x in (ROOT/'events.jsonl').read_text().splitlines()]
baseline=[]
for e in events:
 if e['event_type']=='control' and 51e9<=e['t_sim_ns']<=71e9:
  p=e['payload'];pos=dict(x=p['position_x'],y=p['position_y'],z=p['position_z'])
  baseline.append(dict(t=e['t_sim_ns']/1e9,position=pos,
     distance_to_stored_goal_m=math.dist([pos[k] for k in ['x','y','z']],[g[k] for k in ['x','y','z']])))
for row in r['rows']:
 if 'image' in row:
  row['rgb']='data:image/png;base64,'+base64.b64encode((OUT/row['image']).read_bytes()).decode()
r['baseline']=baseline
r['source_rgb']='data:image/png;base64,'+base64.b64encode((OUT/'original_target_input.png').read_bytes()).decode()
write(OUT/'COMPARISON.json',dict(original_at_71s_distance_m=baseline[-1]['distance_to_stored_goal_m'],
 original_closest_distance_m=min(x['distance_to_stored_goal_m'] for x in baseline),
 component_final_distance_m=r['final_distance_m'],component_closest_distance_m=r['closest_distance_m'],
 component_elapsed_s=r['elapsed_s']))
page='''<!doctype html><html><head><meta charset="utf-8"><title>Accepted goal: execution hold</title>
<style>body{background:#0c1521;color:#d9e5f3;font:16px system-ui;margin:24px;max-width:1550px}
h1{font-size:26px}.grid{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:16px}
article{background:#162638;border:1px solid #334a60;border-radius:10px;padding:16px}
h2{font-size:18px}img{width:100%;max-width:350px;image-rendering:pixelated}canvas{width:100%;height:auto}
input{width:80%}pre{white-space:pre-wrap;font-size:13px}small{color:#9ab1c7}
@media(max-width:950px){.grid{grid-template-columns:1fr}}</style></head><body>
<h1>Can SUPER finish the last accepted target waypoint?</h1>
<p id="summary"></p><p><b>Execution component only:</b> saved51s waypoint retained for at most20s,
common planner replanned at1Hz; no VLM, monitor, or replacement goals. No semantic freshness renewal
is claimed. Intermediate waypoint completion is not mission success.</p>
<p>Prefix verified:1,020 control poses,61 planner outputs, and first branch command.
Cyan: held-goal execution; amber: original flight after51s; purple: stored waypoint.
Obstacle geometry is debugger truth only and does not steer the component.</p>
<div class="grid"><article><h2>Flight map</h2><canvas id="map" width="540" height="420"></canvas></article>
<article><h2>Component camera</h2><img id="camera"><p id="time"></p></article>
<article><h2>Actual VLM input that produced the stored goal</h2><img id="source">
<p>Source observation1000,49.95s; decision accepted51s. The selected pixel was on the red target.</p></article></div>
<p><input id="cursor" type="range" min="0" step="1" value="0"><span id="distance"></span></p>
<article><h2>Latest common-planner result</h2><pre id="plan"></pre></article>
<script>const data=DATA;
const frames=data.rows.filter(x=>x.rgb),slider=document.getElementById('cursor');
slider.max=frames.length-1;document.getElementById('source').src=data.source_rgb;
document.getElementById('summary').textContent=`Outcome: ${data.outcome}. Stored-goal distance ${data.start_distance_m.toFixed(2)} → ${data.final_distance_m.toFixed(2)}m in ${data.elapsed_s.toFixed(2)}s. Collisions: ${data.collision_count}.`;
const c=document.getElementById('map'),ctx=c.getContext('2d'),g=data.goal.target;
let pts=[...data.rows,...data.baseline].map(x=>x.position).concat([g]);
let loX=Math.min(...pts.map(x=>x.x))-4,hiX=Math.max(...pts.map(x=>x.x))+4;
let loY=Math.min(...pts.map(x=>x.y))-4,hiY=Math.max(...pts.map(x=>x.y))+4;
let scale=Math.min(500/(hiX-loX),380/(hiY-loY));
const xy=p=>[20+(p.x-loX)*scale,400-(p.y-loY)*scale];
function path(rows,color,t){ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();let started=false;
 for(const r of rows){if(r.t>t)break;let p=xy(r.position);if(!started){ctx.moveTo(...p);started=true}else ctx.lineTo(...p)}ctx.stroke()}
function render(i){const f=frames[i];ctx.clearRect(0,0,540,420);ctx.fillStyle='#1e3449';ctx.strokeStyle='#657b8c';
for(const o of data.obstacles){let p=xy({x:o.center[0]-o.half[0],y:o.center[1]+o.half[1]});
ctx.fillRect(p[0],p[1],o.half[0]*2*scale,o.half[1]*2*scale);ctx.strokeRect(p[0],p[1],o.half[0]*2*scale,o.half[1]*2*scale)}
path(data.baseline,'#eebc6b',f.t);path(data.rows,'#59d7dd',f.t);
ctx.fillStyle='#bc9eec';ctx.beginPath();ctx.arc(...xy(g),5,0,Math.PI*2);ctx.fill();
ctx.strokeStyle='#bc9eec';ctx.beginPath();ctx.arc(...xy(g),data.goal.tolerance_m*scale,0,Math.PI*2);ctx.stroke();
ctx.fillStyle='#59d7dd';ctx.beginPath();ctx.arc(...xy(f.position),5,0,Math.PI*2);ctx.fill();
document.getElementById('camera').src=f.rgb;document.getElementById('time').textContent=`t=${f.t.toFixed(2)}s; z=${f.position.z.toFixed(2)}m`;
document.getElementById('distance').textContent=`${f.distance_to_stored_goal_m.toFixed(2)}m from stored goal`;
const ps=data.plans.filter(p=>p.t<=f.t);document.getElementById('plan').textContent=ps.length?JSON.stringify(ps.at(-1),null,2):'Original51s plan (matched)';
window.currentFrame=f;}
slider.addEventListener('input',()=>render(+slider.value));render(0);
</script></body></html>'''.replace('DATA',json.dumps(r,separators=(',',':')))
Path('reports/debugger/goal_hold.html').write_text(page,encoding='utf-8')
print(json.dumps(read(OUT/'COMPARISON.json'),indent=2))
