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
        evaluator: Callable[[str, Dict[str, Any], List[str]], Dict[str, Any]],
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
        self.evaluation_cache: Dict[Tuple[float, ...], Dict[str, Any]] = {}

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
            cached = self.evaluation_cache[cache_key]
            solution.objectives = cached["objectives"]
            solution.attributes["pipeline"] = cached["pipeline"]
            solution.attributes["metrics"] = cached["metrics"]
            if cached.get("evaluation_id"):
                solution.attributes["evaluation_id"] = cached["evaluation_id"]
            if cached.get("experiment_id"):
                solution.attributes["experiment_id"] = cached["experiment_id"]
            if cached.get("fingerprint"):
                solution.attributes["fingerprint"] = cached["fingerprint"]
            return solution

        decoded_pipeline = self.search_space.decode(solution.variables)
        evaluation_payload = self.evaluator(self.log_path, decoded_pipeline, self.metrics_list)
        if "metrics" in evaluation_payload and isinstance(evaluation_payload["metrics"], dict):
            metric_values = evaluation_payload["metrics"]
            evaluation_id = evaluation_payload.get("evaluation_id")
            experiment_id = evaluation_payload.get("experiment_id")
            fingerprint = evaluation_payload.get("fingerprint")
        else:
            metric_values = evaluation_payload
            evaluation_id = None
            experiment_id = None
            fingerprint = None

        objectives: List[float] = []
        for metric_name, maximize in zip(self.metrics_list, self.maximize_metrics):
            value = float(metric_values[metric_name])
            objectives.append(-value if maximize else value)

        solution.objectives = objectives
        solution.attributes["pipeline"] = decoded_pipeline
        solution.attributes["metrics"] = metric_values
        if evaluation_id:
            solution.attributes["evaluation_id"] = evaluation_id
        if experiment_id:
            solution.attributes["experiment_id"] = experiment_id
        if fingerprint:
            solution.attributes["fingerprint"] = fingerprint
        if self.use_cache:
            self.evaluation_cache[cache_key] = {
                "objectives": objectives,
                "pipeline": decoded_pipeline,
                "metrics": metric_values,
                "evaluation_id": evaluation_id,
                "experiment_id": experiment_id,
                "fingerprint": fingerprint,
            }
        return solution

    def number_of_objectives(self) -> int:
        return len(self.metrics_list)

    def number_of_constraints(self) -> int:
        return 0

    def name(self) -> str:
        return "Pipeline Optimization Problem"
