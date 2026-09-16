import os
import sys
import random
import unittest

from jmetal.core.solution import FloatSolution
from jmetal.util.comparator import DominanceWithConstraintsComparator
from jmetal.util.evaluator import SequentialEvaluator


SERVICE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SERVICE_SRC not in sys.path:
    sys.path.insert(0, SERVICE_SRC)

from optimizer import PipelineNSGAIIIOptimizer, SeededPolynomialMutation, SeededSBXCrossover, ThreadPoolEvaluator
from pareto import feasible_non_dominated_evaluation_ids
from pipeline_space import PipelineSearchSpace
from problem import PipelineOptimizationProblem


class PipelineNSGAIIIOptimizerTest(unittest.TestCase):
    @staticmethod
    def _solution(evaluation_id, objectives, constraint, is_feasible):
        solution = FloatSolution([0.0], [1.0], len(objectives), 1)
        solution.objectives = list(objectives)
        solution.constraints = [constraint]
        solution.attributes["evaluation_id"] = evaluation_id
        solution.attributes["is_feasible"] = is_feasible
        return solution

    def _build_problem(self, seed=None):
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
            required_metrics=["fitness", "precision", "simplicity", "generalisation"],
            search_space=space,
            evaluator=evaluator,
            rng=random.Random(seed) if seed is not None else None,
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

    def test_feasible_solution_dominates_infeasible_solution_with_better_objectives(self):
        optimizer = PipelineNSGAIIIOptimizer(problem=self._build_problem(), max_evaluations=4, n_partitions=1)
        feasible = self._solution("feasible", [-0.8, -0.8, -0.8, -0.8], 0.0, True)
        infeasible = self._solution("infeasible", [-1.0, -1.0, -1.0, -1.0], -1.0, False)

        front = optimizer._calculate_non_dominated([feasible, infeasible])

        self.assertIsInstance(optimizer.algorithm.dominance_comparator, DominanceWithConstraintsComparator)
        self.assertEqual([feasible], front)
        self.assertEqual({"feasible"}, feasible_non_dominated_evaluation_ids([feasible, infeasible]))

    def test_feasible_front_keeps_mutually_non_dominated_solutions_and_excludes_infeasible(self):
        optimizer = PipelineNSGAIIIOptimizer(problem=self._build_problem(), max_evaluations=4, n_partitions=1)
        first = self._solution("first", [-0.9, -0.3], 0.0, True)
        second = self._solution("second", [-0.3, -0.9], 0.0, True)
        infeasible = self._solution("infeasible", [-1.0, -1.0], -1.0, False)

        self.assertEqual([first, second], optimizer._calculate_non_dominated([first, second, infeasible]))

    def test_feasible_front_is_empty_when_every_solution_is_infeasible(self):
        optimizer = PipelineNSGAIIIOptimizer(problem=self._build_problem(), max_evaluations=4, n_partitions=1)
        first = self._solution("first", [-1.0, -1.0], -1.0, False)
        second = self._solution("second", [-0.5, -0.5], -1.0, False)

        self.assertEqual([], optimizer._calculate_non_dominated([first, second]))

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

    def test_optimizer_captures_generation_snapshots(self):
        problem = self._build_problem()

        optimizer = PipelineNSGAIIIOptimizer(
            problem=problem,
            max_evaluations=8,
            population_size=4,
            n_partitions=1,
        )
        optimizer.run()

        snapshots = optimizer.get_population_snapshots()
        self.assertEqual(2, len(snapshots))
        self.assertEqual([1, 2], [snapshot["snapshot_index"] for snapshot in snapshots])
        self.assertEqual([4, 8], [snapshot["evaluations_done"] for snapshot in snapshots])
        self.assertTrue(all(len(snapshot["solutions"]) == 4 for snapshot in snapshots))


    def test_seeded_variation_operators_modify_solution_variables(self):
        parent1 = FloatSolution([0.0, 0.0], [1.0, 1.0], 2, 0)
        parent2 = FloatSolution([0.0, 0.0], [1.0, 1.0], 2, 0)
        parent1.variables = [0.2, 0.8]
        parent2.variables = [0.8, 0.2]

        crossover = SeededSBXCrossover(probability=1.0, distribution_index=20.0, rng=random.Random(7))
        offspring = crossover.execute([parent1, parent2])

        self.assertNotEqual(parent1.variables, offspring[0].variables)
        self.assertNotEqual(parent2.variables, offspring[1].variables)

        mutation_target = FloatSolution([0.0, 0.0], [1.0, 1.0], 2, 0)
        mutation_target.variables = [0.5, 0.5]
        mutation = SeededPolynomialMutation(probability=1.0, distribution_index=20.0, rng=random.Random(11))
        mutation.execute(mutation_target)

        self.assertNotEqual([0.5, 0.5], mutation_target.variables)

    def test_seeded_optimizer_reproduces_final_population(self):
        def run_once():
            problem = self._build_problem(seed=42)
            optimizer = PipelineNSGAIIIOptimizer(
                problem=problem,
                max_evaluations=8,
                population_size=4,
                n_partitions=1,
                seed=42,
                rng=problem.rng,
            )
            optimizer.run()
            return [
                [round(value, 10) for value in solution.variables]
                for solution in optimizer.get_result()
            ]

        self.assertEqual(run_once(), run_once())


if __name__ == "__main__":
    unittest.main()
