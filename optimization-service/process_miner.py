"""High-level orchestration for pipeline optimization."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

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
        service_url: Optional[str] = None,
        excluded_miners: Optional[Sequence[str]] = ("split",),
    ):
        self.execution_name = execution_name
        self.log_path = log
        self.metrics_list = metrics or ["fitness", "precision", "simplicity", "generalisation"]
        self.service_url = service_url
        self.excluded_miners = tuple(excluded_miners or ())

        self.search_space: Optional[PipelineSearchSpace] = None
        self.problem: Optional[PipelineOptimizationProblem] = None
        self.optimizer: Optional[PipelineNSGAIIIOptimizer] = None
        self.result = None
        self.non_dominated = None

    def discover(
        self,
        service_url: Optional[str] = None,
        max_evaluations: int = 1000,
        population_size: int | None = 100,
        n_partitions: int | None = None,
    ):
        url = service_url or self.service_url
        if not url:
            raise ValueError("service_url is required to evaluate candidate pipelines")

        self.search_space = PipelineSearchSpace(excluded_miners=self.excluded_miners)
        service_client = ProMServiceClient(base_url=url)

        self.problem = PipelineOptimizationProblem(
            log_path=self.log_path,
            metrics_list=self.metrics_list,
            search_space=self.search_space,
            evaluator=service_client.evaluate_pipeline,
            maximize_metrics=[True] * len(self.metrics_list),
        )

        self.optimizer = PipelineNSGAIIIOptimizer(
            problem=self.problem,
            max_evaluations=max_evaluations,
            population_size=population_size,
            n_partitions=n_partitions,
        )
        self.optimizer.run()
        self.result = self.optimizer.get_result()
        self.non_dominated = self.optimizer.get_non_dominated()
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
