"""Saved-pose recovery view probe: no inference, control, or new flight."""
import asyncio
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from uavlab.adapters.gym.deterministic_env import DeterministicEnv
from uavlab.contracts import MissionSpec
from uavlab.core.frame_store import global_store

OUT = Path('reports/qwen4_validation_20260915')
NAME = 'c5_clutter_qwen4_20260915_s1061'


async def main():
    manifest = json.loads((OUT / 'flight/manifest.json').read_text())
    cfg = manifest['environment_config']
    mission = MissionSpec(mission_id='recovery-view-probe', instruction=cfg['instruction'],
                          task_family=cfg['task_family'], success=cfg['params']['success'],
                          constraints=cfg['params']['constraints'])
    env = DeterministicEnv(**cfg['params'])
    await env.reset(mission, 1061)
    rows = json.loads((OUT / 'browser/CHECKS.json').read_text())['checks']
    rows = {r['t']: r for r in rows if r['name'] == NAME}
    target = rows[33.95]['yaw']
    results = []
    sheet = Image.new('RGB', (448, 256), 'white')
    for i, (label, yaw) in enumerate([('actual_39_2', rows[39.2]['yaw']),
                                     ('saved_heading_39_2', target)]):
        env.vehicle.position = np.array(rows[39.2]['position'])
        env.vehicle.velocity = np.zeros(3)
        env.vehicle.yaw = yaw
        env._t_ns = 39_200_000_000
        obs = await env.observe()
        im = global_store().get(obs.rgb.uri).convert('RGB')
        im.save(OUT / f'{label}.png')
        rgb = np.asarray(im)
        mask = (rgb[:, :, 0] > 150) & (rgb[:, :, 1] < 100) & (rgb[:, :, 2] < 100)
        results.append(dict(label=label, position=rows[39.2]['position'],
                            yaw_deg=math.degrees(yaw), red_pixels=int(mask.sum())))
        sheet.paste(im, (224 * i, 30))
        ImageDraw.Draw(sheet).text((224 * i + 5, 5), label, fill='black')
    sheet.save(OUT / 'recovery_views.png')
    result = dict(
        method='Same saved pose/time; actual versus saved recovery yaw. Offline render only.',
                  views=results, target_yaw_deg=math.degrees(target),
                  starting_yaw_deg=math.degrees(rows[37.2]['yaw']),
                  remaining_error_deg=math.degrees(target - rows[39.2]['yaw']),
                  required_turn_deg=math.degrees(target - rows[37.2]['yaw']),
                  maximum_turn_budget_deg=math.degrees((2.0 - 0.25) * 0.4),
                  hold_s=0.25, total_duration_s=2.0, rate_limit_rps=0.4)
    (OUT / 'RECOVERY_COUNTERFACTUAL.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
