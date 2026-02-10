import os
import sys
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pipeline_space import PipelineSearchSpace
from problem import PipelineOptimizationProblem


class PipelineOptimizationProblemTest(unittest.TestCase):
    def test_objectives_are_negated_for_maximization(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "experiment_id": "exp-1",
                "evaluation_id": "ev-1",
                "fingerprint": "fp-1",
                "metrics": {
                    "fitness": 0.9,
                    "precision": 0.8,
                    "simplicity": 0.7,
                    "generalisation": 0.6,
                },
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
            maximize_metrics=[True, True, True, True],
        )

        solution = problem.create_solution()
        evaluated = problem.evaluate(solution)
        self.assertEqual(evaluated.objectives, [-0.9, -0.8, -0.7, -0.6])
        self.assertIn("pipeline", evaluated.attributes)
        self.assertIn("metrics", evaluated.attributes)
        self.assertEqual(evaluated.attributes["evaluation_id"], "ev-1")
        self.assertEqual(evaluated.attributes["experiment_id"], "exp-1")
        self.assertEqual(evaluated.attributes["fingerprint"], "fp-1")

    def test_cache_prevents_duplicate_evaluations(self):
        space = PipelineSearchSpace(excluded_miners=("split",))
        call_count = {"n": 0}

        def evaluator(_log, _pipeline, _metrics):
            call_count["n"] += 1
            return {
                "fitness": 0.1,
                "precision": 0.2,
                "simplicity": 0.3,
                "generalisation": 0.4,
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )
        solution = problem.create_solution()

        problem.evaluate(solution)
        problem.evaluate(solution)
        self.assertEqual(call_count["n"], 1)

    def test_maximize_metrics_length_mismatch_raises(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {"fitness": 0.1}

        with self.assertRaises(ValueError):
            PipelineOptimizationProblem(
                log_path="dummy.xes",
                metrics_list=["fitness"],
                search_space=space,
                evaluator=evaluator,
                maximize_metrics=[True, False],
            )

    def test_cache_restores_attributes(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "experiment_id": "exp-1",
                "evaluation_id": "ev-2",
                "fingerprint": "fp-2",
                "metrics": {
                    "fitness": 0.4,
                    "precision": 0.3,
                    "simplicity": 0.2,
                    "generalisation": 0.1,
                },
            }

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )
        solution = problem.create_solution()
        problem.evaluate(solution)

        cached_solution = problem.create_solution()
        cached_solution.variables = list(solution.variables)
        evaluated_cached = problem.evaluate(cached_solution)
        self.assertEqual(evaluated_cached.attributes["evaluation_id"], "ev-2")
        self.assertEqual(evaluated_cached.attributes["fingerprint"], "fp-2")


if __name__ == "__main__":
    unittest.main()
