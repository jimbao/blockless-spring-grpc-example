#!/usr/bin/env python3
"""Run identical ghz workloads against a running application."""
import argparse
import json
from pathlib import Path
import subprocess


def scenarios():
    for thread in ('pt', 'vt'):
        for mode in ('join', 'blockless'):
            yield f'query-{thread}-{mode}-0.001', 'Query', dict(
                mode=mode, thread_type=thread, country='SE', sleep_seconds=0.001,
                pt_pool_size=4, db_pool_size=10)
    for mode, limit in (('serial', 0), ('parallel', 3)):
        yield f'fanout-{mode}-{limit}-0.001', 'FanOut', dict(
            mode=mode, max_concurrency=limit, countries=['SE', 'US', 'GB', 'DE', 'JP'],
            sleep_seconds=0.001)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--proto', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name, rpc, data in scenarios():
        command = ['ghz', '--insecure', '--proto', args.proto, '--call',
                   f'org.pjlabs.example.BenchmarkService/{rpc}', '--concurrency', '32',
                   '--connections', '4', '--timeout', '10s', '--duration-stop', 'wait', '--data', json.dumps(data),
                   '--format', 'json']
        print(name, flush=True)
        for phase, duration in (('warmup', '1s'), ('measure', '3s')):
            result = subprocess.run(command + ['--duration', duration,
                                               'localhost:9090'], capture_output=True, text=True)
            (output / f'{name}-{phase}.json').write_text(result.stdout)
            (output / f'{name}-{phase}.stderr').write_text(result.stderr)
            if result.returncode:
                raise RuntimeError(f'ghz failed for {name}: {result.stderr}')


if __name__ == '__main__':
    main()
