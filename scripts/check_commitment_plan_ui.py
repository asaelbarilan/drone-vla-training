"""Browser behavior test for retained-goal plan/source association."""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
s=Path('src/uavlab/analysis/flight_debugger.html').read_text(encoding='utf-8')
fn=re.search(r'function activePlan\(\)\{[^\n]+',s).group()
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page()
 tests=page.evaluate('''(fn)=>{let frame={t:1.5,trace_id:'original'};
 let run={events:[
 {event_type:'plan',t_sim_ns:1e9,trace_id:'original',payload:{feasible:true,tag:'first'}},
 {event_type:'plan',t_sim_ns:2e9,trace_id:'deferred-proposal',payload:{feasible:true,tag:'retained',planner_metadata:{target_commitment_source_id:'original'}}},
 {event_type:'plan',t_sim_ns:3e9,trace_id:'failed-proposal',payload:{feasible:false,tag:'failed',planner_metadata:{target_commitment_source_id:'original'}}}]};
 const current=()=>frame;const activePlan=eval('('+fn+')');let checks=[];
 checks.push(activePlan().payload.tag==='first');frame.t=2.5;
 checks.push(activePlan().payload.tag==='retained');frame.t=3.5;
 checks.push(activePlan().payload.tag==='retained');frame.trace_id='other';
 checks.push(activePlan()===null);frame.trace_id=null;checks.push(activePlan()===null);return checks;}''',fn)
 assert all(tests),tests;b.close()
print('Five active-plan ownership/time checks passed')
