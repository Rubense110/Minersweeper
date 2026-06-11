from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, jsonify, request

from .common import LOGGER
from .petri import _render_petri_image_bytes


bp = Blueprint("optimization_petri", __name__)


@bp.post("/petri/render")
def render_petri_net() -> Any:
    payload = request.get_json(silent=True) or {}
    output_format = (request.args.get("format") or payload.get("format") or "svg").strip().lower()
    try:
        image_bytes, mimetype = _render_petri_image_bytes(
            places_payload=payload.get("places"),
            transitions_payload=payload.get("transitions"),
            arcs_payload=payload.get("arcs"),
            initial_marking_payload=payload.get("initial_marking"),
            final_marking_payload=payload.get("final_marking"),
            output_format=output_format,
        )
        return Response(image_bytes, mimetype=mimetype, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    except Exception as exc:
        LOGGER.exception("petri render failed")
        return jsonify({"error": "render_failed", "message": str(exc)}), 500
