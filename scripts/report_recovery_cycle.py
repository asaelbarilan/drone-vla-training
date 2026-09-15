"""Archive, replay and inspect one autonomous recovery cycle (no inference)."""
import argparse
import asyncio
import gzip
import json
import shutil
from collections import Counter
from pathlib import Path

from audit_clutter_stable import audit

from uavlab.analysis.flight_debugger import _sources, html_document, load_run

OUT = Path('reports/recovery_cycle_20260915')
BASE = 'c5_clutter_qwen4_20260915_s1061'


async def main(number):
    state = json.loads((OUT / 'STATE.json').read_text())
    name = state['flights'][number - 1]['run']
    dest = OUT / f'cycle{number}'
    dest.mkdir(exist_ok=True)
    root = Path('runs') / name
    manifest = json.loads((root / 'manifest.json').read_text())
    frozen = json.loads((OUT / f'CYCLE{number}_FREEZE.json').read_text())
    assert manifest['architecture_config'] == frozen['architecture']
    assert manifest['environment_config'] == frozen['environment']
    results = [await load_run(Path('runs') / n) for n in [BASE, name]]
    for r in results:
        assert r['provenance']['max_position_error_m'] < 1e-7
        assert r['provenance']['missing_source_frames'] == 0
    Path(f'reports/debugger/recovery_cycle{number}.html').write_text(
        html_document(dict(schema=1, runs=results, sources=_sources())), encoding='utf-8')
    proof = await audit(name)
    events = [json.loads(x) for x in (root / 'events.jsonl').read_text().splitlines()]
    proof['event_counts'] = dict(Counter(e['event_type'] for e in events))
    proof['recovery'] = [e for e in events if e['event_type'] in
                         ['recovery_trigger', 'recovery_decision']]
    proof['rejections'] = [e for e in events if e['payload'].get('rejected')]
    proof['monitor_labels'] = dict(Counter(e['payload']['label'] for e in events
                                          if e['event_type'] == 'monitor'))
    proof['comparison'] = [dict(name=r['name'], closest=min(f['distance'] for f in r['frames']),
                               closest_t=min(r['frames'], key=lambda f:f['distance'])['t'],
                               provenance=r['provenance']) for r in results]
    (dest / 'AUDIT.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    for filename in ['manifest.json', 'result.json']:
        (dest / filename).write_bytes((root / filename).read_bytes())
    (dest / 'events.jsonl.gz').write_bytes(
        gzip.compress((root / 'events.jsonl').read_bytes(), mtime=0))
    shutil.copytree(root / 'debug', dest / 'debug', dirs_exist_ok=True)
    state['flights'][number - 1]['status'] = 'replayed'
    state['status'] = f'cycle{number}_visual_review'
    (OUT / 'STATE.json').write_text(json.dumps(state, indent=2))
    print(json.dumps({k:v for k,v in proof.items()
                      if k not in ['selected_decisions', 'rejections']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('number', type=int)
    asyncio.run(main(parser.parse_args().number))
