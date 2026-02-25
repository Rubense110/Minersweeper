"""NSGA-III optimizer wrapper for pipeline optimization."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import List

from jmetal.algorithm.multiobjective.nsgaiii import NSGAIII, UniformReferenceDirectionFactory
from jmetal.operator.crossover import SBXCrossover
from jmetal.operator.mutation import PolynomialMutation
from jmetal.util.evaluator import Evaluator, SequentialEvaluator
from jmetal.util.ranking import FastNonDominatedRanking
from jmetal.util.termination_criterion import StoppingByEvaluations

from problem import PipelineOptimizationProblem


class ThreadPoolEvaluator(Evaluator):
    """Thread-based evaluator suitable for IO-bound objective functions."""

    def __init__(self, max_workers: int):
        super().__init__()
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def evaluate(self, solution_list: List, problem):
        futures = [self.executor.submit(Evaluator.evaluate_solution, solution, problem) for solution in solution_list]
        for future in futures:
            future.result()
        return solution_list

    def shutdown(self):
        self.executor.shutdown(wait=True, cancel_futures=False)

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass


class PipelineNSGAIIIOptimizer:
    def __init__(
        self,
        problem: PipelineOptimizationProblem,
        max_evaluations: int = 300,
        population_size: int | None = None,
        n_partitions: int | None = None,
        crossover_probability: float = 0.9,
        crossover_distribution_index: float = 20.0,
        mutation_probability: float | None = None,
        mutation_distribution_index: float = 20.0,
        n_workers: int = 1,
    ):
        self.problem = problem

        n_obj = self.problem.number_of_objectives()
        if n_partitions is None:
            n_partitions = 8 if n_obj >= 4 else 12
        self.reference_directions = UniformReferenceDirectionFactory(n_dim=n_obj, n_partitions=n_partitions)

        if population_size is None:
            population_size = len(self.reference_directions.compute())

        if mutation_probability is None:
            mutation_probability = 1.0 / max(1, self.problem.number_of_variables())

        if n_workers < 1:
            raise ValueError("n_workers must be >= 1")
        population_evaluator = ThreadPoolEvaluator(max_workers=n_workers) if n_workers > 1 else SequentialEvaluator()

        self.algorithm = NSGAIII(
            reference_directions=self.reference_directions,
            problem=self.problem,
            population_size=population_size,
            mutation=PolynomialMutation(
                probability=mutation_probability,
                distribution_index=mutation_distribution_index,
            ),
            crossover=SBXCrossover(
                probability=crossover_probability,
                distribution_index=crossover_distribution_index,
            ),
            termination_criterion=StoppingByEvaluations(max_evaluations=max_evaluations),
            population_evaluator=population_evaluator,
        )
        self.result = None
        self.non_dominated = None

    def run(self):
        self.algorithm.run()
        # In jMetalPy NSGAIII, result() returns only the non-dominated front.
        # We need the full final population for downstream persistence/API.
        population = list(getattr(self.algorithm, "solutions", []) or [])
        if not population:
            population = list(self.algorithm.result() or [])
        self.result = population
        self.non_dominated = self._calculate_non_dominated(self.result)
        return self.result

    @staticmethod
    def _calculate_non_dominated(solutions: List):
        ranking = FastNonDominatedRanking()
        ranking.compute_ranking(solutions)
        return ranking.get_subfront(0)

    def get_result(self):
        return self.result

    def get_non_dominated(self):
        return self.non_dominated
