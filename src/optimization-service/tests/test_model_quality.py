import os
import sys
import unittest

SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from model_quality import validate_v3_feasibility


class ModelQualityContractTest(unittest.TestCase):
    def test_feasible_and_excluded_models(self):
        validate_v3_feasibility(2, True, [])
        validate_v3_feasibility(2, False, ['MULTIPLE_COMPONENTS'])
        validate_v3_feasibility(2, False, ['QUALITY_CHECK_INCONCLUSIVE'])
        validate_v3_feasibility(0, False, ['NO_VISIBLE_TRANSITIONS'])

    def test_rejects_inconsistent_or_unknown_reasons(self):
        for count, feasible, reasons in (
            (2, True, ['DEAD_VISIBLE_TRANSITION']),
            (2, False, []),
            (0, True, []),
            (2, False, ['NO_VISIBLE_TRANSITIONS']),
            (2, False, ['UNRECOGNIZED_REASON']),
            (2, False, ['MULTIPLE_COMPONENTS', 'MULTIPLE_COMPONENTS']),
        ):
            with self.subTest(count=count, feasible=feasible, reasons=reasons):
                with self.assertRaises(ValueError):
                    validate_v3_feasibility(count, feasible, reasons)


if __name__ == '__main__':
    unittest.main()
