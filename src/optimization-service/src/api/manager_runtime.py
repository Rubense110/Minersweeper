from __future__ import annotations

import traceback
from typing import Any, Dict

from execution_control import JobCancelled
from java_service_client import ProMServiceClient

from .common import LOGGER, _utc_now_iso
from .evaluation_trace import append_evaluation_trace
from .manager_state import publish_event, public_progress, update_progress
from .serialization import _count_failed_solutions, _non_dominated_evaluation_ids, _pipeline_for_log, _serialize_solution


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
        "job running job_id=%s execution=%s metrics=%s constraints=%s conformance_mode=%s service_url=%s",
        job_id,
        request_data.get("execution_name"),
        request_data.get("metrics"),
        manager._summarize_constraints(request_data.get("constraints") or []) or "-",
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
    }

    def on_evaluation(event: Dict[str, Any]) -> None:
        evaluations_done = int(event.get("evaluations_done") or 0)
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
        constraints=config.get("constraints"),
        service_url=config["service_url"],
        service_timeout_seconds=manager.java_service_timeout_seconds,
        conformance_mode=config.get("conformance_mode"),
        excluded_miners=tuple(config.get("excluded_miners") or ()),
        execution_control=control,
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

    pareto_ids = set(miner.get_non_dominated_evaluation_ids())
    all_solutions_raw = miner.result or []
    pareto_solutions_raw = miner.non_dominated or []
    population_snapshots_raw = miner.population_snapshots or []

    all_solutions = [_serialize_solution(sol, pareto_ids) for sol in all_solutions_raw]
    pareto_solutions = [_serialize_solution(sol, pareto_ids) for sol in pareto_solutions_raw]
    population_snapshots = []
    for snapshot in population_snapshots_raw:
        snapshot_solutions_raw = list(snapshot.get("solutions") or [])
        snapshot_pareto_ids = _non_dominated_evaluation_ids(snapshot_solutions_raw)
        population_snapshots.append(
            {
                "snapshot_index": int(snapshot.get("snapshot_index") or 0),
                "evaluations_done": int(snapshot.get("evaluations_done") or 0),
                "solutions": [
                    _serialize_solution(solution, snapshot_pareto_ids) for solution in snapshot_solutions_raw
                ],
            }
        )

    control.raise_if_cancel_requested()
    return {
        "execution_name": config["execution_name"],
        "metrics_order": list(miner.metrics_list),
        "constraints": list(miner.constraints),
        "counts": {
            "all_solutions": len(all_solutions),
            "pareto_solutions": len(pareto_solutions),
            "snapshot_solutions": sum(len(snapshot.get("solutions") or []) for snapshot in population_snapshots),
            "snapshots": len(population_snapshots),
            "failed_solutions": _count_failed_solutions(all_solutions, progress_state["error_count"]),
            "feasible_solutions": sum(1 for item in all_solutions if item.get("is_feasible", True)),
        },
        "pareto_evaluation_ids": list(pareto_ids),
        "all_solutions": all_solutions,
        "pareto_solutions": pareto_solutions,
        "population_snapshots": population_snapshots,
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
