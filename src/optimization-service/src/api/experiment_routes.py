from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, jsonify, request

from model_selection import ModelSelectionUnavailable

from .dependencies import get_manager


bp = Blueprint("optimization_experiments", __name__)


@bp.get("/experiments")
def list_experiments() -> Any:
    return jsonify({"experiments": get_manager().list_experiments()})


@bp.get("/experiments/<experiment_id>")
def get_experiment(experiment_id: str) -> Any:
    try:
        return jsonify(get_manager().get_experiment(experiment_id))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"experiment '{experiment_id}' not found"}), 404


@bp.delete("/experiments/<experiment_id>")
def delete_experiment(experiment_id: str) -> Any:
    try:
        return jsonify(get_manager().delete_experiment(experiment_id))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"experiment '{experiment_id}' not found"}), 404


@bp.get("/experiments/<experiment_id>/solutions")
def get_experiment_solutions(experiment_id: str) -> Any:
    scope = (request.args.get("scope") or "all").strip().lower()
    if scope not in {"pareto", "all"}:
        return jsonify({"error": "invalid_request", "message": "scope must be 'pareto' or 'all'"}), 400
    try:
        return jsonify(get_manager().get_experiment_solutions(experiment_id=experiment_id, scope=scope))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"experiment '{experiment_id}' not found"}), 404


@bp.post("/experiments/<experiment_id>/select-model")
def select_experiment_model(experiment_id: str) -> Any:
    payload = request.get_json(silent=True) or {}
    scope = str(payload.get("scope") or "pareto").strip().lower()
    if scope not in {"pareto", "all"}:
        return jsonify({"error": "invalid_request", "message": "scope must be 'pareto' or 'all'"}), 400
    weights = payload.get("weights")
    if weights is None:
        weights = {}
    if not isinstance(weights, dict):
        return jsonify({"error": "invalid_request", "message": "weights must be an object"}), 400

    try:
        return jsonify(
            get_manager().select_experiment_model(
                experiment_id=experiment_id,
                weights=weights,
                scope=scope,
            )
        )
    except KeyError:
        return jsonify({"error": "not_found", "message": f"experiment '{experiment_id}' not found"}), 404
    except ModelSelectionUnavailable as exc:
        return jsonify({"error": "invalid_state", "message": str(exc)}), 409


@bp.get("/experiments/<experiment_id>/download")
def download_experiment_data(experiment_id: str) -> Any:
    try:
        payload, filename = get_manager().get_experiment_export(experiment_id)
    except KeyError:
        return jsonify({"error": "not_found", "message": f"experiment '{experiment_id}' not found"}), 404

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(payload, mimetype="application/zip", headers=headers)
