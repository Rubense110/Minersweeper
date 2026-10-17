from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from typing import Any, Dict, List

from pareto import feasible_non_dominated_evaluation_ids, is_feasible_solution


def _compact_pipeline_for_storage(pipeline: Any) -> Dict[str, Any]:
    if not isinstance(pipeline, dict):
        return {
            "preprocessing": {"variant": "", "parameters": {}},
            "miner": {"variant": "", "parameters": {}},
        }

    preprocessing = pipeline.get("preprocessing") if isinstance(pipeline.get("preprocessing"), dict) else {}
    miner = pipeline.get("miner") if isinstance(pipeline.get("miner"), dict) else {}

    return {
        "preprocessing": {
            "variant": preprocessing.get("variant") or "",
            "parameters": preprocessing.get("parameters") if isinstance(preprocessing.get("parameters"), dict) else {},
        },
        "miner": {
            "variant": miner.get("variant") or "",
            "parameters": miner.get("parameters") if isinstance(miner.get("parameters"), dict) else {},
        },
    }


def _pipeline_for_log(pipeline: Any, max_length: int = 1500) -> str:
    if not pipeline:
        return ""
    try:
        text = json.dumps(pipeline, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    except Exception:
        text = str(pipeline)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _serialize_solution(solution: Any, pareto_ids: set[str]) -> Dict[str, Any]:
    attrs = getattr(solution, "attributes", {}) or {}
    evaluation_id = attrs.get("evaluation_id")
    payload = {
        "evaluation_id": evaluation_id,
        "logical_attempt_id": attrs.get("logical_attempt_id"),
        "experiment_id": attrs.get("experiment_id"),
        "fingerprint": attrs.get("fingerprint"),
        "pipeline": attrs.get("pipeline", {}),
        "metrics": attrs.get("metrics", {}),
        "metrics_status": attrs.get("metrics_status", "computed"),
        "objective_metrics": attrs.get("objective_metrics", {}),
        "runtime_ms": _to_int_or_none(attrs.get("runtime_ms")),
        "objectives": list(getattr(solution, "objectives", []) or []),
        "constraints": list(getattr(solution, "constraints", []) or []),
        "optimization_feasible": is_feasible_solution(solution),
        "evaluation_policy_version": attrs.get("evaluation_policy_version"),
        "model_semantic_sha256": attrs.get("model_semantic_sha256"),
        "discovery_metadata": attrs.get("discovery_metadata"),
        "variables": list(getattr(solution, "variables", []) or []),
        "is_pareto": bool(is_feasible_solution(solution) and evaluation_id and evaluation_id in pareto_ids),
        "model_schema_version": attrs.get("model_schema_version"),
        "is_feasible": attrs.get("is_feasible"),
        "constraint_violations": attrs.get("constraint_violations", []),
        "visible_transition_count": attrs.get("visible_transition_count"),
    }
    if attrs.get("evaluation_error"):
        payload["evaluation_error"] = attrs.get("evaluation_error")
    return payload


def _non_dominated_evaluation_ids(solutions: List[Any]) -> set[str]:
    return feasible_non_dominated_evaluation_ids(solutions)


def _count_failed_solutions(all_solutions: List[Dict[str, Any]], observed_error_count: int = 0) -> int:
    serialized_error_count = sum(1 for item in all_solutions if item.get("evaluation_error"))
    return max(int(observed_error_count or 0), serialized_error_count)


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return str(value)


def _build_csv_bytes(fieldnames: List[str], rows: List[Dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _csv_cell(row.get(field)) for field in fieldnames})
    return buffer.getvalue().encode("utf-8")


def _safe_filename_part(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._-")
    return sanitized or fallback


def _build_experiment_export_archive(
    experiment: Dict[str, Any],
    solutions: List[Dict[str, Any]],
    snapshot_solutions: List[Dict[str, Any]],
    original_artifacts: Dict[str, Any] | None = None,
) -> tuple[bytes, str]:
    experiment_fields = [
        "constraints",
        "experiment_id",
        "experiment_name",
        "start_at",
        "end_at",
        "max_evals",
        "pop_size",
        "workers",
        "seed",
        "log_path",
        "metrics",
        "miners",
        "preprocessing",
        "actual_evaluations",
        "conformance_mode",
        "log_sha256",
        "optimizer_source_sha256",
        "prom_revision",
        "quality_policy_version",
        "optimizer_config",
    ]
    solution_fields = [
        "optimization_feasible",
        "solution_id",
        "experiment_id",
        "variables",
        "objectives",
        "metrics",
        "pipeline",
        "runtime_ms",
        "is_pareto",
        "places",
        "transitions",
        "arcs",
        "visible_transition_count",
        "is_feasible",
        "constraint_violations",
        "model_schema_version",
        "initial_marking",
        "final_marking",
        "final_markings",
        "pipeline_full",
        "evaluation_id",
        "fingerprint",
        "evaluation_error",
        "evaluation_status",
        "logical_attempt_id",
        "constraints",
        "evaluation_policy_version",
        "model_semantic_sha256",
        "discovery_metadata",
        "metrics_status",
        "import_provenance",
    ]
    snapshot_solution_fields = [
        "optimization_feasible",
        "snapshot_solution_id",
        "snapshot_id",
        "experiment_id",
        "snapshot_index",
        "evaluations_done",
        "member_index",
        "variables",
        "objectives",
        "metrics",
        "pipeline",
        "runtime_ms",
        "is_pareto",
        "places",
        "transitions",
        "arcs",
        "visible_transition_count",
        "is_feasible",
        "constraint_violations",
        "model_schema_version",
        "initial_marking",
        "final_marking",
        "final_markings",
        "pipeline_full",
        "evaluation_id",
        "fingerprint",
        "evaluation_error",
        "evaluation_status",
        "logical_attempt_id",
        "constraints",
        "evaluation_policy_version",
        "model_semantic_sha256",
        "discovery_metadata",
        "metrics_status",
        "import_provenance",
    ]
    population_snapshot_fields = [
        "snapshot_id",
        "experiment_id",
        "snapshot_index",
        "evaluations_done",
        "attempts_since_previous",
        "cache_hits_since_previous",
        "errors_since_previous",
        "unique_pipelines_since_previous",
    ]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("experiment.csv", _build_csv_bytes(experiment_fields, [experiment]))
        archive.writestr("solutions.csv", _build_csv_bytes(solution_fields, solutions))
        archive.writestr(
            "snapshot_solutions.csv",
            _build_csv_bytes(snapshot_solution_fields, snapshot_solutions),
        )
        archive.writestr(
            "population_snapshots.csv",
            _build_csv_bytes(population_snapshot_fields, experiment.get("population_snapshots") or []),
        )
        if original_artifacts is not None:
            manifest = []
            for evaluation_id, artifact in sorted(original_artifacts.items()):
                pnml = artifact.get("pnml")
                if not pnml:
                    manifest.append({"evaluation_id": evaluation_id, "original_available": False})
                    continue
                name = _safe_filename_part(evaluation_id, "model")
                if name != evaluation_id:
                    name += "_" + hashlib.sha256(evaluation_id.encode()).hexdigest()[:16]
                pnml_path, metadata_path = f"models/{name}.pnml", f"models/{name}.json"
                content = pnml.encode("utf-8")
                archive.writestr(pnml_path, content)
                archive.writestr(metadata_path, json.dumps(artifact.get("metadata") or {}, ensure_ascii=False, sort_keys=True))
                manifest.append({"evaluation_id": evaluation_id, "original_available": True,
                                 "pnml_path": pnml_path, "metadata_path": metadata_path,
                                 "pnml_sha256": hashlib.sha256(content).hexdigest()})
            archive.writestr("models/index.json", json.dumps({"version": 1, "models": manifest}, sort_keys=True))

    filename = "experiment_{experiment_id}_{experiment_name}.zip".format(
        experiment_id=_safe_filename_part(experiment.get("experiment_id"), "experiment"),
        experiment_name=_safe_filename_part(experiment.get("experiment_name"), "data"),
    )
    return zip_buffer.getvalue(), filename


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
