"""High-level orchestration for pipeline optimization."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from constraints import collect_required_metrics
from execution_control import ExecutionControl
from java_service_client import ProMServiceClient
from optimizer import PipelineNSGAIIIOptimizer
from pipeline_space import PipelineSearchSpace
from problem import PipelineOptimizationProblem


class OptimizedProcessMiner:
    """
    Optimizes full discovery pipeline:
    1. Preprocessing selection + parameters
    2. Mining algorithm family
    3. Miner variant + active parameters
    """

    def __init__(
        self,
        execution_name: str,
        log: str,
        metrics: Optional[List[str]] = None,
        constraints: Optional[List[Dict[str, Any]]] = None,
        service_url: Optional[str] = None,
        service_timeout_seconds: int = 300,
        conformance_mode: Optional[str] = None,
        excluded_miners: Optional[Sequence[str]] = ("ilp",),
        excluded_preprocessings: Optional[Sequence[str]] = None,
        execution_control: Optional[ExecutionControl] = None,
    ):
        self.execution_name = execution_name
        self.log_path = log
        self.metrics_list = metrics or ["fitness", "precision", "simplicity", "generalisation"]
        self.constraints = list(constraints or [])
        self.required_metrics = collect_required_metrics(self.metrics_list, self.constraints)
        self.service_url = service_url
        self.service_timeout_seconds = max(1, int(service_timeout_seconds))
        self.conformance_mode = (conformance_mode or "").strip() or None
        self.excluded_miners = tuple(excluded_miners or ())
        self.excluded_preprocessings = tuple(excluded_preprocessings or ())
        self.execution_control = execution_control or ExecutionControl()

        self.search_space: Optional[PipelineSearchSpace] = None
        self.problem: Optional[PipelineOptimizationProblem] = None
        self.optimizer: Optional[PipelineNSGAIIIOptimizer] = None
        self.service_client: Optional[ProMServiceClient] = None
        self.result = None
        self.non_dominated = None
        self.population_snapshots: List[Dict[str, Any]] = []

    def discover(
        self,
        service_url: Optional[str] = None,
        max_evaluations: int = 1000,
        population_size: int | None = 100,
        n_partitions: int | None = None,
        n_workers: int = 1,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        url = service_url or self.service_url
        if not url:
            raise ValueError("service_url is required to evaluate candidate pipelines")

        self.search_space = PipelineSearchSpace(
            excluded_miners=self.excluded_miners,
            log_path=self.log_path,
            excluded_preprocessings=self.excluded_preprocessings,
        )
        self.service_client = ProMServiceClient(
            base_url=url,
            experiment_id=self.execution_name,
            timeout_seconds=self.service_timeout_seconds,
            conformance_mode=self.conformance_mode,
            excluded_miners=self.excluded_miners,
            constraints=self.constraints,
        )

        self.problem = PipelineOptimizationProblem(
            log_path=self.log_path,
            metrics_list=self.metrics_list,
            required_metrics=self.required_metrics,
            constraints=self.constraints,
            search_space=self.search_space,
            evaluator=self.service_client.evaluate_pipeline,
            maximize_metrics=[True] * len(self.metrics_list),
            on_evaluation=progress_callback,
        )

        self.optimizer = PipelineNSGAIIIOptimizer(
            problem=self.problem,
            max_evaluations=max_evaluations,
            population_size=population_size,
            n_partitions=n_partitions,
            n_workers=n_workers,
            execution_control=self.execution_control,
        )
        self.optimizer.run()
        self.result = self.optimizer.get_result()
        self.non_dominated = self.optimizer.get_non_dominated()
        self.population_snapshots = self.optimizer.get_population_snapshots()
        return self.result

    def get_non_dominated_pipelines(self) -> List[Dict]:
        if self.non_dominated is None:
            return []
        return [solution.attributes.get("pipeline", {}) for solution in self.non_dominated]

    def get_non_dominated_metrics(self) -> List[Dict[str, float]]:
        if self.non_dominated is None:
            return []
        result = []
        for solution in self.non_dominated:
            metrics = solution.attributes.get("metrics", {})
            if metrics:
                result.append(metrics)
        return result

    def get_non_dominated_evaluation_ids(self) -> List[str]:
        if self.non_dominated is None:
            return []
        ids: List[str] = []
        seen = set()
        for solution in self.non_dominated:
            evaluation_id = solution.attributes.get("evaluation_id")
            if not evaluation_id:
                continue
            if evaluation_id in seen:
                continue
            seen.add(evaluation_id)
            ids.append(evaluation_id)
        return ids

    def fetch_non_dominated_artifacts(self, include_pnml: bool = True) -> List[Dict]:
        if self.service_client is None:
            raise ValueError("discover() must be executed before fetching artifacts")
        evaluation_ids = self.get_non_dominated_evaluation_ids()
        if not evaluation_ids:
            return []
        return self.service_client.fetch_artifacts(
            evaluation_ids=evaluation_ids,
            include_pnml=include_pnml,
            experiment_id=self.execution_name,
        )

    def cleanup_experiment_artifacts(self) -> Dict:
        if self.service_client is None:
            raise ValueError("discover() must be executed before cleaning artifacts")
        return self.service_client.cleanup_experiment(experiment_id=self.execution_name)

    def request_cancel(self) -> None:
        self.execution_control.request_cancel()
        if self.optimizer is not None:
            self.optimizer.cancel()

    def raise_if_cancel_requested(self) -> None:
        self.execution_control.raise_if_cancel_requested()
