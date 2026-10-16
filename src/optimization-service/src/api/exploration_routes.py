from __future__ import annotations

import hashlib
import json
import threading

from flask import Blueprint, Response, current_app, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from model_exploration.importing import MAX_BYTES, archive_files, import_export
from model_exploration.service import ExplorationBusy, ExplorationService
from .dependencies import get_manager

bp = Blueprint('model_exploration', __name__)
_service_lock = threading.Lock()


def service():
    store = get_manager().job_store
    with _service_lock:
        instance = current_app.config.get('exploration_service')
        if instance is None or instance.store is not store:
            instance = ExplorationService(store)
            current_app.config['exploration_service'] = instance
    return instance


def _error(exc):
    if isinstance(exc, KeyError):
        return jsonify(error='not_found', message='Experimento, exploración o modelo no encontrado.'), 404
    if isinstance(exc, ExplorationBusy):
        return jsonify(error='busy', message=str(exc)), 429
    return jsonify(error='invalid_request', message=str(exc)), 400


@bp.post('/explorations/import')
def import_population():
    try:
        request.max_content_length = MAX_BYTES
        uploaded = request.files.get('archive')
        if not uploaded:
            raise ValueError('Adjunta la exportación estándar en archive.')
        supplementary = {}
        total = 0
        for file in request.files.getlist('originals'):
            value = file.read(MAX_BYTES + 1)
            total += len(value)
            if total > MAX_BYTES:
                raise ValueError('Los originales superan los límites de importación.')
            if file.filename.lower().endswith('.zip'):
                additional = archive_files(value)
            else:
                additional = {file.filename: value}
            for name, content in additional.items():
                if name in supplementary and supplementary[name] != content:
                    raise ValueError('Originales complementarios en conflicto.')
                supplementary[name] = content
        eid = import_export(get_manager().job_store, uploaded.read(MAX_BYTES + 1), supplementary)
        return jsonify(experiment_id=eid), 201
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, UnicodeError, RequestEntityTooLarge) as exc:
        return _error(exc)


@bp.post('/experiments/<experiment_id>/explorations')
def create_exploration(experiment_id):
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError('El cuerpo debe ser un objeto JSON.')
        result = service().start(experiment_id, payload.get('representation', 'petri'))
        return jsonify(result), 200 if result['status'] == 'completed' else 202
    except (ValueError, KeyError, ExplorationBusy) as exc:
        return _error(exc)


@bp.get('/explorations/<exploration_id>')
def get_exploration(exploration_id):
    try:
        result = service().get(exploration_id)
        return jsonify({k: v for k, v in result.items() if k not in ('views', 'derived_models')})
    except KeyError as exc:
        return _error(exc)


@bp.post('/explorations/<exploration_id>/cancel')
def cancel_exploration(exploration_id):
    try:
        return jsonify(service().cancel(exploration_id))
    except KeyError as exc:
        return _error(exc)


@bp.get('/explorations/<exploration_id>/views/<kind>')
def get_view(exploration_id, kind):
    if kind not in ('merging', 'variation', 'template'):
        return _error(ValueError('Vista desconocida.'))
    try:
        result = service().get(exploration_id)
        if result['status'] != 'completed':
            return jsonify(error='not_ready', message='El análisis no ha terminado.'), 409
        return jsonify(result['views'][kind])
    except KeyError as exc:
        return _error(exc)


@bp.get('/explorations/<exploration_id>/models/<model_id>')
@bp.get('/explorations/<exploration_id>/models/<model_id>/pnml')
def get_source_model(exploration_id, model_id):
    try:
        result = service().get(exploration_id)
        if result['status'] != 'completed':
            return jsonify(error='not_ready', message='El análisis no ha terminado.'), 409
        item = next((m for m in result['models'] if m['model_id'] == model_id), None)
        if not item:
            raise KeyError(model_id)
        store = get_manager().job_store
        row = store.get_experiment_solution(result['experiment_id'], item['solution_id'])
        artifact = store.get_original_artifact(result['experiment_id'], row['evaluation_id'])
        if not artifact.get('pnml'):
            raise KeyError(model_id)
        if request.path.endswith('/pnml'):
            # Original bytes, never reconstructed from the overlay.
            return Response(artifact['pnml'].encode('utf-8'), mimetype='application/xml',
                            headers={'Content-Disposition': f'attachment; filename="{model_id}.pnml"'})
        return jsonify({**row, 'model_id': model_id, 'display_name': item['display_name'],
                        'representation': result.get('representation', 'petri'),
                        'bpmn': result.get('derived_models', {}).get(model_id),
                        'pnml_sha256': hashlib.sha256(artifact['pnml'].encode('utf-8')).hexdigest(),
                        'original_metadata': artifact['metadata']})
    except (KeyError, StopIteration) as exc:
        return _error(KeyError(str(exc)))
