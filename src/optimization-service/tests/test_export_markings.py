import csv
import io
import json
import os
import sys
import unittest
import zipfile

SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from api.serialization import _build_experiment_export_archive


class ExportMarkingsTest(unittest.TestCase):
    def test_export_includes_experiment_provenance_and_snapshot_interval_stats(self):
        payload, _ = _build_experiment_export_archive(
            {
                'experiment_id': 'test', 'experiment_name': 'provenance',
                'conformance_mode': 'replay-token', 'log_sha256': 'a' * 64,
                'optimizer_config': {'n_partitions': 2},
                'population_snapshots': [{
                    'snapshot_id': 7, 'experiment_id': 'test', 'snapshot_index': 1,
                    'evaluations_done': 12, 'attempts_since_previous': 12,
                    'cache_hits_since_previous': 3, 'errors_since_previous': 1,
                    'unique_pipelines_since_previous': 9,
                }],
            },
            [{'solution_id': 1, 'evaluation_id': 'eval-1', 'evaluation_status': 'feasible',
              'pipeline_full': {'miner': {'key': 'alpha'}}}],
            [{'snapshot_solution_id': 2, 'snapshot_id': 7, 'evaluation_id': 'eval-1'}],
        )
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIn('population_snapshots.csv', archive.namelist())
            experiment = next(csv.DictReader(io.StringIO(archive.read('experiment.csv').decode('utf-8'))))
            snapshot = next(csv.DictReader(io.StringIO(archive.read('population_snapshots.csv').decode('utf-8'))))
            solution = next(csv.DictReader(io.StringIO(archive.read('solutions.csv').decode('utf-8'))))
            member = next(csv.DictReader(io.StringIO(archive.read('snapshot_solutions.csv').decode('utf-8'))))
            self.assertEqual(experiment['conformance_mode'], 'replay-token')
            self.assertEqual(json.loads(experiment['optimizer_config']), {'n_partitions': 2})
            self.assertEqual(snapshot['cache_hits_since_previous'], '3')
            self.assertEqual(solution['evaluation_id'], 'eval-1')
            self.assertEqual(json.loads(solution['pipeline_full']), {'miner': {'key': 'alpha'}})
            self.assertEqual(member['snapshot_id'], '7')

    def test_solution_and_snapshot_exports_preserve_alternative_final_markings(self):
        initial = [{'place_id': 'p_start', 'tokens': 2}]
        finals = [
            [{'place_id': 'p_left', 'tokens': 1}],
            [{'place_id': 'p_right', 'tokens': 3}],
        ]
        markings = {
            'initial_marking': initial,
            'final_marking': finals[0],
            'final_markings': finals,
        }
        payload, _ = _build_experiment_export_archive(
            {'experiment_id': 'test', 'experiment_name': 'multi-final'},
            [{'solution_id': 1, **markings}],
            [{'snapshot_solution_id': 1, **markings}],
        )

        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for filename in ('solutions.csv', 'snapshot_solutions.csv'):
                row = next(csv.DictReader(io.StringIO(archive.read(filename).decode('utf-8'))))
                for field, expected in markings.items():
                    self.assertEqual(json.loads(row[field]), expected, (filename, field))


if __name__ == '__main__':
    unittest.main()
