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
