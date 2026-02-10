"""NSGA-III optimizer wrapper for pipeline optimization."""

from __future__ import annotations

from typing import List

from jmetal.algorithm.multiobjective.nsgaiii import NSGAIII, UniformReferenceDirectionFactory
from jmetal.operator.crossover import SBXCrossover
from jmetal.operator.mutation import PolynomialMutation
from jmetal.util.ranking import FastNonDominatedRanking
from jmetal.util.termination_criterion import StoppingByEvaluations

from problem import PipelineOptimizationProblem


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
        )
        self.result = None
        self.non_dominated = None

    def run(self):
        self.algorithm.run()
        self.result = self.algorithm.result()
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

