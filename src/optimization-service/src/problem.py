"""jMetalPy problem definition for pipeline optimization."""

from __future__ import annotations

import json
import math
import random
import threading
import time
from copy import deepcopy
from typing import Any, Callable, Dict, List, Sequence

from execution_control import JobCancelled, EvaluationTerminationUnconfirmed, ReproducibilityError, ExecutionControl
from jmetal.core.problem import FloatProblem
from jmetal.core.solution import FloatSolution
from model_quality import validate_v3_feasibility

from pipeline_space import PipelineSearchSpace
from preprocessing_constraints import repair_pipeline_preprocessing


class PipelineOptimizationProblem(FloatProblem):
    """
    jMetalPy float problem where each solution decodes into:
    preprocessing + miner + active parameters.
    """

    _EVALUATION_ATTRIBUTE_KEYS = (
        "pipeline",
        "metrics",
        "metrics_status",
        "objective_metrics",
        "runtime_ms",
        "evaluation_error",
        "evaluation_id",
        "experiment_id",
        "fingerprint",
        "model_schema_version",
        "is_feasible",
        "constraint_violations",
        "visible_transition_count",
        "is_pareto",
        "evaluation_policy_version",
        "model_semantic_sha256",
        "evaluation_environment",
        "discovery_metadata",
    )

    def __init__(
        self,
        log_path: str,
        metrics_list: List[str],
        required_metrics: List[str],
        search_space: PipelineSearchSpace,
        evaluator: Callable[[str, Dict[str, Any], List[str]], Dict[str, Any]],
        maximize_metrics: Sequence[bool] | None = None,
        use_cache: bool = True,
        on_evaluation: Callable[[Dict[str, Any]], None] | None = None,
        rng: random.Random | None = None,
        execution_control: ExecutionControl | None = None,
    ):
        super().__init__()
        if not metrics_list:
            raise ValueError("metrics_list cannot be empty")

        self.log_path = log_path
        self.metrics_list = metrics_list
        self.required_metrics = list(required_metrics or metrics_list)
        self.search_space = search_space
        self.evaluator = evaluator
        self.execution_control = execution_control
        self.use_cache = use_cache
        self.evaluation_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_inflight: Dict[str, threading.Event] = {}
        self._cache_lock = threading.Lock()
        self.on_evaluation = on_evaluation
        self.rng = rng or random.Random()
        self._evaluations_done = 0
        self._eval_lock = threading.Lock()

        self.maximize_metrics = list(maximize_metrics) if maximize_metrics is not None else [True] * len(metrics_list)
        if len(self.maximize_metrics) != len(metrics_list):
            raise ValueError("maximize_metrics must match metrics_list length")

        self.lower_bound = self.search_space.lower_bounds()
        self.upper_bound = self.search_space.upper_bounds()
        self.obj_directions = [self.MINIMIZE] * len(metrics_list)
        self.obj_labels = metrics_list

    def create_solution(self) -> FloatSolution:
        solution = FloatSolution(
            self.lower_bound,
            self.upper_bound,
            self.number_of_objectives(),
            self.number_of_constraints(),
        )
        solution.variables = [
            self.rng.uniform(self.lower_bound[index], self.upper_bound[index])
            for index in range(self.number_of_variables())
        ]
        return solution

    def evaluate(self, solution: FloatSolution) -> FloatSolution:
        self._clear_evaluation_state(solution)
        solution.objectives = [0.0] * self.number_of_objectives()
        solution.constraints = [0.0] * self.number_of_constraints()
        self.raise_if_cancel_requested()

        decoded_pipeline = repair_pipeline_preprocessing(
            self.log_path,
            self.search_space.decode(solution.variables),
        )
        if not self.use_cache:
            return self._evaluate_uncached(solution, decoded_pipeline, None)

        # Only the effective request is relevant: inactive genes and selector
        # values that decode to the same option must share an evaluation.
        cache_key = json.dumps(
            decoded_pipeline,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        while True:
            with self._cache_lock:
                cached = self.evaluation_cache.get(cache_key)
                if cached is not None:
                    break
                inflight = self._cache_inflight.get(cache_key)
                if inflight is None:
                    inflight = threading.Event()
                    self._cache_inflight[cache_key] = inflight
                    break
            # Do not hold the lock during a ProM call, or while waiting for one.
            inflight.wait(timeout=0.1)
            self.raise_if_cancel_requested()

        if cached is not None:
            solution.objectives = list(cached["objectives"])
            solution.constraints = list(cached["constraints"])
            solution.attributes["pipeline"] = deepcopy(cached["pipeline"])
            solution.attributes["metrics"] = dict(cached["metrics"])
            solution.attributes["metrics_status"] = cached.get("metrics_status", "computed")
            solution.attributes["objective_metrics"] = dict(cached["objective_metrics"])
            if cached.get("runtime_ms") is not None:
                solution.attributes["runtime_ms"] = cached["runtime_ms"]
            if cached.get("evaluation_error"):
                solution.attributes["evaluation_error"] = cached["evaluation_error"]
            if cached.get("evaluation_id"):
                solution.attributes["evaluation_id"] = cached["evaluation_id"]
            if cached.get("experiment_id"):
                solution.attributes["experiment_id"] = cached["experiment_id"]
            if cached.get("fingerprint"):
                solution.attributes["fingerprint"] = cached["fingerprint"]
            if cached.get("model_schema_version") is not None:
                solution.attributes["model_schema_version"] = cached["model_schema_version"]
            if cached.get("is_feasible") is not None:
                solution.attributes["is_feasible"] = cached["is_feasible"]
                solution.attributes["constraint_violations"] = list(cached["constraint_violations"])
                solution.attributes["visible_transition_count"] = cached["visible_transition_count"]
            for key in ("evaluation_policy_version", "model_semantic_sha256", "evaluation_environment", "discovery_metadata"):
                if cached.get(key) is not None:
                    solution.attributes[key] = cached[key]
            self._notify_evaluation(
                logical_attempt_id=solution.attributes.get("logical_attempt_id"),
                cache_hit=True,
                has_error=bool(cached.get("evaluation_error")),
                evaluation_error=cached.get("evaluation_error"),
                pipeline=cached.get("pipeline"),
                metrics=cached.get("metrics"),
                runtime_ms=0,
                cached_runtime_ms=cached.get("runtime_ms"),
                evaluation_id=cached.get("evaluation_id"),
                experiment_id=cached.get("experiment_id"),
                fingerprint=cached.get("fingerprint"),
                evaluation_policy_version=cached.get("evaluation_policy_version"),
                model_semantic_sha256=cached.get("model_semantic_sha256"),
                evaluation_environment=cached.get("evaluation_environment"),
                discovery_metadata=cached.get("discovery_metadata"),
            )
            return solution

        try:
            return self._evaluate_uncached(solution, decoded_pipeline, cache_key)
        finally:
            with self._cache_lock:
                self._cache_inflight.pop(cache_key).set()

    def _evaluate_uncached(
        self,
        solution: FloatSolution,
        decoded_pipeline: Dict[str, Any],
        cache_key: str | None,
    ) -> FloatSolution:
        eval_started_ns = time.perf_counter_ns()
        metrics_status = "computed"
        try:
            evaluation_payload = self.evaluator(self.log_path, decoded_pipeline, self.required_metrics)
            self.raise_if_cancel_requested()
            runtime_ms = int((time.perf_counter_ns() - eval_started_ns) / 1_000_000)
            if "metrics" in evaluation_payload and isinstance(evaluation_payload["metrics"], dict):
                metric_values = evaluation_payload["metrics"]
                metrics_status = evaluation_payload.get("metrics_status", "computed")
                evaluation_id = evaluation_payload.get("evaluation_id")
                experiment_id = evaluation_payload.get("experiment_id")
                fingerprint = evaluation_payload.get("fingerprint")
                model_schema_version = evaluation_payload.get("model_schema_version")
                payload_runtime_ms = evaluation_payload.get("runtime_ms")
                if payload_runtime_ms is not None:
                    try:
                        runtime_ms = int(payload_runtime_ms)
                    except (TypeError, ValueError):
                        pass
                visible_transition_count = evaluation_payload.get("visible_transition_count")
                is_feasible = evaluation_payload.get("is_feasible")
                constraint_violations = evaluation_payload.get("constraint_violations")
            else:
                metric_values = evaluation_payload
                evaluation_id = None
                experiment_id = None
                fingerprint = None
                model_schema_version = None
                visible_transition_count = None
                is_feasible = None
                constraint_violations = None
            evaluation_error = None
        except (EvaluationTerminationUnconfirmed, ReproducibilityError) as error:
            if self.execution_control is not None:
                self.execution_control.request_failure(error)
            raise
        except JobCancelled:
            raise
        except Exception as error:  # noqa: BLE001 - We must keep optimization running.
            runtime_ms = int((time.perf_counter_ns() - eval_started_ns) / 1_000_000)
            metric_values = {
                metric_name: (0.0 if maximize else 1.0)
                for metric_name, maximize in zip(self.metrics_list, self.maximize_metrics)
            }
            evaluation_id = None
            experiment_id = None
            fingerprint = None
            model_schema_version = None
            evaluation_error = str(error) or type(error).__name__
            visible_transition_count = None
            is_feasible = None
            constraint_violations = None

        if not isinstance(metric_values, dict):
            raise ValueError("evaluator returned an invalid metrics payload")
        metric_values = dict(metric_values)

        objectives: List[float] = []
        objective_metrics: Dict[str, float] = {}
        for metric_name, maximize in zip(self.metrics_list, self.maximize_metrics):
            fallback = 0.0 if maximize else 1.0
            skipped = metrics_status == "skipped_infeasible"
            if skipped and is_feasible is not False:
                raise ValueError("Only infeasible models can skip metrics")
            raw_value = fallback if skipped else metric_values.get(metric_name)
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                value = fallback
                if evaluation_error is None:
                    evaluation_error = f"invalid metric value for '{metric_name}': {raw_value!r}"
            else:
                if not math.isfinite(value):
                    value = fallback
                    if evaluation_error is None:
                        evaluation_error = f"non-finite metric value for '{metric_name}': {raw_value!r}"
            if not skipped:
                metric_values[metric_name] = value
            objective_metrics[metric_name] = value
            objectives.append(-value if maximize else value)

        if evaluation_error is None and isinstance(evaluation_payload, dict):
            for key in ("evaluation_policy_version", "model_semantic_sha256", "evaluation_environment", "discovery_metadata"):
                if evaluation_payload.get(key) is not None:
                    solution.attributes[key] = evaluation_payload[key]
        solution.objectives = objectives
        solution.attributes["pipeline"] = decoded_pipeline
        solution.attributes["metrics"] = metric_values
        solution.attributes["metrics_status"] = metrics_status
        solution.attributes["objective_metrics"] = objective_metrics
        solution.attributes["runtime_ms"] = runtime_ms
        if model_schema_version is not None:
            if not isinstance(model_schema_version, int) or isinstance(model_schema_version, bool):
                raise ValueError("evaluator returned an invalid model_schema_version")
            if model_schema_version not in (2, 3):
                raise ValueError(f"unsupported model_schema_version: {model_schema_version}")
            solution.attributes["model_schema_version"] = model_schema_version
            if not isinstance(is_feasible, bool):
                raise ValueError("versioned evaluator response is missing feasibility metadata")

        if isinstance(is_feasible, bool):
            if not isinstance(visible_transition_count, int) or isinstance(visible_transition_count, bool):
                raise ValueError("evaluator returned an invalid visible_transition_count")
            if not isinstance(constraint_violations, list) or not all(
                isinstance(item, str) for item in constraint_violations
            ):
                raise ValueError("evaluator returned invalid constraint_violations")
            if model_schema_version == 3:
                validate_v3_feasibility(visible_transition_count, is_feasible, constraint_violations)
            else:
                expected_violations = [] if is_feasible else ["NO_VISIBLE_TRANSITIONS"]
                if constraint_violations != expected_violations:
                    raise ValueError("evaluator returned inconsistent feasibility metadata")
                if is_feasible != (visible_transition_count > 0):
                    raise ValueError("evaluator returned inconsistent visible_transition_count")
            solution.constraints[0] = 0.0 if is_feasible else -1.0
            solution.attributes["is_feasible"] = is_feasible
            solution.attributes["constraint_violations"] = constraint_violations
            solution.attributes["visible_transition_count"] = visible_transition_count
        else:
            solution.constraints[0] = 0.0
        if evaluation_error is not None:
            # A technical failure cannot compete as an unconstrained candidate,
            # even if the returned net passed the model-quality checks.
            solution.constraints[0] = -1.0
            solution.attributes["evaluation_error"] = evaluation_error
        if evaluation_id:
            solution.attributes["evaluation_id"] = evaluation_id
        if experiment_id:
            solution.attributes["experiment_id"] = experiment_id
        if fingerprint:
            solution.attributes["fingerprint"] = fingerprint
        if cache_key is not None and evaluation_error is None:
            cached_result = {
                "objectives": objectives,
                "evaluation_policy_version": solution.attributes.get("evaluation_policy_version"),
                "model_semantic_sha256": solution.attributes.get("model_semantic_sha256"),
                "evaluation_environment": solution.attributes.get("evaluation_environment"),
                "discovery_metadata": solution.attributes.get("discovery_metadata"),
                "constraints": list(solution.constraints),
                "pipeline": deepcopy(decoded_pipeline),
                "metrics": dict(metric_values),
                "metrics_status": metrics_status,
                "objective_metrics": dict(objective_metrics),
                "runtime_ms": runtime_ms,
                "evaluation_id": evaluation_id,
                "experiment_id": experiment_id,
                "fingerprint": fingerprint,
                "model_schema_version": solution.attributes.get("model_schema_version"),
                "evaluation_error": evaluation_error,
                "is_feasible": solution.attributes.get("is_feasible"),
                "constraint_violations": list(solution.attributes.get("constraint_violations", [])),
                "visible_transition_count": solution.attributes.get("visible_transition_count"),
            }
            with self._cache_lock:
                self.evaluation_cache[cache_key] = cached_result
        self._notify_evaluation(
            logical_attempt_id=solution.attributes.get("logical_attempt_id"),
            cache_hit=False,
            has_error=bool(evaluation_error),
            evaluation_error=evaluation_error,
            pipeline=decoded_pipeline,
            metrics=metric_values,
            runtime_ms=runtime_ms,
            cached_runtime_ms=None,
            evaluation_id=evaluation_id,
            experiment_id=experiment_id,
            fingerprint=fingerprint,
            evaluation_policy_version=solution.attributes.get("evaluation_policy_version"),
            model_semantic_sha256=solution.attributes.get("model_semantic_sha256"),
            evaluation_environment=solution.attributes.get("evaluation_environment"),
            discovery_metadata=solution.attributes.get("discovery_metadata"),
        )
        return solution

    def raise_if_cancel_requested(self) -> None:
        if self.execution_control is not None:
            self.execution_control.raise_if_cancel_requested()
        if hasattr(self.evaluator, "raise_if_cancel_requested"):
            self.evaluator.raise_if_cancel_requested()

    @classmethod
    def _clear_evaluation_state(cls, solution: FloatSolution) -> None:
        attributes = getattr(solution, "attributes", None)
        if attributes is None:
            return
        for key in cls._EVALUATION_ATTRIBUTE_KEYS:
            attributes.pop(key, None)

    def _notify_evaluation(
        self,
        cache_hit: bool,
        has_error: bool,
        evaluation_error: str | None = None,
        pipeline: Dict[str, Any] | None = None,
        metrics: Dict[str, Any] | None = None,
        runtime_ms: int | None = None,
        cached_runtime_ms: int | None = None,
        evaluation_id: str | None = None,
        experiment_id: str | None = None,
        fingerprint: str | None = None,
        logical_attempt_id: int | None = None,
        evaluation_policy_version: str | None = None,
        model_semantic_sha256: str | None = None,
        evaluation_environment: Dict[str, Any] | None = None,
        discovery_metadata: Dict[str, Any] | None = None,
    ) -> None:
        if self.on_evaluation is None:
            return
        with self._eval_lock:
            self._evaluations_done += 1
            done = self._evaluations_done
        with self._cache_lock:
            solution_cache_size = len(self.evaluation_cache)
        try:
            self.on_evaluation(
                {
                    "evaluations_done": done,
                    "logical_attempt_id": logical_attempt_id,
                    "evaluation_policy_version": evaluation_policy_version,
                    "model_semantic_sha256": model_semantic_sha256,
                    "evaluation_environment": evaluation_environment,
                    "discovery_metadata": discovery_metadata,
                    "cache_hit": cache_hit,
                    "has_error": has_error,
                    "evaluation_error": evaluation_error,
                    "pipeline": pipeline or {},
                    "metrics": metrics or {},
                    "runtime_ms": runtime_ms,
                    "cached_runtime_ms": cached_runtime_ms,
                    "evaluation_id": evaluation_id,
                    "experiment_id": experiment_id,
                    "fingerprint": fingerprint,
                    "solution_cache_size": solution_cache_size,
                }
            )
        except Exception:
            # Progress callback must never break optimization.
            pass

    def number_of_objectives(self) -> int:
        return len(self.metrics_list)

    def number_of_constraints(self) -> int:
        return 1

    def name(self) -> str:
        return "Pipeline Optimization Problem"
