"""Build the inline held-out trajectory-map visualization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from export_end_map_data import export


TEMPLATE = r'''<div class="end-maps">
  <style>
    .end-maps { color: var(--foreground); font-family: var(--font-sans); padding: 8px 2px 2px; }
    .end-maps * { box-sizing: border-box; }
    .head { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin-bottom:12px; }
    .head h2 { margin:0 0 3px; font-size:19px; font-weight:650; letter-spacing:-.02em; }
    .sub { color:var(--muted-foreground); font-size:12px; line-height:1.4; }
    .seed-control { display:flex; gap:6px; flex:0 0 auto; }
    .seed-control .btn { min-width:58px; }
    .legend { display:flex; gap:14px; align-items:center; flex-wrap:wrap; color:var(--muted-foreground); font-size:11px; margin:0 0 10px; }
    .legend span { display:inline-flex; align-items:center; gap:5px; }
    .dot { width:9px; height:9px; display:inline-block; border-radius:50%; border:1.5px solid var(--foreground); }
    .start-dot { background:var(--foreground); }
    .goal-dot { border-color:var(--green); background:transparent; }
    .end-dot { background:var(--red); border-color:var(--red); }
    .obstacle-key { width:10px; height:8px; background:var(--muted); border:1px solid var(--border); display:inline-block; }
    .maps { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
    .map-panel { min-width:0; border:1px solid var(--border); border-radius:8px; overflow:hidden; background:color-mix(in srgb, var(--card) 48%, transparent); }
    .panel-head { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 9px 6px; }
    .arch { font-size:13px; font-weight:650; }
    .verdict { font-size:10px; padding:2px 6px; border-radius:999px; border:1px solid var(--border); color:var(--muted-foreground); }
    .verdict.success { color:var(--green); border-color:var(--green); }
    .verdict.collision { color:var(--red); border-color:var(--red); }
    .plot { width:100%; height:270px; }
    .plot svg { display:block; width:100%; height:100%; }
    .stats { display:grid; grid-template-columns:repeat(3,1fr); gap:4px; padding:7px 9px 9px; border-top:1px solid var(--border); }
    .metric { min-width:0; }
    .metric b { display:block; font-size:12px; font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .metric small { color:var(--muted-foreground); font-size:9px; text-transform:uppercase; letter-spacing:.04em; }
    .note { margin-top:9px; color:var(--muted-foreground); font-size:10px; line-height:1.45; }
    @media (max-width: 900px) { .maps { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media (max-width: 520px) { .head { align-items:flex-start; flex-direction:column; } .maps { grid-template-columns:1fr; } .map-panel { max-width:none; } }
  </style>
  <div class="head">
    <div>
      <h2>Held-out end maps</h2>
      <div class="sub">Local deterministic simulator · Gemma depth + semantic confirmation gate · identical scene within each seed</div>
    </div>
    <div class="seed-control" role="group" aria-label="Choose held-out seed">
      <button class="btn" data-seed="1" aria-pressed="true">Seed 1</button>
      <button class="btn" data-seed="2" aria-pressed="false">Seed 2</button>
      <button class="btn" data-seed="3" aria-pressed="false">Seed 3</button>
    </div>
  </div>
  <div class="legend" aria-label="Map legend">
    <span><i class="dot start-dot"></i>start</span><span><i class="dot goal-dot"></i>goal + 2 m success radius</span>
    <span><i class="dot end-dot"></i>end</span><span><i class="obstacle-key"></i>obstacle footprint</span>
  </div>
  <div class="maps"></div>
  <div class="note">C2 is the simulated-perception reference. C2G, C3G, and C6G use Gemma 3 4B vision. Paths are reconstructed from the logged 20 Hz control commands; end positions and verdicts come directly from each episode result.</div>
  <script>
  (() => {
    const DATA = __DATA__;
    const ORDER = ['c2','c2g','c3g','c6g'];
    const LABEL = {c2:'C2 reference',c2g:'C2G Gemma',c3g:'C3G + verifier',c6g:'C6G recovery'};
    const SERIES = {c2:'var(--viz-series-1)',c2g:'var(--viz-series-2)',c3g:'var(--viz-series-3)',c6g:'var(--viz-series-4)'};
    const root = document.currentScript.closest('.end-maps');
    const maps = root.querySelector('.maps');
    let selectedSeed = 1;
    let resizeFrame = 0;

    const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const episode = (arch, seed) => DATA.episodes.find(d => d.architecture === arch && d.seed === seed);
    const pointsForSeed = seed => {
      const scene = DATA.scenes[String(seed)];
      const points = [[0,0], scene.goal, ...scene.subgoals];
      scene.obstacles.forEach(o => { points.push([o.center[0]-o.half[0],o.center[1]-o.half[1]],[o.center[0]+o.half[0],o.center[1]+o.half[1]]); });
      ORDER.forEach(a => points.push(...episode(a,seed).path));
      return points;
    };
    const bounds = seed => {
      const pts = pointsForSeed(seed); let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
      pts.forEach(([x,y]) => { minX=Math.min(minX,x); maxX=Math.max(maxX,x); minY=Math.min(minY,y); maxY=Math.max(maxY,y); });
      const span = Math.max(maxX-minX,maxY-minY,20) * 1.18;
      return {cx:(minX+maxX)/2, cy:(minY+maxY)/2, span};
    };
    const statusClass = d => d.success ? 'success' : d.collided ? 'collision' : '';
    const statusText = d => d.success ? 'SUCCESS' : d.collided ? 'COLLISION' : 'TIMEOUT';

    function shell() {
      maps.innerHTML = ORDER.map(a => {
        const d = episode(a,selectedSeed);
        return `<section class="map-panel" data-arch="${a}"><div class="panel-head"><span class="arch">${LABEL[a]}</span><span class="verdict ${statusClass(d)}">${statusText(d)}</span></div><div class="plot"></div><div class="stats"><span class="metric"><b>${d.distanceToGoal.toFixed(1)} m</b><small>to goal</small></span><span class="metric"><b>${d.pathLength.toFixed(1)} m</b><small>path</small></span><span class="metric"><b>${d.flightTime.toFixed(1)} s</b><small>flight</small></span></div></section>`;
      }).join('');
      drawAll();
    }

    function draw(panel) {
      const arch = panel.dataset.arch;
      const d = episode(arch, selectedSeed);
      const scene = DATA.scenes[String(selectedSeed)];
      const box = bounds(selectedSeed);
      const host = panel.querySelector('.plot');
      const w = Math.max(210, Math.floor(host.getBoundingClientRect().width));
      const h = 270, pad = 14, scale = Math.min((w-2*pad)/box.span,(h-2*pad)/box.span);
      const px = x => w/2 + (x-box.cx)*scale;
      const py = y => h/2 - (y-box.cy)*scale;
      const path = d.path.map((p,i) => `${i?'L':'M'}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join(' ');
      const obstacles = scene.obstacles.map(o => `<rect x="${px(o.center[0]-o.half[0]).toFixed(1)}" y="${py(o.center[1]+o.half[1]).toFixed(1)}" width="${(2*o.half[0]*scale).toFixed(1)}" height="${(2*o.half[1]*scale).toFixed(1)}" rx="1" fill="var(--muted)" stroke="var(--border)"><title>Obstacle footprint</title></rect>`).join('');
      const subgoals = scene.subgoals.map((p,i) => `<circle cx="${px(p[0]).toFixed(1)}" cy="${py(p[1]).toFixed(1)}" r="3" fill="none" stroke="var(--muted-foreground)" stroke-dasharray="2 2"><title>Scoring subgoal ${i+1}</title></circle>`).join('');
      const gx=px(scene.goal[0]), gy=py(scene.goal[1]), ex=px(d.end[0]), ey=py(d.end[1]);
      host.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(LABEL[arch])}, seed ${selectedSeed}, trajectory ending ${d.distanceToGoal.toFixed(1)} metres from goal">
        <line x1="${px(0)}" y1="${py(0)}" x2="${gx}" y2="${gy}" stroke="var(--border)" stroke-dasharray="4 5"/>
        ${obstacles}${subgoals}
        <circle cx="${gx}" cy="${gy}" r="${Math.max(5,scene.goalRadius*scale).toFixed(1)}" fill="none" stroke="var(--green)" stroke-width="1.5"><title>Goal success radius</title></circle>
        <circle cx="${gx}" cy="${gy}" r="3.2" fill="var(--green)"><title>Goal (${scene.goal[0].toFixed(1)}, ${scene.goal[1].toFixed(1)})</title></circle>
        <path d="${path}" fill="none" stroke="${SERIES[arch]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><title>${LABEL[arch]} path: ${d.pathLength.toFixed(1)} m</title></path>
        <circle cx="${px(0)}" cy="${py(0)}" r="3.5" fill="var(--foreground)"><title>Start (0, 0)</title></circle>
        <circle cx="${ex}" cy="${ey}" r="5" fill="${d.success?'var(--green)':'var(--red)'}" stroke="var(--background)" stroke-width="1.5"><title>End (${d.end[0].toFixed(1)}, ${d.end[1].toFixed(1)}), ${d.distanceToGoal.toFixed(1)} m from goal</title></circle>
      </svg>`;
    }
    function drawAll() { root.querySelectorAll('.map-panel').forEach(draw); }
    root.querySelectorAll('[data-seed]').forEach(button => button.addEventListener('click', () => {
      selectedSeed = Number(button.dataset.seed);
      root.querySelectorAll('[data-seed]').forEach(b => b.setAttribute('aria-pressed', String(b===button)));
      shell();
    }));
    new ResizeObserver(() => { cancelAnimationFrame(resizeFrame); resizeFrame=requestAnimationFrame(drawAll); }).observe(maps);
    shell();
  })();
  </script>
</div>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = json.dumps(export(args.report_dir.resolve()), separators=(",", ":"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(TEMPLATE.replace("__DATA__", data), encoding="utf-8")


if __name__ == "__main__":
    main()
