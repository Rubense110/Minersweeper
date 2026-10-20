from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, jsonify, request

from .common import LOGGER
from .petri import _render_petri_image_bytes
from .bpmn import _render_bpmn_image_bytes


bp = Blueprint("optimization_petri", __name__)


@bp.post("/petri/render")
@bp.post("/bpmn/render")
def render_petri_net() -> Any:
    payload = request.get_json(silent=True) or {}
    output_format = (request.args.get("format") or payload.get("format") or "svg").strip().lower()
    try:
        renderer = _render_bpmn_image_bytes if request.path.endswith('/bpmn/render') else _render_petri_image_bytes
        image_bytes, mimetype = renderer(
            places_payload=payload.get("places"),
            transitions_payload=payload.get("transitions"),
            arcs_payload=payload.get("arcs"),
            initial_marking_payload=payload.get("initial_marking"),
            final_marking_payload=payload.get("final_marking"),
            final_markings_payload=payload.get("final_markings"),
            output_format=output_format,
        )
        return Response(image_bytes, mimetype=mimetype, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400
    except Exception as exc:
        LOGGER.exception("model image render failed")
        return jsonify({"error": "render_failed", "message": str(exc)}), 500
