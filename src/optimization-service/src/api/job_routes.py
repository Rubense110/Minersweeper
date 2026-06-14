from __future__ import annotations

import json
import queue
from typing import Any, Dict

from flask import Blueprint, Response, jsonify, request, stream_with_context

from .common import _TERMINAL_JOB_STATUSES, _to_bool
from .dependencies import get_manager


bp = Blueprint("optimization_jobs", __name__)


@bp.get("/optimizations")
def list_jobs() -> Any:
    return jsonify({"jobs": get_manager().list_jobs()})


@bp.post("/optimizations")
def create_job() -> Any:
    payload = request.get_json(silent=True) or {}
    try:
        job = get_manager().submit(payload)
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    return jsonify(job), 202


@bp.post("/optimizations/<job_id>/cancel")
def cancel_job(job_id: str) -> Any:
    try:
        job = get_manager().cancel(job_id)
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404
    except RuntimeError as exc:
        return jsonify({"error": "invalid_state", "message": str(exc)}), 409
    return jsonify(job), 202


@bp.get("/optimizations/<job_id>")
def get_job(job_id: str) -> Any:
    try:
        return jsonify(get_manager().get(job_id))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404


@bp.get("/optimizations/<job_id>/progress")
def get_job_progress(job_id: str) -> Any:
    try:
        return jsonify(get_manager().get_progress(job_id))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404


def _format_sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"


@bp.get("/optimizations/<job_id>/events")
def stream_job_events(job_id: str) -> Any:
    try:
        listener, initial_events = get_manager().subscribe_events(job_id)
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404

    def generate():
        terminal = False
        try:
            yield "retry: 2000\n\n"
            for item in initial_events:
                yield _format_sse(item["event"], item["data"])
                if item["event"] == "status_changed" and item["data"].get("status") in _TERMINAL_JOB_STATUSES:
                    terminal = True
            while not terminal:
                try:
                    item = listener.get(timeout=15.0)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield _format_sse(item["event"], item["data"])
                if item["event"] == "status_changed" and item["data"].get("status") in _TERMINAL_JOB_STATUSES:
                    terminal = True
        finally:
            get_manager().unsubscribe_events(job_id, listener)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers=headers)


@bp.get("/optimizations/<job_id>/solutions")
def get_solutions(job_id: str) -> Any:
    scope = (request.args.get("scope") or "pareto").strip().lower()
    if scope not in {"pareto", "all"}:
        return jsonify({"error": "invalid_request", "message": "scope must be 'pareto' or 'all'"}), 400

    try:
        return jsonify(get_manager().get_solutions(job_id, scope))
    except KeyError:
        return jsonify({"error": "not_found", "message": f"job '{job_id}' not found"}), 404
    except RuntimeError as exc:
        return jsonify({"error": "invalid_state", "message": str(exc)}), 409

