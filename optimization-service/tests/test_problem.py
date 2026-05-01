import os
import sys
import unittest
import math


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pipeline_space import PipelineSearchSpace
from problem import PipelineOptimizationProblem
from execution_control import JobCancelled


class PipelineOptimizationProblemTest(unittest.TestCase):
    def test_objectives_are_negated_for_maximization(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "experiment_id": "exp-1",
                "evaluation_id": "ev-1",
                "fingerprint": "fp-1",
                "runtime_ms": 123,
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
        self.assertEqual(evaluated.attributes["runtime_ms"], 123)

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
                "runtime_ms": 77,
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
        self.assertEqual(evaluated_cached.attributes["runtime_ms"], 77)

    def test_evaluator_error_is_penalized_without_crash(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            raise RuntimeError("service unavailable")

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )

        solution = problem.create_solution()
        evaluated = problem.evaluate(solution)
        self.assertEqual(evaluated.objectives, [0.0, 0.0, 0.0, 0.0])
        self.assertIn("evaluation_error", evaluated.attributes)
        self.assertIn("runtime_ms", evaluated.attributes)
        self.assertGreaterEqual(evaluated.attributes["runtime_ms"], 0)

    def test_non_finite_metric_values_are_sanitized(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            return {
                "metrics": {
                    "fitness": 0.5,
                    "precision": float("nan"),
                    "simplicity": 0.8,
                    "generalisation": 1.0,
                }
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
        self.assertTrue(all(math.isfinite(value) for value in evaluated.objectives))
        self.assertEqual(evaluated.objectives[0], -0.5)
        self.assertEqual(evaluated.objectives[1], -0.0)
        self.assertIn("evaluation_error", evaluated.attributes)

    def test_job_cancelled_is_propagated(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, _pipeline, _metrics):
            raise JobCancelled("job cancelled")

        problem = PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )

        with self.assertRaises(JobCancelled):
            problem.evaluate(problem.create_solution())


if __name__ == "__main__":
    unittest.main()
