import os
import math
import itertools
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
    summarize_constraints,
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


class CompoundConstraintsTest(unittest.TestCase):
    familiarity = [{"any": [
        {"metric": "elc", "operator": "<=", "value": 137.5},
        {"all": [
            {"metric": "cfc", "operator": ">", "value": 69},
            {"metric": "transitions", "operator": "<=", "value": 178},
        ]},
    ]}]

    def test_familiarity_boundaries_and_adjacent_values(self):
        rules = normalize_constraints(self.familiarity)
        points = [[0., math.nextafter(t, -math.inf), t, math.nextafter(t, math.inf), 2*t]
                  for t in (137.5, 69., 178.)]
        for elc, cfc, transitions in itertools.product(*points):
            expected = elc <= 137.5 or (cfc > 69 and transitions <= 178)
            metrics = dict(elc=elc, cfc=cfc, transitions=transitions)
            with self.subTest(**metrics):
                margins = evaluate_constraints(metrics, rules)
                self.assertEqual(1, len(margins))
                self.assertEqual(expected, is_feasible_constraint_values(margins))

    def test_required_metrics_and_description_traverse_all_branches(self):
        self.assertEqual(['fitness', 'elc', 'cfc', 'transitions'], collect_required_metrics(['fitness'], self.familiarity))
        self.assertEqual('(elc<=137.5 OR (cfc>69 AND transitions<=178))', summarize_constraints(self.familiarity))

    def test_normalization_deduplicates_and_preserves_tree(self):
        duplicate = {'any': [self.familiarity[0], self.familiarity[0]]}
        self.assertEqual([{'any': normalize_constraints(self.familiarity)}], normalize_constraints([duplicate, duplicate]))

    def test_bad_or_unbounded_groups_are_rejected(self):
        for node in ({'any': []}, {'all': None}, {'any': {}}, {'all': [], 'any': []},
                     {'any': self.familiarity, 'metric': 'elc'}, {'unknown': []},
                     {'metric': 'elc', 'operator': '<', 'value': 5, 'any': []}):
            with self.subTest(node=node), self.assertRaises(ValueError):
                normalize_constraints([node])
        deep = self.familiarity[0]
        for _ in range(9): deep = {'all': [deep]}
        with self.assertRaises(ValueError): normalize_constraints([deep])
        with self.assertRaises(ValueError): normalize_constraints(self.familiarity * 256)

    def test_missing_metric_in_otherwise_passing_or_is_not_masked(self):
        for missing in (None, math.nan, math.inf, 'not a number'):
            values = {'elc': 0, 'cfc': missing, 'transitions': 1}
            self.assertLess(evaluate_constraints(values, self.familiarity)[0], 0)

    def test_group_margins_use_fixed_scales_and_flat_rules_stay_raw(self):
        leaves = [{'metric': 'elc', 'operator': '<=', 'value': 100},
                  {'metric': 'transitions', 'operator': '<=', 'value': 10}]
        metrics = {'elc': 150, 'transitions': 20}
        self.assertEqual([-50, -10], evaluate_constraints(metrics, leaves))
        self.assertEqual([-.5], evaluate_constraints(metrics, [{'any': leaves}]))
        self.assertEqual([-1.], evaluate_constraints(metrics, [{'all': leaves}]))

    def test_scaling_preserves_subnormal_violation(self):
        leaf = {'metric': 'elc', 'operator': '<=', 'value': 0}
        self.assertLess(evaluate_constraints({'elc': math.ulp(0.)}, [{'any': [leaf]}])[0], 0)


if __name__ == "__main__":
    unittest.main()
