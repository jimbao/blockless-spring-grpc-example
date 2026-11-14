#!/usr/bin/env python3
"""Summarize repeated ghz measurements in a compact PR table."""
import json
import os
from pathlib import Path
from statistics import median

from run import scenarios


def read_runs(root, variant):
    groups = {}
    for path in sorted((root / variant).glob('*/*-measure.json')):
        run = json.loads(path.read_text())
        count = run['count']
        if count <= 0:
            raise ValueError(f'No requests: {path}')
        errors = count - run.get('statusCodeDistribution', {}).get('OK', 0)
        latency = {item['percentage']: item['latency'] / 1e6 for item in run['latencyDistribution']}
        groups.setdefault(path.name.removesuffix('-measure.json'), []).append({
            'rps': run['rps'], 'p95': latency[95], 'errors': errors, 'count': count})
    expected = {name for name, _, _ in scenarios()}
    if groups.keys() != expected or any(len(runs) != 5 for runs in groups.values()):
        raise ValueError(f'Expected all six scenarios with five repetitions for {variant}')
    return groups


def delta(old, new):
    return f'{100 * (new / old - 1):+.1f}%' if old else 'n/a'


def report(root):
    base, candidate = (read_runs(root, variant) for variant in ('base', 'candidate'))
    lines = ['<!-- blockless-performance -->', '### Performance: main → PR', '',
             f"`{os.environ.get('BASE_SHA', 'unknown')[:7]}` → "
             f"`{os.environ.get('CANDIDATE_SHA', 'unknown')[:7]}` · "
             '5 runs · medians; latency ranges in brackets · informational', '',
             '| Scenario | Requests/s ↑ | Change | p95 ms ↓ | Change | Errors/requests |',
             '|---|---:|---:|---:|---:|---:|']
    for name, rpc, data in scenarios():
        groups = [group[name] for group in (base, candidate)]
        rates = [median(r['rps'] for r in runs) for runs in groups]
        latencies = [[r['p95'] for r in runs] for runs in groups]
        p95 = list(map(median, latencies))
        latency_cells = [f'{median(v):.2f} [{min(v):.2f}–{max(v):.2f}]' for v in latencies]
        errors = [f"{sum(r['errors'] for r in runs)}/{sum(r['count'] for r in runs)}" for runs in groups]
        label = f"Query {data['thread_type'].upper()} / {data['mode']}" if rpc == 'Query' else (
            'FanOut / serial' if data['mode'] == 'serial' else 'FanOut / parallel (3)')
        lines.append(f'| {label} | {rates[0]:.1f} → {rates[1]:.1f} | {delta(*rates)} | '
                     f'{latency_cells[0]} → {latency_cells[1]} | {delta(*p95)} | {errors[0]} → {errors[1]} |')
    lines += ['', '1 ms I/O · DB pool 10 · PT pool 4 · concurrency 32 · 1s warmup / 3s measurement.',
              f"[Raw results, environment and logs]({os.environ.get('RUN_URL', '')})"]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    Path('results/report.md').write_text(report(Path('results')))
