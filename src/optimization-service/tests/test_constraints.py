import os
import sys
import unittest


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from constraints import (
    collect_required_metrics,
    evaluate_constraints,
    is_feasible_constraint_values,
    normalize_constraints,
    normalize_metric_names,
)


class ConstraintsTest(unittest.TestCase):
    def test_normalize_metric_names_deduplicates(self):
        metrics = normalize_metric_names(["fitness", "precision", "fitness"])
        self.assertEqual(["fitness", "precision"], metrics)

    def test_normalize_constraints_accepts_all_supported_operators(self):
        constraints = normalize_constraints(
            [
                {"metric": "fitness", "operator": ">=", "value": 0.7},
                {"metric": "places", "operator": "<=", "value": 10},
                {"metric": "precision", "operator": ">", "value": 0.5},
                {"metric": "arcs", "operator": "<", "value": 20},
                {"metric": "simplicity", "operator": "==", "value": 0.3},
            ]
        )
        self.assertEqual(5, len(constraints))

    def test_collect_required_metrics_includes_constraint_metrics(self):
        required = collect_required_metrics(
            ["fitness", "precision"],
            [{"metric": "places", "operator": "<=", "value": 25.0}],
        )
        self.assertEqual(["fitness", "precision", "places"], required)

    def test_evaluate_constraints_returns_non_negative_for_satisfied(self):
        values = evaluate_constraints(
            {"fitness": 0.9, "places": 10.0},
            [
                {"metric": "fitness", "operator": ">=", "value": 0.8},
                {"metric": "places", "operator": "<=", "value": 12.0},
            ],
        )
        self.assertTrue(is_feasible_constraint_values(values))

    def test_evaluate_constraints_returns_negative_for_violations(self):
        values = evaluate_constraints(
            {"fitness": 0.7, "places": 15.0},
            [
                {"metric": "fitness", "operator": ">=", "value": 0.8},
                {"metric": "places", "operator": "<=", "value": 12.0},
            ],
        )
        self.assertEqual(2, len(values))
        self.assertLess(values[0], 0.0)
        self.assertLess(values[1], 0.0)


if __name__ == "__main__":
    unittest.main()
