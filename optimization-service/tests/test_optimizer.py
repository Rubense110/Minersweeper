import os
import sys
import unittest

from jmetal.util.evaluator import SequentialEvaluator


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from optimizer import PipelineNSGAIIIOptimizer, ThreadPoolEvaluator
from pipeline_space import PipelineSearchSpace
from problem import PipelineOptimizationProblem


class PipelineNSGAIIIOptimizerTest(unittest.TestCase):
    def _build_problem(self):
        space = PipelineSearchSpace(excluded_miners=("split",))

        def evaluator(_log, pipeline, _metrics):
            params = pipeline["miner"]["parameters"]
            quality = float(len(params)) / 10.0
            return {
                "fitness": quality,
                "precision": quality * 0.9,
                "simplicity": quality * 0.8,
                "generalisation": quality * 0.7,
            }

        return PipelineOptimizationProblem(
            log_path="dummy.xes",
            metrics_list=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
        )

    def test_optimizer_runs_and_returns_non_dominated(self):
        problem = self._build_problem()

        optimizer = PipelineNSGAIIIOptimizer(
            problem=problem,
            max_evaluations=12,
            n_partitions=1,
        )
        optimizer.run()

        self.assertIsNotNone(optimizer.get_result())
        self.assertGreater(len(optimizer.get_result()), 0)
        self.assertIsNotNone(optimizer.get_non_dominated())
        self.assertGreater(len(optimizer.get_non_dominated()), 0)

    def test_optimizer_uses_sequential_evaluator_by_default(self):
        problem = self._build_problem()
        optimizer = PipelineNSGAIIIOptimizer(problem=problem, max_evaluations=4, n_partitions=1)
        self.assertIsInstance(optimizer.algorithm.population_evaluator, SequentialEvaluator)

    def test_optimizer_uses_thread_pool_evaluator_when_n_workers_gt_one(self):
        problem = self._build_problem()
        optimizer = PipelineNSGAIIIOptimizer(problem=problem, max_evaluations=4, n_partitions=1, n_workers=3)
        self.assertIsInstance(optimizer.algorithm.population_evaluator, ThreadPoolEvaluator)

    def test_optimizer_invalid_workers_raises(self):
        problem = self._build_problem()
        with self.assertRaises(ValueError):
            PipelineNSGAIIIOptimizer(problem=problem, n_workers=0)


if __name__ == "__main__":
    unittest.main()
