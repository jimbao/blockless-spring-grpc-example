#!/usr/bin/env python3
"""Run identical ghz workloads against a running application."""
import argparse
import json
from pathlib import Path
import subprocess


def scenarios():
    for delay in (0.001, 0.05):
        for thread in ('pt', 'vt'):
            for mode in ('join', 'blockless'):
                yield f'query-{thread}-{mode}-{delay}', 'Query', dict(
                    mode=mode, thread_type=thread, country='SE', sleep_seconds=delay,
                    pt_pool_size=4, db_pool_size=10)
        for mode, limit in (('serial', 0), ('parallel', 0), ('parallel', 3)):
            yield f'fanout-{mode}-{limit}-{delay}', 'FanOut', dict(
                mode=mode, max_concurrency=limit, countries=['SE', 'US', 'GB', 'DE', 'JP'],
                sleep_seconds=delay)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--proto', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--warmup', default='10s')
    parser.add_argument('--duration', default='20s')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name, rpc, data in scenarios():
        command = ['ghz', '--insecure', '--proto', args.proto, '--call',
                   f'org.pjlabs.example.BenchmarkService/{rpc}', '--concurrency', '32',
                   '--connections', '4', '--timeout', '10s', '--duration-stop', 'wait', '--data', json.dumps(data),
                   '--format', 'json']
        print(name, flush=True)
        for phase, duration in (('warmup', args.warmup), ('measure', args.duration)):
            result = subprocess.run(command + ['--duration', duration,
                                               'localhost:9090'], capture_output=True, text=True)
            (output / f'{name}-{phase}.json').write_text(result.stdout)
            (output / f'{name}-{phase}.stderr').write_text(result.stderr)
            if result.returncode:
                raise RuntimeError(f'ghz failed for {name}: {result.stderr}')


if __name__ == '__main__':
    main()
