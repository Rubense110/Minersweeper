"""jMetalPy problem definition for pipeline optimization."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, Tuple

from jmetal.core.problem import FloatProblem
from jmetal.core.solution import FloatSolution

from pipeline_space import PipelineSearchSpace


class PipelineOptimizationProblem(FloatProblem):
    """
    jMetalPy float problem where each solution decodes into:
    preprocessing + miner + active parameters.
    """

    def __init__(
        self,
        log_path: str,
        metrics_list: List[str],
        search_space: PipelineSearchSpace,
        evaluator: Callable[[str, Dict[str, Any], List[str]], Dict[str, float]],
        maximize_metrics: Sequence[bool] | None = None,
        use_cache: bool = True,
    ):
        super().__init__()
        if not metrics_list:
            raise ValueError("metrics_list cannot be empty")

        self.log_path = log_path
        self.metrics_list = metrics_list
        self.search_space = search_space
        self.evaluator = evaluator
        self.use_cache = use_cache
        self.evaluation_cache: Dict[Tuple[float, ...], List[float]] = {}

        self.maximize_metrics = list(maximize_metrics) if maximize_metrics is not None else [True] * len(metrics_list)
        if len(self.maximize_metrics) != len(metrics_list):
            raise ValueError("maximize_metrics must match metrics_list length")

        self.lower_bound = self.search_space.lower_bounds()
        self.upper_bound = self.search_space.upper_bounds()
        self.obj_directions = [self.MINIMIZE] * len(metrics_list)
        self.obj_labels = metrics_list

    def evaluate(self, solution: FloatSolution) -> FloatSolution:
        cache_key = tuple(round(value, 8) for value in solution.variables)
        if self.use_cache and cache_key in self.evaluation_cache:
            solution.objectives = self.evaluation_cache[cache_key]
            return solution

        decoded_pipeline = self.search_space.decode(solution.variables)
        metric_values = self.evaluator(self.log_path, decoded_pipeline, self.metrics_list)

        objectives: List[float] = []
        for metric_name, maximize in zip(self.metrics_list, self.maximize_metrics):
            value = float(metric_values[metric_name])
            objectives.append(-value if maximize else value)

        solution.objectives = objectives
        solution.attributes["pipeline"] = decoded_pipeline
        solution.attributes["metrics"] = metric_values
        if self.use_cache:
            self.evaluation_cache[cache_key] = objectives
        return solution

    def number_of_objectives(self) -> int:
        return len(self.metrics_list)

    def number_of_constraints(self) -> int:
        return 0

    def name(self) -> str:
        return "Pipeline Optimization Problem"

