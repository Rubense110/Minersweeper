from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from typing import Any, Dict, List


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
        "experiment_id": attrs.get("experiment_id"),
        "fingerprint": attrs.get("fingerprint"),
        "pipeline": attrs.get("pipeline", {}),
        "metrics": attrs.get("metrics", {}),
        "objective_metrics": attrs.get("objective_metrics", {}),
        "runtime_ms": _to_int_or_none(attrs.get("runtime_ms")),
        "objectives": list(getattr(solution, "objectives", []) or []),
        "variables": list(getattr(solution, "variables", []) or []),
        "is_pareto": bool(evaluation_id and evaluation_id in pareto_ids),
    }
    if attrs.get("evaluation_error"):
        payload["evaluation_error"] = attrs.get("evaluation_error")
    return payload


def _non_dominated_evaluation_ids(solutions: List[Any]) -> set[str]:
    evaluation_ids: set[str] = set()
    for solution in solutions:
        attrs = getattr(solution, "attributes", {}) or {}
        evaluation_id = attrs.get("evaluation_id")
        if evaluation_id:
            evaluation_ids.add(str(evaluation_id))
    return evaluation_ids


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
) -> tuple[bytes, str]:
    experiment_fields = [
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
    ]
    solution_fields = [
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
        "initial_marking",
        "final_markings",
    ]
    snapshot_solution_fields = [
        "snapshot_solution_id",
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
        "initial_marking",
        "final_markings",
    ]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("experiment.csv", _build_csv_bytes(experiment_fields, [experiment]))
        archive.writestr("solutions.csv", _build_csv_bytes(solution_fields, solutions))
        archive.writestr(
            "snapshot_solutions.csv",
            _build_csv_bytes(snapshot_solution_fields, snapshot_solutions),
        )

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
