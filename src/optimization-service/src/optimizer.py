"""NSGA-III optimizer wrapper for pipeline optimization."""

from __future__ import annotations

from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List

from execution_control import ExecutionControl, JobCancelled
from jmetal.algorithm.multiobjective.nsgaiii import NSGAIII, UniformReferenceDirectionFactory
from jmetal.operator.crossover import SBXCrossover
from jmetal.operator.mutation import PolynomialMutation
from jmetal.util.comparator import DominanceWithConstraintsComparator
from jmetal.util.evaluator import Evaluator, SequentialEvaluator
from jmetal.util.ranking import FastNonDominatedRanking
from jmetal.util.termination_criterion import StoppingByEvaluations

from problem import PipelineOptimizationProblem


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
    ):
        self.problem = problem
        self.execution_control = execution_control
        self.snapshot_callback = snapshot_callback
        self.population_snapshots: List[Dict[str, Any]] = []
        self.dominance_comparator = DominanceWithConstraintsComparator()

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
            dominance_comparator=self.dominance_comparator,
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
        ranking = FastNonDominatedRanking(self.dominance_comparator)
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
