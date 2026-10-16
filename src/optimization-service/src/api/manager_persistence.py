from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from java_service_client import ProMServiceClient
from model_quality import validate_v3_feasibility
from pareto import has_evaluation_error

from .common import LOGGER, _parse_utc_iso, _to_int_or_none
from .petri import _petri_from_pnml, _petri_from_v2_artifact
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


def persist_completed_experiment(
    manager: Any,
    job_id: str,
    *,
    artifact_client: Any = None,
    cleanup_artifacts: bool = True,
) -> None:
    """Persist through the same path for live jobs and offline recovery.

    An offline caller may supply an artifact reader and retain its source files.
    Live application jobs use the ProM client and cleanup policy by default.
    """
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
        client = artifact_client if artifact_client is not None else ProMServiceClient(
            base_url=str(request_data.get("service_url") or manager.default_service_url),
            experiment_id=str(request_data.get("execution_name") or ""),
            timeout_seconds=manager.java_service_timeout_seconds,
        )
        for offset in range(0, len(evaluation_ids), 16):
            control.raise_if_cancel_requested()
            artifacts = client.fetch_artifacts(
                evaluation_ids=evaluation_ids[offset:offset + 16], include_pnml=True,
                experiment_id=str(request_data.get("execution_name") or ""),
            )
            for artifact in artifacts:
                evaluation_id = artifact.get("evaluation_id")
                if not evaluation_id:
                    continue
                schema = artifact.get("model_schema_version")
                if schema in (2, 3):
                    graph = _petri_from_v2_artifact(artifact)
                elif schema is None:
                    places, transitions, arcs, initial, finals = _petri_from_pnml(str(artifact.get("pnml") or ""))
                    initial = artifact["initial_marking"] if isinstance(artifact.get("initial_marking"), list) else initial
                    finals = artifact["final_markings"] if isinstance(artifact.get("final_markings"), list) else finals
                    graph = (places, transitions, arcs, initial, finals[0] if finals else [], finals)
                else:
                    raise ValueError(f"unsupported model_schema_version: {schema}")
                # Keep each original once per evaluation; solutions reference the same object.
                artifacts_by_evaluation_id[str(evaluation_id)] = {
                    key: artifact.get(key) for key in (
                        "model_schema_version", "visible_transition_count", "is_feasible", "constraint_violations"
                    )
                }
                artifacts_by_evaluation_id[str(evaluation_id)]["_graph"] = graph
                artifacts_by_evaluation_id[str(evaluation_id)]["original_pnml"] = artifact.get("pnml")
                artifacts_by_evaluation_id[str(evaluation_id)]["original_metadata"] = {
                    key: value for key, value in artifact.items() if key != "pnml"
                }
            if artifacts:
                del artifact
            del artifacts
    control.raise_if_cancel_requested()

    parsed_solutions: List[Dict[str, Any]] = []
    parsed_snapshot_solutions: List[Dict[str, Any]] = []

    def parse_solution_payload(solution: Dict[str, Any]) -> Dict[str, Any]:
        places: List[Dict[str, Any]] = []
        transitions: List[Dict[str, Any]] = []
        arcs: List[Dict[str, Any]] = []
        initial_marking: List[Dict[str, Any]] = []
        final_marking: List[Dict[str, Any]] = []
        final_markings: List[List[Dict[str, Any]]] = []
        model_schema_version = solution.get("model_schema_version")
        visible_transition_count = solution.get("visible_transition_count")
        is_feasible = solution.get("is_feasible")
        constraint_violations = solution.get("constraint_violations", [])

        evaluation_id = solution.get("evaluation_id")
        if evaluation_id:
            artifact = artifacts_by_evaluation_id.get(str(evaluation_id))
            if artifact:
                artifact_schema_version = artifact.get("model_schema_version")
                if (
                    model_schema_version is not None
                    and artifact_schema_version != model_schema_version
                ):
                    raise ValueError("solution and artifact model_schema_version do not match")
                model_schema_version = artifact_schema_version
                if model_schema_version in (2, 3):
                    (
                        places,
                        transitions,
                        arcs,
                        initial_marking,
                        final_marking,
                        final_markings,
                    ) = artifact["_graph"]
                    visible_transition_count = artifact.get("visible_transition_count")
                    is_feasible = artifact.get("is_feasible")
                    constraint_violations = artifact.get("constraint_violations")
                    if model_schema_version == 3:
                        validate_v3_feasibility(visible_transition_count, is_feasible, constraint_violations)
                    else:
                        if not isinstance(visible_transition_count, int) or isinstance(visible_transition_count, bool):
                            raise ValueError("v2 artifact is missing visible_transition_count")
                        if not isinstance(is_feasible, bool) or not isinstance(constraint_violations, list):
                            raise ValueError("v2 artifact is missing feasibility metadata")
                        expected_violations = [] if is_feasible else ["NO_VISIBLE_TRANSITIONS"]
                        if (
                            is_feasible != (visible_transition_count > 0)
                            or constraint_violations != expected_violations
                        ):
                            raise ValueError("v2 artifact has inconsistent feasibility metadata")
                elif model_schema_version is None:
                    places, transitions, arcs, initial_marking, final_marking, final_markings = artifact["_graph"]
                else:
                    raise ValueError(f"unsupported model_schema_version: {model_schema_version}")
            elif model_schema_version in (2, 3):
                raise ValueError("versioned solution is missing its semantic artifact")

        return {
            "variables": solution.get("variables", []),
            "objectives": solution.get("objectives", []),
            "metrics": solution.get("metrics", {}),
            "metrics_status": solution.get("metrics_status", "computed"),
            "pipeline": _compact_pipeline_for_storage(solution.get("pipeline")),
            "pipeline_full": solution.get("pipeline") if isinstance(solution.get("pipeline"), dict) else None,
            "evaluation_id": evaluation_id,
            "fingerprint": solution.get("fingerprint"),
            "evaluation_error": solution.get("evaluation_error"),
            "evaluation_status": (
                "error" if has_evaluation_error(solution) else
                "feasible" if is_feasible is True else
                "infeasible" if is_feasible is False else "unknown"
            ),
            "runtime_ms": _to_int_or_none(solution.get("runtime_ms")),
            "is_pareto": (
                bool(solution.get("is_pareto"))
                and is_feasible is not False
                and not has_evaluation_error(solution)
            ),
            "places": places,
            "transitions": transitions,
            "arcs": arcs,
            "model_schema_version": model_schema_version,
            **{key: solution.get(key) for key in ("logical_attempt_id", "evaluation_policy_version", "model_semantic_sha256", "constraints", "discovery_metadata")},
            "visible_transition_count": visible_transition_count,
            "is_feasible": is_feasible,
            "constraint_violations": constraint_violations,
            "initial_marking": initial_marking,
            "final_marking": final_marking,
            "final_markings": final_markings,
            "original_pnml": artifacts_by_evaluation_id.get(str(evaluation_id), {}).get("original_pnml"),
            "original_metadata": artifacts_by_evaluation_id.get(str(evaluation_id), {}).get("original_metadata"),
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
        "pop_size": _to_int_or_none((result.get("optimizer_config") or {}).get("population_size") or discover.get("population_size")),
        "seed": _to_int_or_none((result.get("optimizer_config") or {}).get("seed", discover.get("seed"))),
        "miners": (result.get("catalogs") or {}).get("miners", []),
        "preprocessing": (result.get("catalogs") or {}).get("preprocessing", []),
        "log_path": request_data.get("log_path") or "",
        "metrics": result.get("metrics_order") or request_data.get("metrics") or [],
        "workers": int((result.get("optimizer_config") or {}).get("n_workers") or discover.get("n_workers") or 1),
        "actual_evaluations": _to_int_or_none(result.get("actual_evaluations")),
        "conformance_mode": request_data.get("conformance_mode") or "replay-token",
        "log_sha256": result.get("log_sha256"),
        "optimizer_source_sha256": result.get("optimizer_source_sha256"),
        "prom_revision": result.get("prom_revision"),
        "quality_policy_version": result.get("quality_policy_version"),
        "optimizer_config": result.get("optimizer_config"),
    }

    parsed_population_snapshots = [
        {key: snapshot.get(key) for key in (
            "snapshot_index", "evaluations_done", "attempts_since_previous",
            "cache_hits_since_previous", "errors_since_previous", "unique_pipelines_since_previous",
        )}
        for snapshot in population_snapshots
    ]

    control.raise_if_cancel_requested()
    manager.job_store.save_completed_experiment(
        experiment_data, parsed_solutions, parsed_snapshot_solutions, parsed_population_snapshots
    )
    if cleanup_artifacts:
        _cleanup_persisted_experiment_artifacts(manager, request_data, job_id)
