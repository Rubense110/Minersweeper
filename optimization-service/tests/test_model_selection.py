import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from model_selection import ModelSelectionUnavailable, normalize_slider_weights, select_weighted_model


class ModelSelectionTest(unittest.TestCase):
    def test_normalize_slider_weights_defaults_missing_metrics_to_fifty(self):
        slider_weights, normalized = normalize_slider_weights(
            ["fitness", "precision", "simplicity"],
            {"fitness": 80},
        )

        self.assertEqual({"fitness": 80.0, "precision": 50.0, "simplicity": 50.0}, slider_weights)
        self.assertAlmostEqual(80.0 / 180.0, normalized["fitness"])
        self.assertAlmostEqual(50.0 / 180.0, normalized["precision"])
        self.assertAlmostEqual(50.0 / 180.0, normalized["simplicity"])

    def test_normalize_slider_weights_uses_uniform_distribution_when_all_are_zero(self):
        slider_weights, normalized = normalize_slider_weights(
            ["fitness", "precision"],
            {"fitness": 0, "precision": 0},
        )

        self.assertEqual({"fitness": 0.0, "precision": 0.0}, slider_weights)
        self.assertEqual({"fitness": 0.5, "precision": 0.5}, normalized)

    def test_select_weighted_model_returns_best_candidate(self):
        experiment = {
            "experiment_id": "exp-1",
            "metrics": ["fitness", "precision"],
        }
        solutions = [
            {"solution_id": 1, "objectives": [-0.80, -0.70], "is_pareto": True},
            {"solution_id": 2, "objectives": [-0.90, -0.40], "is_pareto": True},
            {"solution_id": 3, "objectives": [-0.30], "is_pareto": True},
        ]

        payload = select_weighted_model(
            experiment=experiment,
            solutions=solutions,
            raw_weights={"fitness": 80, "precision": 20},
            scope="pareto",
        )

        self.assertEqual("exp-1", payload["experiment_id"])
        self.assertEqual("pareto", payload["scope"])
        self.assertEqual(2, payload["candidate_count"])
        self.assertEqual(2, payload["selected_solution_id"])
        self.assertAlmostEqual(-0.8, payload["scalarized_objective"])

    def test_select_weighted_model_rejects_experiment_without_metrics(self):
        with self.assertRaises(ModelSelectionUnavailable):
            select_weighted_model(
                experiment={"experiment_id": "exp-1", "metrics": []},
                solutions=[{"solution_id": 1, "objectives": [-0.8]}],
                raw_weights={"fitness": 80},
                scope="pareto",
            )

    def test_select_weighted_model_rejects_when_no_valid_candidates_exist(self):
        with self.assertRaises(ModelSelectionUnavailable):
            select_weighted_model(
                experiment={"experiment_id": "exp-1", "metrics": ["fitness", "precision"]},
                solutions=[{"solution_id": 1, "objectives": [-0.8]}],
                raw_weights={"fitness": 80},
                scope="pareto",
            )


if __name__ == "__main__":
    unittest.main()
