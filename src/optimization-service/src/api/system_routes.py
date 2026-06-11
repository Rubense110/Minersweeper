from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify

from .common import _list_logs_in_root


bp = Blueprint("optimization_system", __name__)


@bp.get("/health")
def health() -> Any:
    return jsonify({"status": "ok"})


@bp.get("/logs")
def list_logs() -> Any:
    return jsonify({"logs": _list_logs_in_root()})
