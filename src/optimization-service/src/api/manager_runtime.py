from __future__ import annotations

import json
import hashlib
import platform
import threading
import traceback
from importlib.metadata import version
from typing import Any, Dict

from execution_control import JobCancelled, EvaluationTerminationUnconfirmed, ReproducibilityError
from java_service_client import ProMServiceClient
from parameters.miners import MINER_CATALOG
from pareto import feasible_non_dominated

from .common import LOGGER, _utc_now_iso
from .evaluation_trace import append_evaluation_trace
from .manager_state import publish_event, public_progress, update_progress
from .provenance import configured_revision, file_sha256, optimizer_source_sha256
from .serialization import _count_failed_solutions, _non_dominated_evaluation_ids, _pipeline_for_log, _serialize_solution


def _interval_evaluation_stats(events: list[Dict[str, Any]], start: int, end: int) -> Dict[str, int]:
    interval = [event for event in events if start < event["evaluations_done"] <= end]
    return {
        "attempts_since_previous": len(interval),
        "cache_hits_since_previous": sum(event["cache_hit"] for event in interval),
        "errors_since_previous": sum(event["has_error"] for event in interval),
        "unique_pipelines_since_previous": len({event["pipeline_key"] for event in interval}),
    }


def run_job(manager: Any, job_id: str) -> None:
    with manager._lock:
        job = manager._jobs.get(job_id)
        if not job:
            return
        control = job["_control"]
        if control.is_cancel_requested():
            if job.get("status") != "cancelled":
                job["status"] = "cancelled"
                job["finished_at"] = _utc_now_iso()
            cancelled_payload = public_progress(job)
        else:
            cancelled_payload = None
        if cancelled_payload is None:
            job["status"] = "running"
            job["started_at"] = _utc_now_iso()
            request_data = dict(job["request"])
    if cancelled_payload is not None:
        publish_event(manager, job_id, "status_changed", {"job_id": job_id, "status": "cancelled"})
        publish_event(manager, job_id, "progress", cancelled_payload)
        return

    LOGGER.info(
        "job running job_id=%s execution=%s metrics=%s conformance_mode=%s service_url=%s",
        job_id,
        request_data.get("execution_name"),
        request_data.get("metrics"),
        request_data.get("conformance_mode"),
        request_data.get("service_url"),
    )
    publish_event(manager, job_id, "status_changed", {"job_id": job_id, "status": "running"})

    try:
        result = execute_job(manager, job_id, job["request"])
        control.raise_if_cancel_requested()
        with manager._lock:
            job = manager._jobs.get(job_id)
            if not job:
                return
            job["_runtime_miner"] = None
            job["finished_at"] = _utc_now_iso()
            job["result"] = result
            progress = job.get("progress", {})
            max_evaluations = int(progress.get("max_evaluations") or 0)
            current = int(progress.get("evaluations_done") or 0)
            if max_evaluations > current:
                progress["evaluations_done"] = max_evaluations

        manager._persist_completed_experiment(job_id)
        control.raise_if_cancel_requested()

        with manager._lock:
            job = manager._jobs.get(job_id)
            if not job:
                return
            if control.is_cancel_requested():
                raise JobCancelled("job cancelled")
            job["status"] = "completed"
            job["_result_persisted"] = True
            job["result"] = {key: result.get(key) for key in ("execution_name", "counts", "pareto_evaluation_ids")}
            # The persisted experiment remains available; discard all population
            # copies and runtime objects held solely for the completed job.
            job["_runtime_miner"] = None

        all_solutions = result.get("all_solutions", [])
        failed_solutions = _count_failed_solutions(
            all_solutions,
            result.get("counts", {}).get("failed_solutions", 0),
        )
        total_solutions = len(all_solutions)
        LOGGER.info(
            "job completed job_id=%s execution=%s total_solutions=%s pareto_solutions=%s failed_solutions=%s",
            job_id,
            result.get("execution_name"),
            total_solutions,
            result.get("counts", {}).get("pareto_solutions", 0),
            failed_solutions,
        )
        publish_event(manager, job_id, "status_changed", {"job_id": job_id, "status": "completed"})
        publish_event(manager, job_id, "progress", manager.get_progress(job_id))
        publish_event(
            manager,
            job_id,
            "result_ready",
            {
                "job_id": job_id,
                "result_summary": {
                    "execution_name": result.get("execution_name"),
                    "counts": result.get("counts", {}),
                    "pareto_evaluation_ids": result.get("pareto_evaluation_ids", []),
                },
            },
        )
    except JobCancelled:
        manager._finalize_cancelled_job(job_id)
    except Exception as exc:
        if isinstance(exc, (EvaluationTerminationUnconfirmed, ReproducibilityError)):
            request_java_experiment_cancel(manager, job_id, request_data)
        with manager._lock:
            job = manager._jobs.get(job_id)
            if not job:
                return
            job["_runtime_miner"] = None
            job["status"] = "failed"
            job["finished_at"] = _utc_now_iso()
            job["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        publish_event(manager, job_id, "status_changed", {"job_id": job_id, "status": "failed"})
        publish_event(
            manager,
            job_id,
            "error",
            {"job_id": job_id, "message": str(exc), "error_type": type(exc).__name__},
        )
        LOGGER.exception("job failed job_id=%s", job_id)


def execute_job(manager: Any, job_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    from process_miner import OptimizedProcessMiner

    with manager._lock:
        job = manager._jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        control = job["_control"]

    control.raise_if_cancel_requested()
    discover = config["discover"]
    max_evaluations = int(discover["max_evaluations"])
    progress_log_step = max(1, max_evaluations // 10)
    progress_state = {
        "last_progress_logged": 0,
        "error_count": 0,
        "error_occurrences": {},
        "unique_errors_logged": 0,
        "evaluation_events": [],
    }
    event_lock = threading.Lock()
    log_sha256 = file_sha256(config["log_path"])
    source_sha256 = optimizer_source_sha256()

    def on_evaluation(event: Dict[str, Any]) -> None:
        evaluations_done = int(event.get("evaluations_done") or 0)
        pipeline_key = json.dumps(
            event.get("pipeline") or {}, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        with event_lock:
            progress_state["evaluation_events"].append({
                "evaluations_done": evaluations_done,
                "cache_hit": bool(event.get("cache_hit")),
                "has_error": bool(event.get("has_error")),
                "pipeline_key": pipeline_key,
                "evaluation_policy_version": event.get("evaluation_policy_version"),
                "model_semantic_sha256": event.get("model_semantic_sha256"),
                "evaluation_environment": event.get("evaluation_environment"),
                "discovery_metadata": event.get("discovery_metadata"),
            })
        update_progress(manager, job_id, evaluations_done)
        try:
            append_evaluation_trace(job_id=job_id, config=config, event=event)
        except Exception:
            LOGGER.warning("evaluation trace write failed job_id=%s", job_id, exc_info=True)

        should_log_progress = (
            evaluations_done == 1
            or evaluations_done >= max_evaluations
            or evaluations_done - int(progress_state["last_progress_logged"]) >= progress_log_step
        )
        if should_log_progress:
            progress_state["last_progress_logged"] = evaluations_done
            LOGGER.info(
                "job progress job_id=%s evaluations=%s/%s cache_hit=%s errors=%s",
                job_id,
                evaluations_done,
                max_evaluations,
                bool(event.get("cache_hit")),
                progress_state["error_count"],
            )

        if not event.get("has_error"):
            return

        progress_state["error_count"] = int(progress_state["error_count"]) + 1
        error_message = str(event.get("evaluation_error") or "evaluation_failed")
        error_occurrences = progress_state["error_occurrences"]
        error_count_for_message = int(error_occurrences.get(error_message, 0)) + 1
        error_occurrences[error_message] = error_count_for_message

        if error_count_for_message == 1 and int(progress_state["unique_errors_logged"]) < 5:
            progress_state["unique_errors_logged"] = int(progress_state["unique_errors_logged"]) + 1
            pipeline_text = _pipeline_for_log(event.get("pipeline"))
            LOGGER.warning(
                "job evaluation failed job_id=%s evaluation=%s/%s error=%s pipeline=%s",
                job_id,
                evaluations_done,
                max_evaluations,
                error_message,
                pipeline_text,
            )

    miner = OptimizedProcessMiner(
        execution_name=config["execution_name"],
        log=config["log_path"],
        metrics=config.get("metrics"),
        service_url=config["service_url"],
        service_timeout_seconds=manager.java_service_timeout_seconds,
        conformance_mode=config.get("conformance_mode"),
        excluded_miners=tuple(config.get("excluded_miners") or ()),
        execution_control=control,
        seed=discover.get("seed"),
        constraints=config.get("constraints"),
        observation_metrics=config.get("observation_metrics"),
    )
    with manager._lock:
        job = manager._jobs.get(job_id)
        if job is not None:
            job["_runtime_miner"] = miner

    miner.discover(
        max_evaluations=discover["max_evaluations"],
        population_size=discover["population_size"],
        n_partitions=discover["n_partitions"],
        n_workers=discover["n_workers"],
        progress_callback=on_evaluation,
    )
    miner.raise_if_cancel_requested()

    all_solutions_raw = miner.result or []
    pareto_solutions_raw = feasible_non_dominated(all_solutions_raw)
    pareto_ids = _non_dominated_evaluation_ids(pareto_solutions_raw)
    population_snapshots_raw = miner.population_snapshots or []

    all_solutions = [_serialize_solution(sol, pareto_ids) for sol in all_solutions_raw]
    pareto_solutions = [_serialize_solution(sol, pareto_ids) for sol in pareto_solutions_raw]
    population_snapshots = []
    with event_lock:
        evaluation_events = sorted(
            progress_state["evaluation_events"], key=lambda event: event["evaluations_done"]
        )
    previous_evaluations = 0
    for snapshot in population_snapshots_raw:
        snapshot_solutions_raw = list(snapshot.get("solutions") or [])
        snapshot_pareto_ids = _non_dominated_evaluation_ids(snapshot_solutions_raw)
        evaluations_done = int(snapshot.get("evaluations_done") or 0)
        population_snapshots.append(
            {
                "snapshot_index": int(snapshot.get("snapshot_index") or 0),
                "evaluations_done": evaluations_done,
                **_interval_evaluation_stats(evaluation_events, previous_evaluations, evaluations_done),
                "solutions": [
                    _serialize_solution(solution, snapshot_pareto_ids) for solution in snapshot_solutions_raw
                ],
            }
        )
        previous_evaluations = evaluations_done

    effective_config = dict(miner.optimizer.effective_config)
    effective_config.update({
        "max_evaluations": max_evaluations,
        "requested_population_size": discover.get("requested_population_size", discover["population_size"]),
        "requested_n_workers": int(discover["n_workers"]),
        "variable_count": miner.problem.number_of_variables(),
        "python_version": platform.python_version(),
        "jmetalpy_version": version("jmetalpy"),
        "objective_directions": {metric: "maximize" for metric in miner.metrics_list},
        "observation_metrics": list(miner.observation_metrics),
        "required_metrics": list(miner.required_metrics),
        "model_schema_versions": sorted({
            int(solution.get("model_schema_version")) for solution in all_solutions
            if isinstance(solution.get("model_schema_version"), int)
        }),
        "excluded_miners": list(config.get("excluded_miners") or []),
        "enabled_variants": {
            key: [variant.key for variant in MINER_CATALOG[key].variants]
            for key in miner.search_space.miner_keys
        },
    })

    # Hash scientific outcomes in logical population order, not UUID/timing order.
    stable_keys = ("variables", "pipeline", "objectives", "constraints", "is_feasible",
                   "constraint_violations", "model_semantic_sha256", "discovery_metadata")
    final_state = [{key: solution.get(key) for key in stable_keys} for solution in all_solutions]
    effective_config["result_sha256"] = hashlib.sha256(
        json.dumps(final_state, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    policies = sorted({e["evaluation_policy_version"] for e in evaluation_events if e.get("evaluation_policy_version")})
    effective_config["evaluation_policy_versions"] = policies
    environments = {json.dumps(event["evaluation_environment"], sort_keys=True, separators=(",", ":"))
                    for event in evaluation_events if event.get("evaluation_environment")}
    effective_config["evaluation_environments"] = [json.loads(value) for value in sorted(environments)]
    effective_config["reproducibility_scope"] = "seeded_search_and_own_evaluation"
    # A technical failure or older Java response must not be advertised as certified.
    effective_config["reproducibility_status"] = (
        "controlled" if effective_config.get("python_rng_from_seed")
        and (config.get("conformance_mode") or "replay-token") == "replay-token"
        and len(environments) == 1
        and policies == ["minersweeper-evaluation-v2"]
        and all(s.get("evaluation_policy_version") and s.get("model_semantic_sha256") for s in all_solutions)
        and all(e.get("evaluation_policy_version") == "minersweeper-evaluation-v2"
                and e.get("model_semantic_sha256") and e.get("evaluation_environment") for e in evaluation_events)
        and not any(event["has_error"] for event in evaluation_events) else "not_certified"
    )
    control.raise_if_cancel_requested()
    return {
        "execution_name": config["execution_name"],
        "metrics_order": list(miner.metrics_list),
        "counts": {
            "all_solutions": len(all_solutions),
            "pareto_solutions": len(pareto_solutions),
            "snapshot_solutions": sum(len(snapshot.get("solutions") or []) for snapshot in population_snapshots),
            "snapshots": len(population_snapshots),
            "failed_solutions": _count_failed_solutions(all_solutions, progress_state["error_count"]),
        },
        "pareto_evaluation_ids": list(pareto_ids),
        "all_solutions": all_solutions,
        "pareto_solutions": pareto_solutions,
        "population_snapshots": population_snapshots,
        "actual_evaluations": int(miner.optimizer.algorithm.evaluations or 0),
        "optimizer_config": effective_config,
        "log_sha256": log_sha256,
        "optimizer_source_sha256": source_sha256,
        "prom_revision": configured_revision("PROM_SERVICE_REVISION"),
        "quality_policy_version": configured_revision("MODEL_QUALITY_POLICY_VERSION"),
        "non_dominated_pipelines": miner.get_non_dominated_pipelines(),
        "non_dominated_metrics": miner.get_non_dominated_metrics(),
        "catalogs": {
            "miners": list(miner.search_space.miner_keys if miner.search_space else []),
            "preprocessing": list(miner.search_space.preprocessing_keys if miner.search_space else []),
        },
    }


def request_java_experiment_cancel(manager: Any, job_id: str, request_data: Dict[str, Any]) -> None:
    execution_name = str(request_data.get("execution_name") or "").strip()
    service_url = str(request_data.get("service_url") or manager.default_service_url).strip()
    if not execution_name or not service_url:
        return

    client = ProMServiceClient(
        base_url=service_url,
        experiment_id=execution_name,
        timeout_seconds=manager.java_service_timeout_seconds,
    )
    try:
        client.cancel_experiment(experiment_id=execution_name)
    except Exception:
        LOGGER.warning(
            "job cancel remote interrupt failed job_id=%s execution=%s",
            job_id,
            execution_name,
            exc_info=True,
        )


def cleanup_cancelled_experiment(manager: Any, request_data: Dict[str, Any]) -> None:
    execution_name = str(request_data.get("execution_name") or "").strip()
    service_url = str(request_data.get("service_url") or manager.default_service_url).strip()
    if not execution_name or not service_url:
        return

    client = ProMServiceClient(
        base_url=service_url,
        experiment_id=execution_name,
        timeout_seconds=manager.java_service_timeout_seconds,
    )
    try:
        client.cleanup_experiment(experiment_id=execution_name)
    except Exception:
        LOGGER.warning("job cancel cleanup failed execution=%s", execution_name, exc_info=True)


def finalize_cancelled_job(manager: Any, job_id: str) -> None:
    with manager._lock:
        job = manager._jobs.get(job_id)
        if not job:
            return
        request_data = dict(job.get("request") or {})
        job["_runtime_miner"] = None
        job["status"] = "cancelled"
        job["finished_at"] = _utc_now_iso()
        job["result"] = None
        job["error"] = None
        progress_payload = public_progress(job)

    try:
        manager.job_store.delete_experiment(job_id)
    except Exception:
        LOGGER.warning("job cancel database cleanup failed job_id=%s", job_id, exc_info=True)
    cleanup_cancelled_experiment(manager, request_data)
    publish_event(manager, job_id, "status_changed", {"job_id": job_id, "status": "cancelled"})
    publish_event(manager, job_id, "progress", progress_payload)
    LOGGER.info("job cancelled job_id=%s execution=%s", job_id, request_data.get("execution_name"))
