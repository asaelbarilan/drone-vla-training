"""Build professor-ready representative end maps from actual episode logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from export_end_map_data import export


ARCH_ORDER = (
    "c0",
    "c1_aerialclaw_qwen4_shared",
    "c2_spf_qwen4_shared",
    "c3_onfly_qwen4_shared",
    "c8_aerovla_qwen4_shared",
)
ARCH_META = {
    "c0": {
        "label": "C0 SUPER control ceiling - oracle semantics",
        "short": "C0 SUPER ceiling\nOracle semantics (privileged)",
        "colour": "var(--viz-series-1)",
        "pdf_colour": "#6b7280",
        "status": "privileged control baseline",
    },
    "c1_aerialclaw_qwen4_shared": {
        "label": "C1 AerialClaw - Qwen3-VL 4B",
        "short": "C1 AerialClaw\nQwen3-VL 4B",
        "colour": "var(--viz-series-2)",
        "pdf_colour": "#2563eb",
        "status": "real local model",
    },
    "c2_spf_qwen4_shared": {
        "label": "C2 See, Point, Fly - Qwen3-VL 4B",
        "short": "C2 See, Point, Fly\nQwen3-VL 4B",
        "colour": "var(--viz-series-3)",
        "pdf_colour": "#8b5cf6",
        "status": "real local VLM",
    },
    "c3_onfly_qwen4_shared": {
        "label": "C3 OnFly - Qwen3-VL 4B",
        "short": "C3 OnFly\nQwen3-VL 4B",
        "colour": "var(--viz-series-4)",
        "pdf_colour": "#f59e0b",
        "status": "real compatible backend",
    },
    "c8_aerovla_qwen4_shared": {
        "label": "C8 AeroVLA + shield - Qwen3-VL 4B",
        "short": "C8 AeroVLA + shield\nQwen3-VL 4B",
        "colour": "var(--viz-series-5)",
        "pdf_colour": "#059669",
        "status": "real compatible backend",
    },
}


def _representatives(data: dict) -> tuple[list[dict], dict[str, int]]:
    """Rank seeds once, using non-oracle aggregate outcomes only."""
    rows = []
    seeds = sorted(int(seed) for seed in data["scenes"])
    for seed in seeds:
        episodes = [
            row for row in data["episodes"]
            if row["seed"] == seed and row["architecture"] != "c0"
        ]
        if len(episodes) != len(ARCH_ORDER) - 1:
            raise ValueError(f"seed {seed} is missing one or more real-architecture episodes")
        row = {
            "seed": seed,
            "successes": sum(bool(item["success"]) for item in episodes),
            "collisions": sum(int(item["collisions"]) for item in episodes),
            "meanDistance": sum(float(item["distanceToGoal"]) for item in episodes) / len(episodes),
            "meanFlightTime": sum(float(item["flightTime"]) for item in episodes) / len(episodes),
        }
        rows.append(row)
    rows.sort(
        key=lambda row: (
            -row["successes"],
            row["collisions"],
            row["meanDistance"],
            row["meanFlightTime"],
            row["seed"],
        )
    )
    reps = {"best": rows[0]["seed"], "median": rows[len(rows) // 2]["seed"], "worst": rows[-1]["seed"]}
    return rows, reps


def _episode(data: dict, architecture: str, seed: int) -> dict:
    return next(
        row for row in data["episodes"]
        if row["architecture"] == architecture and row["seed"] == seed
    )


def _scene(data: dict, seed: int) -> dict:
    return data["scenes"].get(seed) or data["scenes"][str(seed)]


def _bounds(data: dict, seed: int) -> tuple[float, float, float, float]:
    scene = _scene(data, seed)
    points = [[0.0, 0.0], scene["goal"], *scene["subgoals"]]
    for obstacle in scene["obstacles"]:
        x, y = obstacle["center"]
        hx, hy = obstacle["half"]
        points.extend(([x - hx, y - hy], [x + hx, y + hy]))
    for architecture in ARCH_ORDER:
        points.extend(_episode(data, architecture, seed)["path"])
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 20.0) * 1.18
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    return cx - span / 2, cx + span / 2, cy - span / 2, cy + span / 2


def _pdf_xy(value: float, low: float, scale: float, origin: float) -> float:
    return origin + (value - low) * scale


def _draw_pdf_map(pdf: canvas.Canvas, data: dict, architecture: str, seed: int, x: float, y: float, width: float, height: float) -> None:
    scene = _scene(data, seed)
    episode = _episode(data, architecture, seed)
    meta = ARCH_META[architecture]
    pdf.setStrokeColor(colors.HexColor("#d1d5db"))
    pdf.setFillColor(colors.white)
    pdf.roundRect(x, y, width, height, 5, stroke=1, fill=1)
    verdict = "SUCCESS" if episode["success"] else episode["termination"].replace("_", " ").upper()
    verdict_colour = colors.HexColor("#15803d" if episode["success"] else "#dc2626")
    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.setFont("Helvetica-Bold", 8.2)
    title_lines = meta["short"].split("\n")
    pdf.drawString(x + 7, y + height - 13, title_lines[0])
    if len(title_lines) > 1:
        pdf.setFont("Helvetica", 7.2)
        pdf.drawString(x + 7, y + height - 23, title_lines[1])
    pdf.setFillColor(verdict_colour)
    pdf.setFont("Helvetica-Bold", 6.6)
    pdf.drawRightString(x + width - 7, y + height - 13, verdict)

    map_x, map_y = x + 7, y + 35
    map_w, map_h = width - 14, height - 65
    xmin, xmax, ymin, ymax = _bounds(data, seed)
    span = xmax - xmin
    scale = min(map_w / span, map_h / span)
    draw_w = span * scale
    draw_h = span * scale
    origin_x = map_x + (map_w - draw_w) / 2
    origin_y = map_y + (map_h - draw_h) / 2
    px = lambda value: _pdf_xy(value, xmin, scale, origin_x)
    py = lambda value: _pdf_xy(value, ymin, scale, origin_y)

    pdf.setStrokeColor(colors.HexColor("#e5e7eb"))
    pdf.setLineWidth(0.35)
    for fraction in (0.25, 0.5, 0.75):
        pdf.line(origin_x + draw_w * fraction, origin_y, origin_x + draw_w * fraction, origin_y + draw_h)
        pdf.line(origin_x, origin_y + draw_h * fraction, origin_x + draw_w, origin_y + draw_h * fraction)
    for obstacle in scene["obstacles"]:
        obstacle_x, obstacle_y = obstacle["center"]
        hx, hy = obstacle["half"]
        pdf.setFillColor(colors.HexColor("#d1d5db"))
        pdf.setStrokeColor(colors.HexColor("#9ca3af"))
        pdf.rect(px(obstacle_x - hx), py(obstacle_y - hy), 2 * hx * scale, 2 * hy * scale, stroke=1, fill=1)
    for point in scene["subgoals"]:
        pdf.setStrokeColor(colors.HexColor("#6b7280"))
        pdf.circle(px(point[0]), py(point[1]), 2.0, stroke=1, fill=0)
    goal_x, goal_y = scene["goal"]
    pdf.setStrokeColor(colors.HexColor("#16a34a"))
    pdf.setLineWidth(1.0)
    pdf.circle(px(goal_x), py(goal_y), scene["goalRadius"] * scale, stroke=1, fill=0)
    pdf.setFillColor(colors.HexColor("#16a34a"))
    pdf.circle(px(goal_x), py(goal_y), 2.2, stroke=0, fill=1)
    path = episode["path"]
    if len(path) > 1:
        trajectory = pdf.beginPath()
        trajectory.moveTo(px(path[0][0]), py(path[0][1]))
        for point in path[1:]:
            trajectory.lineTo(px(point[0]), py(point[1]))
        pdf.setStrokeColor(colors.HexColor(meta["pdf_colour"]))
        pdf.setLineWidth(1.45)
        pdf.drawPath(trajectory, stroke=1, fill=0)
    pdf.setFillColor(colors.HexColor("#111827"))
    pdf.circle(px(0), py(0), 2.3, stroke=0, fill=1)
    pdf.setFillColor(verdict_colour)
    pdf.circle(px(episode["end"][0]), py(episode["end"][1]), 3.1, stroke=0, fill=1)

    pdf.setFillColor(colors.HexColor("#374151"))
    pdf.setFont("Helvetica", 6.7)
    pdf.drawString(x + 7, y + 20, f"goal {episode['distanceToGoal']:.1f} m | path {episode['pathLength']:.1f} m | collisions {episode['collisions']}")
    pdf.drawString(x + 7, y + 10, f"flight {episode['flightTime']:.1f} s | model calls {episode['modelCalls']} | end ({episode['end'][0]:.1f}, {episode['end'][1]:.1f})")


def _write_static(data: dict, reps: dict[str, int], output_dir: Path) -> Path:
    pdf_path = output_dir / "professor_end_maps_shared_qwen4_best_median_worst.pdf"
    page_w, page_h = landscape(A4)
    pdf = canvas.Canvas(str(pdf_path), pagesize=(page_w, page_h), pageCompression=1)
    pdf.setTitle("Single-model UAV architecture end maps - best, median, and worst development seeds")
    pdf.setAuthor("UAV Architecture Lab")
    margin, gap = 24.0, 12.0
    header_h = 48.0
    cell_w = (page_w - 2 * margin - 2 * gap) / 3
    cell_h = (page_h - 2 * margin - header_h - gap) / 2
    for rank in ("best", "median", "worst"):
        seed = reps[rank]
        score = next(row for row in data["seedRanking"] if row["seed"] == seed)
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.setFont("Helvetica-Bold", 15)
        pdf.drawString(margin, page_h - margin - 13, f"Single-model UAV architecture end maps - {rank} representative (seed {seed})")
        pdf.setFillColor(colors.HexColor("#4b5563"))
        pdf.setFont("Helvetica", 8)
        pdf.drawString(margin, page_h - margin - 29, "Qwen3-VL 4B for all non-oracle architectures | fixed shared testbed | development seeds only")
        for index, architecture in enumerate(ARCH_ORDER):
            row, col = divmod(index, 3)
            x = margin + col * (cell_w + gap)
            y = page_h - margin - header_h - (row + 1) * cell_h - row * gap
            _draw_pdf_map(pdf, data, architecture, seed, x, y, cell_w, cell_h)
        note_x = margin + 2 * (cell_w + gap)
        note_y = page_h - margin - header_h - 2 * cell_h - gap
        pdf.setStrokeColor(colors.HexColor("#d1d5db"))
        pdf.setFillColor(colors.HexColor("#f9fafb"))
        pdf.roundRect(note_x, note_y, cell_w, cell_h, 5, stroke=1, fill=1)
        pdf.setFillColor(colors.HexColor("#111827"))
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(note_x + 10, note_y + cell_h - 18, f"{rank.title()} development seed: {seed}")
        pdf.setFillColor(colors.HexColor("#374151"))
        pdf.setFont("Helvetica", 7.6)
        lines = [
            "Selection across four non-oracle ports:",
            f"{score['successes']}/4 successes, {score['collisions']} collisions,",
            f"mean endpoint distance {score['meanDistance']:.1f} m.",
            "",
            "C6 PMR: BLOCKED - trained CVI checkpoint absent.",
            "The scripted C6 structural sentinel is excluded.",
            "",
            "Paths: logged onboard pose at controller ticks.",
            "Scene and verdict: deterministic simulator logs.",
            "Same model, scene, controller, success rule, and channels.",
        ]
        cursor = note_y + cell_h - 34
        for line in lines:
            pdf.drawString(note_x + 10, cursor, line)
            cursor -= 11
        pdf.showPage()
    pdf.save()
    return pdf_path


HTML = r'''<div id="professor-end-maps-v1" class="pem">
<style>
#professor-end-maps-v1{color:var(--foreground);font-family:var(--font-sans);padding:8px 2px 4px}#professor-end-maps-v1 *{box-sizing:border-box}.pem-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin-bottom:10px}.pem h2{margin:0 0 3px}.pem-sub,.pem-note{color:var(--muted-foreground)}.pem-controls{display:flex;gap:6px;flex-wrap:wrap}.pem-summary{display:grid;grid-template-columns:minmax(0,1fr) minmax(210px,.42fr);gap:9px;margin-bottom:10px}.pem-rule,.pem-blocked{padding:8px 10px}.pem-legend{display:flex;flex-wrap:wrap;gap:13px;margin-bottom:9px;color:var(--muted-foreground)}.pem-legend span{display:inline-flex;align-items:center;gap:5px}.pem-k{width:9px;height:9px;display:inline-block}.pem-start{border-radius:50%;background:var(--foreground)}.pem-goal{border-radius:50%;border:2px solid var(--green)}.pem-end{border-radius:50%;background:var(--red)}.pem-obstacle{background:var(--muted);border:1px solid var(--border)}.pem-maps{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:12px}.pem-panel{overflow:hidden;min-width:0}.pem-panel-head{padding:6px 2px;display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.pem-name{font-weight:500}.pem-kind{display:block;color:var(--muted-foreground);font-weight:400;margin-top:2px}.pem-badge{white-space:nowrap}.pem-badge.ok{color:var(--green)}.pem-badge.fail{color:var(--red)}.pem-plot{height:246px;width:100%;border:1px solid var(--border)}.pem-plot svg{display:block;width:100%;height:100%}.pem-stats{display:grid;grid-template-columns:repeat(5,1fr)}.pem-stat{padding:6px 4px;text-align:center;min-width:0}.pem-stat b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.pem-stat small{color:var(--muted-foreground)}.pem-note{margin-top:9px}@media(max-width:736px){.pem-head{align-items:flex-start;flex-direction:column}.pem-summary{grid-template-columns:1fr}.pem-maps{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:430px){.pem-maps{grid-template-columns:1fr}.pem-controls{width:100%}}
</style>
<div class="pem-head"><div><h2>Single-model architecture end maps</h2><div class="pem-sub">Qwen3-VL 4B for every non-oracle architecture · fixed shared testbed · development seeds only</div></div><div class="pem-controls" role="group" aria-label="Representative development seed"></div></div>
<div class="pem-summary"><div class="pem-rule card"></div><div class="pem-blocked card"><b>C6 PMR - blocked</b><br>Trained CVI checkpoint is absent. The scripted structural sentinel is excluded.</div></div>
<div class="pem-legend"><span><i class="pem-k pem-start"></i>start</span><span><i class="pem-k pem-goal"></i>goal + 2 m radius</span><span><i class="pem-k pem-end"></i>failed endpoint</span><span><i class="pem-k pem-obstacle"></i>obstacle footprint</span></div>
<div class="pem-maps"></div><div class="pem-note">Paths are sampled directly from onboard pose in the 20 Hz controller log; endpoints, collisions, and verdicts come from episode results. C0 alone receives privileged goal semantics. Extra sensor channels are present identically for every architecture but are consumed only by architectures that use them.</div>
<script>(()=>{const DATA=__DATA__;const ORDER=__ORDER__;const META=__META__;const root=document.getElementById('professor-end-maps-v1');const maps=root.querySelector('.pem-maps');const controls=root.querySelector('.pem-controls');let rank='best',resizeFrame=0;const esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const ep=(a,s)=>DATA.episodes.find(d=>d.architecture===a&&d.seed===s);const seed=()=>DATA.representatives[rank];const scene=()=>DATA.scenes[String(seed())];function bounds(){const sc=scene(),pts=[[0,0],sc.goal,...sc.subgoals];sc.obstacles.forEach(o=>pts.push([o.center[0]-o.half[0],o.center[1]-o.half[1]],[o.center[0]+o.half[0],o.center[1]+o.half[1]]));ORDER.forEach(a=>pts.push(...ep(a,seed()).path));let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;pts.forEach(([x,y])=>{minX=Math.min(minX,x);maxX=Math.max(maxX,x);minY=Math.min(minY,y);maxY=Math.max(maxY,y)});const span=Math.max(maxX-minX,maxY-minY,20)*1.18;return{cx:(minX+maxX)/2,cy:(minY+maxY)/2,span}}function verdict(d){return d.success?'SUCCESS':d.termination.replaceAll('_',' ').toUpperCase()}function shell(){const s=seed(),score=DATA.seedRanking.find(d=>d.seed===s);root.querySelector('.pem-rule').innerHTML=`<b>${rank.toUpperCase()} representative: seed ${s}</b><br>Ranked before plotting by non-oracle outcomes: successes (more), collisions (fewer), mean endpoint distance (lower), then mean flight time (lower). This seed: ${score.successes}/4 successes, ${score.collisions} collisions, ${score.meanDistance.toFixed(1)} m mean distance.`;maps.innerHTML=ORDER.map(a=>{const d=ep(a,s),m=META[a];return`<section class="pem-panel" data-arch="${a}"><div class="pem-panel-head"><span class="pem-name">${esc(m.label)}<small class="pem-kind">${esc(m.status)}</small></span><span class="pem-badge ${d.success?'ok':'fail'}">${esc(verdict(d))}</span></div><div class="pem-plot"></div><div class="pem-stats"><span class="pem-stat"><b>${d.distanceToGoal.toFixed(1)} m</b><small>to goal</small></span><span class="pem-stat"><b>${d.pathLength.toFixed(1)} m</b><small>path</small></span><span class="pem-stat"><b>${d.collisions}</b><small>collisions</small></span><span class="pem-stat"><b>${d.flightTime.toFixed(1)} s</b><small>flight</small></span><span class="pem-stat"><b>${d.modelCalls}</b><small>model calls</small></span></div></section>`}).join('');drawAll()}function draw(panel){const a=panel.dataset.arch,d=ep(a,seed()),sc=scene(),box=bounds(),host=panel.querySelector('.pem-plot'),w=Math.max(220,Math.floor(host.getBoundingClientRect().width)),h=246,pad=13,scale=Math.min((w-2*pad)/box.span,(h-2*pad)/box.span),px=x=>w/2+(x-box.cx)*scale,py=y=>h/2-(y-box.cy)*scale,path=d.path.map((p,i)=>`${i?'L':'M'}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join(' '),obstacles=sc.obstacles.map(o=>`<rect x="${px(o.center[0]-o.half[0]).toFixed(1)}" y="${py(o.center[1]+o.half[1]).toFixed(1)}" width="${(2*o.half[0]*scale).toFixed(1)}" height="${(2*o.half[1]*scale).toFixed(1)}" fill="var(--muted)" stroke="var(--border)"/>`).join(''),subs=sc.subgoals.map(p=>`<circle cx="${px(p[0]).toFixed(1)}" cy="${py(p[1]).toFixed(1)}" r="2.6" fill="none" stroke="var(--muted-foreground)"/>`).join(''),gx=px(sc.goal[0]),gy=py(sc.goal[1]),ex=px(d.end[0]),ey=py(d.end[1]);host.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(META[a].label)}, ${rank} seed ${seed()}, ${esc(verdict(d))}"><line x1="${px(0)}" y1="${py(0)}" x2="${gx}" y2="${gy}" stroke="var(--border)" stroke-dasharray="4 5"/>${obstacles}${subs}<circle cx="${gx}" cy="${gy}" r="${Math.max(5,sc.goalRadius*scale).toFixed(1)}" fill="none" stroke="var(--green)" stroke-width="1.5"/><circle cx="${gx}" cy="${gy}" r="3" fill="var(--green)"/><path d="${path}" fill="none" stroke="${META[a].colour}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${px(0)}" cy="${py(0)}" r="3.3" fill="var(--foreground)"/><circle cx="${ex}" cy="${ey}" r="4.8" fill="${d.success?'var(--green)':'var(--red)'}" stroke="var(--background)" stroke-width="1.4"/></svg>`}function drawAll(){root.querySelectorAll('.pem-panel').forEach(draw)}['best','median','worst'].forEach((r,i)=>{const b=document.createElement('button');b.className='btn';b.dataset.rank=r;b.setAttribute('aria-pressed',String(i===0));b.textContent=`${r[0].toUpperCase()+r.slice(1)} · ${DATA.representatives[r]}`;b.addEventListener('click',()=>{rank=r;controls.querySelectorAll('.btn').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));shell()});controls.appendChild(b)});new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(drawAll)}).observe(maps);shell()})()</script></div>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("visualization_html", type=Path)
    args = parser.parse_args()
    report_dir = args.report_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data = export(report_dir)
    ranking, representatives = _representatives(data)
    data.update(
        {
            "seedPool": sorted(int(seed) for seed in data["scenes"]),
            "seedRanking": ranking,
            "representatives": representatives,
            "selectionRule": "non-oracle successes descending, collisions ascending, mean endpoint distance ascending, mean flight time ascending",
            "blocked": {"c6_pmr": "trained CVI checkpoint absent; scripted structural sentinel excluded"},
        }
    )
    data_path = output_dir / "professor_end_maps_shared_qwen4_data.json"
    data_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    compact = json.dumps(data, separators=(",", ":"))
    html = HTML.replace("__DATA__", compact).replace("__ORDER__", json.dumps(ARCH_ORDER)).replace("__META__", json.dumps(ARCH_META))
    html_path = output_dir / "professor_end_maps_shared_qwen4.html"
    html_path.write_text(html, encoding="utf-8")
    args.visualization_html.parent.mkdir(parents=True, exist_ok=True)
    args.visualization_html.write_text(html, encoding="utf-8")
    pdf_path = _write_static(data, representatives, output_dir)
    print(json.dumps({"html": str(html_path), "visualization": str(args.visualization_html), "data": str(data_path), "pdf": str(pdf_path), "representatives": representatives}, indent=2))


if __name__ == "__main__":
    main()
