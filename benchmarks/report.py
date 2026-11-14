#!/usr/bin/env python3
"""Summarize ghz JSON; latency values are nanoseconds, reported as milliseconds."""
import json
import os
from pathlib import Path
from statistics import median


def read_runs(root, variant):
    groups = {}
    for path in sorted((root / variant).glob('*/*-measure.json')):
        run = json.loads(path.read_text())
        count = run['count']
        if count <= 0:
            raise ValueError(f'No requests: {path}')
        ok = run.get('statusCodeDistribution', {}).get('OK', 0)
        latency = {item['percentage']: item['latency'] / 1e6 for item in run['latencyDistribution']}
        groups.setdefault(path.name.removesuffix('-measure.json'), []).append({
            'rps': run['rps'], 'p50': latency[50], 'p95': latency[95],
            'p99': latency[99], 'errors': 100 * (count - ok) / count})
    if not groups or any(len(runs) != 5 for runs in groups.values()):
        raise ValueError(f'Expected five repetitions per scenario for {variant}')
    return groups


def report(root):
    base, candidate = (read_runs(root, variant) for variant in ('base', 'candidate'))
    if base.keys() != candidate.keys():
        raise ValueError('Scenario sets differ')
    lines = ['<!-- blockless-performance -->', '## Performance: main → proposed merge', '',
             f"Base: `{os.environ.get('BASE_SHA', 'unknown')}`", 
             f"PR head: `{os.environ.get('HEAD_SHA', 'unknown')}`",
             f"Candidate merge: `{os.environ.get('CANDIDATE_SHA', 'unknown')}`", '',
             'Informational only. Medians of five runs; ranges show run-to-run variation.',
             ('**SMOKE VALIDATION: short durations verify the pipeline, not performance.**'
              if os.environ.get('DURATION', '20s') != '20s' else ''),
             'Latency is measured end to end by ghz. No significance or regression gate is inferred.', '',
             '| Scenario | Metric | main median [min–max] | Merge median [min–max] | Change |',
             '|---|---|---:|---:|---:|']
    for scenario in base:
        for key, label in [('rps', 'Requests/sec ↑'), ('p50', 'p50 ms ↓'),
                           ('p95', 'p95 ms ↓'), ('p99', 'p99 ms ↓'), ('errors', 'Errors % ↓')]:
            values = [[r[key] for r in group[scenario]] for group in (base, candidate)]
            old, new = map(median, values)
            change = f'{new - old:+.2f} pp' if key == 'errors' else (
                f'{100 * (new / old - 1):+.1f}%' if old else 'n/a')
            cells = [f'{median(v):.2f} [{min(v):.2f}–{max(v):.2f}]' for v in values]
            lines.append(f'| {scenario} | {label} | {cells[0]} | {cells[1]} | {change} |')
    lines += ['', 'Java 21; PostgreSQL 18.1; DB pool 10; PT pool 4; 32 concurrent requests;',
              f"4 connections; {os.environ.get('WARMUP', '10s')} warmup + {os.environ.get('DURATION', '20s')} measurement per scenario; 512 MiB JVM heap;",
              'JVM active processor count 2. Fresh app/database per variant and repetition.',
              'Base/candidate order alternates. Shared runner and colocated load generator can add noise.',
              '', f"[Workflow and raw artifacts]({os.environ.get('RUN_URL', '')})"]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    Path('results/report.md').write_text(report(Path('results')))
