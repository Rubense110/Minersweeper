"""NSGA-III optimizer wrapper for pipeline optimization."""

from __future__ import annotations

import copy
import random
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List

from execution_control import ExecutionControl, JobCancelled
from jmetal.algorithm.multiobjective.nsgaiii import NSGAIII, UniformReferenceDirectionFactory
from jmetal.operator.crossover import SBXCrossover
from jmetal.operator.mutation import PolynomialMutation
from jmetal.util.comparator import MultiComparator
from jmetal.util.density_estimator import CrowdingDistanceDensityEstimator
from jmetal.util.evaluator import Evaluator, SequentialEvaluator
from jmetal.util.ranking import FastNonDominatedRanking
from jmetal.util.termination_criterion import StoppingByEvaluations

from problem import PipelineOptimizationProblem


class SeededBinaryTournamentSelection:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.comparator = MultiComparator(
            [FastNonDominatedRanking.get_comparator(), CrowdingDistanceDensityEstimator.get_comparator()]
        )

    def execute(self, front: List[Any]) -> Any:
        if not front:
            raise ValueError("The front is empty")
        if len(front) == 1:
            return front[0]
        idx1, idx2 = self.rng.sample(range(len(front)), 2)
        solution1 = front[idx1]
        solution2 = front[idx2]
        comparison = self.comparator.compare(solution1, solution2)
        if comparison == -1:
            return solution1
        if comparison == 1:
            return solution2
        return solution1 if self.rng.random() < 0.5 else solution2

    def get_name(self) -> str:
        return "Seeded binary tournament selection"


class SeededPolynomialMutation(PolynomialMutation):
    def __init__(self, probability: float, distribution_index: float, rng: random.Random):
        super().__init__(probability=probability, distribution_index=distribution_index)
        self.rng = rng

    def execute(self, solution):
        for i in range(len(solution.variables)):
            if self.rng.random() <= self.probability:
                y = solution.variables[i]
                yl, yu = solution.lower_bound[i], solution.upper_bound[i]
                if yl == yu:
                    y = yl
                else:
                    delta1 = (y - yl) / (yu - yl)
                    delta2 = (yu - y) / (yu - yl)
                    rnd = self.rng.random()
                    mut_pow = 1.0 / (self.distribution_index + 1.0)
                    if rnd <= 0.5:
                        xy = 1.0 - delta1
                        val = 2.0 * rnd + (1.0 - 2.0 * rnd) * pow(xy, self.distribution_index + 1.0)
                        deltaq = pow(val, mut_pow) - 1.0
                    else:
                        xy = 1.0 - delta2
                        val = 2.0 * (1.0 - rnd) + 2.0 * (rnd - 0.5) * pow(xy, self.distribution_index + 1.0)
                        deltaq = 1.0 - pow(val, mut_pow)
                    y += deltaq * (yu - yl)
                    y = max(yl, min(y, yu))
                    solution.variables[i] = y
        return solution


class SeededSBXCrossover(SBXCrossover):
    __EPS = 1.0e-14

    def __init__(self, probability: float, distribution_index: float, rng: random.Random):
        super().__init__(probability=probability, distribution_index=distribution_index)
        self.rng = rng

    def execute(self, parents: List[Any]) -> List[Any]:
        if len(parents) != 2:
            raise ValueError("The number of parents is not two: {}".format(len(parents)))

        offspring = copy.deepcopy(parents)
        if self.rng.random() <= self.probability:
            for i in range(len(parents[0].variables)):
                value_x1, value_x2 = parents[0].variables[i], parents[1].variables[i]
                if self.rng.random() <= 0.5 and abs(value_x1 - value_x2) > self.__EPS:
                    if value_x1 < value_x2:
                        y1, y2 = value_x1, value_x2
                    else:
                        y1, y2 = value_x2, value_x1

                    try:
                        lb1, ub1 = parents[0].lower_bound[i], parents[0].upper_bound[i]
                        beta1 = 1.0 + (2.0 * (y1 - lb1) / (y2 - y1))
                        alpha1 = 2.0 - pow(beta1, -(self.distribution_index + 1.0))
                        rand_val = self.rng.random()
                        if rand_val <= (1.0 / alpha1):
                            betaq1 = pow(rand_val * alpha1, 1.0 / (self.distribution_index + 1.0))
                        else:
                            betaq1 = pow(1.0 / (2.0 - rand_val * alpha1), 1.0 / (self.distribution_index + 1.0))
                        c1 = 0.5 * (y1 + y2 - betaq1 * (y2 - y1))

                        lb2, ub2 = parents[1].lower_bound[i], parents[1].upper_bound[i]
                        beta2 = 1.0 + (2.0 * (ub2 - y2) / (y2 - y1))
                        alpha2 = 2.0 - pow(beta2, -(self.distribution_index + 1.0))
                        if rand_val <= (1.0 / alpha2):
                            betaq2 = pow(rand_val * alpha2, 1.0 / (self.distribution_index + 1.0))
                        else:
                            betaq2 = pow(1.0 / (2.0 - rand_val * alpha2), 1.0 / (self.distribution_index + 1.0))
                        c2 = 0.5 * (y1 + y2 + betaq2 * (y2 - y1))
                    except (ValueError, ZeroDivisionError):
                        c1, c2 = y1, y2
                        lb1, ub1 = parents[0].lower_bound[i], parents[0].upper_bound[i]
                        lb2, ub2 = parents[1].lower_bound[i], parents[1].upper_bound[i]

                    if isinstance(c1, complex):
                        c1 = c1.real
                    if isinstance(c2, complex):
                        c2 = c2.real
                    c1 = max(lb1, min(c1, ub1))
                    c2 = max(lb2, min(c2, ub2))

                    if self.rng.random() <= 0.5:
                        offspring[0].variables[i] = c2
                        offspring[1].variables[i] = c1
                    else:
                        offspring[0].variables[i] = c1
                        offspring[1].variables[i] = c2
                else:
                    offspring[0].variables[i] = value_x1
                    offspring[1].variables[i] = value_x2
        return offspring


class ThreadPoolEvaluator(Evaluator):
    """Thread-based evaluator suitable for IO-bound objective functions."""

    def __init__(self, max_workers: int, execution_control: ExecutionControl | None = None):
        super().__init__()
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.execution_control = execution_control

    def evaluate(self, solution_list: List, problem):
        self.raise_if_cancel_requested()
        futures = [self.executor.submit(Evaluator.evaluate_solution, solution, problem) for solution in solution_list]
        try:
            for future in as_completed(futures):
                try:
                    future.result()
                except CancelledError as error:
                    raise JobCancelled("job cancelled") from error
            self.raise_if_cancel_requested()
        except JobCancelled:
            for future in futures:
                future.cancel()
            raise
        return solution_list

    def raise_if_cancel_requested(self) -> None:
        if self.execution_control is not None:
            self.execution_control.raise_if_cancel_requested()

    def shutdown(self, wait: bool = True, cancel_futures: bool = False):
        self.executor.shutdown(wait=wait, cancel_futures=cancel_futures)

    def cancel(self) -> None:
        self.shutdown(wait=False, cancel_futures=True)

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass


class CancelAwareNSGAIII(NSGAIII):
    def __init__(
        self,
        *args,
        execution_control: ExecutionControl | None = None,
        snapshot_callback: Callable[[int, List[Any]], None] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.execution_control = execution_control
        self.snapshot_callback = snapshot_callback

    def stopping_condition_is_met(self) -> bool:
        if self.execution_control is not None and self.execution_control.is_cancel_requested():
            return True
        return super().stopping_condition_is_met()

    def init_progress(self) -> None:
        super().init_progress()
        self._emit_snapshot()

    def update_progress(self) -> None:
        super().update_progress()
        self._emit_snapshot()

    def _emit_snapshot(self) -> None:
        if self.snapshot_callback is None:
            return
        self.snapshot_callback(int(self.evaluations or 0), list(self.solutions or []))


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
        execution_control: ExecutionControl | None = None,
        snapshot_callback: Callable[[Dict[str, Any]], None] | None = None,
        seed: int | None = None,
        rng: random.Random | None = None,
    ):
        self.problem = problem
        self.execution_control = execution_control
        self.snapshot_callback = snapshot_callback
        self.population_snapshots: List[Dict[str, Any]] = []
        self.seed = seed
        self.rng = rng or random.Random(seed)

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
        population_evaluator = (
            ThreadPoolEvaluator(max_workers=n_workers, execution_control=execution_control)
            if n_workers > 1
            else SequentialEvaluator()
        )

        self.algorithm = CancelAwareNSGAIII(
            reference_directions=self.reference_directions,
            problem=self.problem,
            population_size=population_size,
            mutation=SeededPolynomialMutation(
                probability=mutation_probability,
                distribution_index=mutation_distribution_index,
                rng=self.rng,
            ),
            crossover=SeededSBXCrossover(
                probability=crossover_probability,
                distribution_index=crossover_distribution_index,
                rng=self.rng,
            ),
            selection=SeededBinaryTournamentSelection(self.rng),
            termination_criterion=StoppingByEvaluations(max_evaluations=max_evaluations),
            population_evaluator=population_evaluator,
            execution_control=execution_control,
            snapshot_callback=self._store_population_snapshot,
        )
        self.result = None
        self.non_dominated = None

    def run(self):
        self.raise_if_cancel_requested()
        self.algorithm.run()
        self.raise_if_cancel_requested()
        # In jMetalPy NSGAIII, result() returns only the non-dominated front.
        # We need the full final population for downstream persistence/API.
        population = list(getattr(self.algorithm, "solutions", []) or [])
        if not population:
            population = list(self.algorithm.result() or [])
        self.result = population
        self.non_dominated = self._calculate_non_dominated(self.result)
        return self.result

    def _calculate_non_dominated(self, solutions: List):
        ranking = FastNonDominatedRanking()
        ranking.compute_ranking(solutions)
        return ranking.get_subfront(0)

    def get_result(self):
        return self.result

    def get_non_dominated(self):
        return self.non_dominated

    def get_population_snapshots(self) -> List[Dict[str, Any]]:
        return list(self.population_snapshots)

    def cancel(self) -> None:
        population_evaluator = getattr(self.algorithm, "population_evaluator", None)
        if hasattr(population_evaluator, "cancel"):
            population_evaluator.cancel()

    def raise_if_cancel_requested(self) -> None:
        if self.execution_control is not None:
            self.execution_control.raise_if_cancel_requested()

    def _store_population_snapshot(self, evaluations_done: int, solutions: List[Any]) -> None:
        snapshot = {
            "snapshot_index": len(self.population_snapshots) + 1,
            "evaluations_done": int(evaluations_done),
            "solutions": list(solutions or []),
        }
        self.population_snapshots.append(snapshot)

        if self.snapshot_callback is not None:
            self.snapshot_callback(dict(snapshot))
