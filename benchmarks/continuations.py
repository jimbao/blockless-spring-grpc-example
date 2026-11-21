#!/usr/bin/env python3
"""Compare continuation, waiting-platform, and virtual-thread query modes over real gRPC."""
import argparse
import json
from pathlib import Path
from statistics import median
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghz', default='ghz')
    parser.add_argument('--address', default='localhost:9090')
    parser.add_argument('--output', type=Path, default=Path('results/continuations'))
    parser.add_argument('--repetitions', type=int, default=5)
    parser.add_argument('--sleep-seconds', type=float, default=0.01)
    parser.add_argument('--db-pool-size', type=int, default=10)
    args = parser.parse_args()
    if args.repetitions < 1 or args.sleep_seconds <= 0 or args.db_pool_size < 1:
        parser.error('repetitions, sleep-seconds and db-pool-size must be positive')
    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = [(thread, mode) for thread in ('pt', 'vt')
                 for mode in ('join', 'blockless', 'continuation')]
    samples = {f'{thread}-{mode}': [] for thread, mode in scenarios}
    proto = Path(__file__).resolve().parents[1] / 'src/main/proto/greeting.proto'
    for repetition in range(1, args.repetitions + 1):
        order = scenarios if repetition % 2 else list(reversed(scenarios))
        for thread, mode in order:
            name = f'{thread}-{mode}'
            data = dict(mode=mode, thread_type=thread, country='SE',
                        sleep_seconds=args.sleep_seconds, pt_pool_size=4,
                        db_pool_size=args.db_pool_size)
            command = [args.ghz, '--insecure', '--proto', str(proto), '--call',
                       'org.pjlabs.example.BenchmarkService/Query', '--concurrency', '32',
                       '--connections', '4', '--timeout', '10s', '--duration-stop', 'wait',
                       '--data', json.dumps(data), '--format', 'json']
            print(f'run {repetition}/{args.repetitions}: {name}', flush=True)
            for phase, duration in (('warmup', '1s'), ('measure', '3s')):
                run = subprocess.run(command + ['--duration', duration, args.address],
                                     capture_output=True, text=True, timeout=30)
                stem = args.output / f'{repetition}-{name}-{phase}'
                stem.with_suffix('.json').write_text(run.stdout)
                stem.with_suffix('.stderr').write_text(run.stderr)
                if run.returncode:
                    raise RuntimeError(f'ghz failed for {name}: {run.stderr}')
                result = json.loads(run.stdout)
                count = result['count']
                ok = result.get('statusCodeDistribution', {}).get('OK', 0)
                if count <= 0 or ok != count:
                    raise RuntimeError(f'{name}: {count - ok}/{count} requests failed')
                if phase == 'measure':
                    p95 = next(item['latency'] / 1e6 for item in result['latencyDistribution']
                               if item['percentage'] == 95)
                    samples[name].append(dict(rps=result['rps'], p95_ms=p95, count=count))
    summary = dict(settings=dict(concurrency=32, connections=4, pt_pool_size=4,
                                db_pool_size=args.db_pool_size, sleep_seconds=args.sleep_seconds,
                                repetitions=args.repetitions, warmup_seconds=1, measure_seconds=3),
                   scenarios={})
    print('\nScenario             Median req/s       p95 ms [min–max]       Errors/requests')
    for name, runs in samples.items():
        rates = [run['rps'] for run in runs]
        latencies = [run['p95_ms'] for run in runs]
        row = dict(median_rps=median(rates), median_p95_ms=median(latencies),
                   min_p95_ms=min(latencies), max_p95_ms=max(latencies),
                   min_rps=min(rates), max_rps=max(rates),
                   count=sum(run['count'] for run in runs), errors=0)
        summary['scenarios'][name] = row
        print(f"{name:22} {row['median_rps']:8.1f}     {row['median_p95_ms']:8.2f} "
              f"[{min(latencies):.2f}–{max(latencies):.2f}]       0/{row['count']}")
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
