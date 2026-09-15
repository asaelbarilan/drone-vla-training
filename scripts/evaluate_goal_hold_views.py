import asyncio,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import MissionSpec
out=Path('reports/recovery_cycle_20260915/goal_hold_component');r=json.loads((out/'RESULT.json').read_text());f=json.loads((out/'FREEZE.json').read_text());cfg=f['manifest']['environment_config'];mission=MissionSpec(mission_id='eval-only',instruction=cfg['instruction'],task_family=cfg['task_family'],success=cfg['params']['success'],constraints=cfg['params']['constraints']);env=DeterministicEnv(**cfg['params']);asyncio.run(env.reset(mission,1061));goal=env.goal
rows=[]
for x in r['rows']:
 if 'image' not in x:continue
 im=np.asarray(Image.open(out/x['image']).convert('RGB')).astype(int);count=int(((im[:,:,0]>150)&(im[:,:,0]>im[:,:,1]*1.5)&(im[:,:,0]>im[:,:,2]*1.5)).sum());pos=np.array([x['position'][k] for k in ['x','y','z']]);rows.append(dict(t=x['t'],red_pixel_count=count,distance_to_truth_m=float(np.linalg.norm(pos-goal))))
(out/'VISUAL_EVALUATION.json').write_text(json.dumps(dict(goal_truth_for_evaluation_only=goal.tolist(),frames=rows),indent=2))
selected=[0,4,8,12,16,20];sheet=Image.new('RGB',(672,500),'white');d=ImageDraw.Draw(sheet)
for i,j in enumerate(selected):
 frame=[x for x in r['rows'] if 'image' in x][j];im=Image.open(out/frame['image']);x=(i%3)*224;y=(i//3)*250;sheet.paste(im,(x,y+25));d.text((x+3,y+4),f"t={frame['t']:.0f}s",fill='black')
sheet.save(out/'CAMERA_SEQUENCE.png');print(json.dumps(rows,indent=2))
