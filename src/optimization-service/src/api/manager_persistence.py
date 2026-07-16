from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from java_service_client import ProMServiceClient

from .common import LOGGER, _parse_utc_iso, _to_int_or_none
from .petri import _petri_from_pnml
from .serialization import _compact_pipeline_for_storage


def _cleanup_persisted_experiment_artifacts(manager: Any, request_data: Dict[str, Any], job_id: str) -> None:
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
        LOGGER.warning(
            "job artifact cleanup failed job_id=%s execution=%s",
            job_id,
            execution_name,
            exc_info=True,
        )


def persist_completed_experiment(manager: Any, job_id: str) -> None:
    with manager._lock:
        job = manager._jobs.get(job_id)
        if not job:
            return
        control = job["_control"]
        request_data = dict(job.get("request") or {})
        result = dict(job.get("result") or {})
        started_at = job.get("started_at")
        finished_at = job.get("finished_at")

    control.raise_if_cancel_requested()

    discover = request_data.get("discover") or {}
    all_solutions = list(result.get("all_solutions") or [])
    population_snapshots = list(result.get("population_snapshots") or [])

    evaluation_ids: List[str] = []
    seen = set()
    for solution in all_solutions:
        evaluation_id = solution.get("evaluation_id")
        if not evaluation_id or evaluation_id in seen:
            continue
        seen.add(evaluation_id)
        evaluation_ids.append(evaluation_id)
    for snapshot in population_snapshots:
        for solution in snapshot.get("solutions") or []:
            evaluation_id = solution.get("evaluation_id")
            if not evaluation_id or evaluation_id in seen:
                continue
            seen.add(evaluation_id)
            evaluation_ids.append(evaluation_id)

    artifacts_by_evaluation_id: Dict[str, Dict[str, Any]] = {}
    if evaluation_ids:
        client = ProMServiceClient(
            base_url=str(request_data.get("service_url") or manager.default_service_url),
            experiment_id=str(request_data.get("execution_name") or ""),
            timeout_seconds=manager.java_service_timeout_seconds,
        )
        artifacts = client.fetch_artifacts(
            evaluation_ids=evaluation_ids,
            include_pnml=True,
            experiment_id=str(request_data.get("execution_name") or ""),
        )
        for artifact in artifacts:
            evaluation_id = artifact.get("evaluation_id")
            if not evaluation_id:
                continue
            artifacts_by_evaluation_id[str(evaluation_id)] = artifact
    control.raise_if_cancel_requested()

    parsed_solutions: List[Dict[str, Any]] = []
    parsed_snapshot_solutions: List[Dict[str, Any]] = []

    def parse_solution_payload(solution: Dict[str, Any]) -> Dict[str, Any]:
        places: List[Dict[str, Any]] = []
        transitions: List[Dict[str, Any]] = []
        arcs: List[Dict[str, Any]] = []

        evaluation_id = solution.get("evaluation_id")
        if evaluation_id:
            artifact = artifacts_by_evaluation_id.get(str(evaluation_id))
            if artifact:
                pnml_text = str(artifact.get("pnml") or "")
                places, transitions, arcs = _petri_from_pnml(pnml_text)

        return {
            "variables": solution.get("variables", []),
            "objectives": solution.get("objectives", []),
            "metrics": solution.get("metrics", {}),
            "pipeline": _compact_pipeline_for_storage(solution.get("pipeline")),
            "runtime_ms": _to_int_or_none(solution.get("runtime_ms")),
            "is_pareto": bool(solution.get("is_pareto")),
            "places": places,
            "transitions": transitions,
            "arcs": arcs,
        }

    for solution in all_solutions:
        parsed_solutions.append(parse_solution_payload(solution))

    for snapshot in population_snapshots:
        snapshot_index = int(snapshot.get("snapshot_index") or 0)
        evaluations_done = int(snapshot.get("evaluations_done") or 0)
        for member_index, solution in enumerate(list(snapshot.get("solutions") or []), start=1):
            parsed_snapshot = parse_solution_payload(solution)
            parsed_snapshot["snapshot_index"] = snapshot_index
            parsed_snapshot["evaluations_done"] = evaluations_done
            parsed_snapshot["member_index"] = member_index
            parsed_snapshot_solutions.append(parsed_snapshot)

    experiment_data = {
        "experiment_id": job_id,
        "experiment_name": request_data.get("execution_name") or job_id,
        "start_at": _parse_utc_iso(started_at) or datetime.now(timezone.utc),
        "end_at": _parse_utc_iso(finished_at) or datetime.now(timezone.utc),
        "max_evals": int(discover.get("max_evaluations") or 0),
        "pop_size": _to_int_or_none(discover.get("population_size")),
        "miners": (result.get("catalogs") or {}).get("miners", []),
        "preprocessing": (result.get("catalogs") or {}).get("preprocessing", []),
        "log_path": request_data.get("log_path") or "",
        "metrics": result.get("metrics_order") or request_data.get("metrics") or [],
        "workers": int(discover.get("n_workers") or 1),
    }

    control.raise_if_cancel_requested()
    manager.job_store.save_completed_experiment(experiment_data, parsed_solutions, parsed_snapshot_solutions)
    _cleanup_persisted_experiment_artifacts(manager, request_data, job_id)
