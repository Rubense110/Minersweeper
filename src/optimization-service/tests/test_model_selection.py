import os
import sys
import unittest

import numpy as np
from pymoo.decomposition.asf import ASF

SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

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

    def test_select_weighted_model_returns_best_candidate_using_asf(self):
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

        expected_matrix = np.asarray([[-0.80, -0.70], [-0.90, -0.40]], dtype=float)
        ideal = expected_matrix.min(axis=0)
        nadir = expected_matrix.max(axis=0)
        normalized = (expected_matrix - ideal) / np.where((nadir - ideal) != 0.0, (nadir - ideal), 1.0)
        expected_score = float(ASF().do(normalized, 1.0 / np.asarray([0.8, 0.2], dtype=float))[1])

        self.assertEqual("exp-1", payload["experiment_id"])
        self.assertEqual("pareto", payload["scope"])
        self.assertEqual("asf", payload["selection_method"])
        self.assertEqual(2, payload["candidate_count"])
        self.assertEqual(2, payload["selected_solution_id"])
        self.assertAlmostEqual(expected_score, payload["scalarized_objective"])
        self.assertEqual(ideal.tolist(), payload["approx_ideal"])
        self.assertEqual(nadir.tolist(), payload["approx_nadir"])

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


    def test_select_weighted_model_tolerates_zero_slider_weight_for_asf(self):
        payload = select_weighted_model(
            experiment={"experiment_id": "exp-1", "metrics": ["fitness", "precision"]},
            solutions=[
                {"solution_id": 1, "objectives": [-0.9, -0.5]},
                {"solution_id": 2, "objectives": [-0.6, -0.9]},
            ],
            raw_weights={"fitness": 100, "precision": 0},
            scope="pareto",
        )

        self.assertEqual("asf", payload["selection_method"])
        self.assertEqual(1, payload["selected_solution_id"])


if __name__ == "__main__":
    unittest.main()
