import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).parent))
from run import scenarios

spec = importlib.util.spec_from_file_location('report', Path(__file__).with_name('report.py'))
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for variant, rps, latency in [('base', 100, 10000000), ('candidate', 120, 8000000)]:
            for repetition in range(1, 6):
                directory = self.root / variant / str(repetition)
                directory.mkdir(parents=True)
                for name, _, _ in scenarios():
                    (directory / f'{name}-measure.json').write_text(json.dumps({
                        'count': 100, 'rps': rps, 'statusCodeDistribution': {'OK': 99},
                        'latencyDistribution': [{'percentage': p, 'latency': latency} for p in (50, 95, 99)]}))

    def test_units_deltas_and_errors(self):
        output = report.report(self.root)
        self.assertIn('+20.0%', output)
        self.assertIn('-20.0%', output)
        self.assertIn('10.00 [10.00–10.00]', output)
        self.assertIn('5/500 → 5/500', output)
        self.assertEqual(sum(line.startswith('| Query') or line.startswith('| FanOut') for line in output.splitlines()), 6)

    def test_missing_repetition_rejected(self):
        next((self.root / 'base/1').glob('*-measure.json')).unlink()
        with self.assertRaises(ValueError):
            report.report(self.root)

    def test_missing_scenario_rejected(self):
        name = next(scenarios())[0]
        for file in self.root.glob(f'*/*/{name}-measure.json'):
            file.unlink()
        with self.assertRaises(ValueError):
            report.report(self.root)

    def test_different_scenarios_rejected(self):
        for file in (self.root / 'candidate').glob('*/*.json'):
            file.rename(file.with_name('different-measure.json'))
        with self.assertRaises(ValueError):
            report.report(self.root)


if __name__ == '__main__':
    unittest.main()
