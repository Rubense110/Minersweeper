"""Import the application's common export; never synthesize missing PNML."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import PurePosixPath
import uuid
import zipfile
from datetime import datetime, timezone


GRAPH_FIELDS = ('places', 'transitions', 'arcs', 'initial_marking', 'final_marking', 'final_markings')
MAX_BYTES = 64 * 1024 * 1024
MAX_MODELS = 500


def archive_files(content: bytes) -> dict[str, bytes]:
    if len(content) > MAX_BYTES:
        raise ValueError('El ZIP supera el límite de 64 MiB.')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = [i for i in archive.infolist() if not i.is_dir()]
            if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_BYTES:
                raise ValueError('El contenido expandido supera los límites de importación.')
            result = {}
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename or info.filename in result:
                    raise ValueError('El ZIP contiene rutas inseguras o duplicadas.')
                result[info.filename] = archive.read(info)
            return result
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError('No se puede leer el ZIP.') from exc


def _rows(files, name):
    if name not in files:
        raise ValueError(f'Falta {name} en la exportación.')
    try:
        return list(csv.DictReader(io.StringIO(files[name].decode('utf-8-sig'))))
    except (UnicodeError, csv.Error) as exc:
        raise ValueError(f'CSV inválido: {name}.') from exc


def _cell(value):
    if value == '' or value is None:
        return None
    if value in ('True', 'False'):
        return value == 'True'
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def graph_signature(graph):
    """IDs must agree with source files; labels of places are presentation only."""
    def marking(m):
        return sorted((e['place_id'], e['tokens']) for e in (m or []))
    return {
        'places': sorted(p['id'] for p in graph['places']),
        'transitions': sorted((t['id'], t.get('label'), t['invisible']) for t in graph['transitions']),
        'arcs': sorted((a['id'], a['source'], a['target'], a.get('weight', 1)) for a in graph['arcs']),
        'initial': marking(graph['initial_marking']),
        'final': marking(graph['final_marking']),
        'finals': sorted(marking(m) for m in graph['final_markings']),
    }


def validate_original(row, pnml: bytes, metadata: dict) -> dict:
    from api.petri import _petri_from_v2_artifact
    if metadata.get('model_schema_version') not in (2, 3):
        raise ValueError('La exploración requiere metadata semántica de versión 2 o 3.')
    if metadata.get('evaluation_id') != row.get('evaluation_id'):
        raise ValueError('El evaluation_id del original no coincide con la solución.')
    for field in ('model_schema_version', 'visible_transition_count', 'is_feasible', 'constraint_violations'):
        if row.get(field) != metadata.get(field):
            raise ValueError(f'La metadata y el CSV difieren en {field}.')
    if len(pnml) > 2 * 1024 * 1024 or b'<!DOCTYPE' in pnml.upper() or b'<!ENTITY' in pnml.upper():
        raise ValueError('PNML demasiado grande o con declaraciones XML no permitidas.')
    text = pnml.decode('utf-8')
    parts = _petri_from_v2_artifact({**metadata, 'pnml': text})
    graph = dict(zip(GRAPH_FIELDS, parts))
    if graph_signature(graph) != graph_signature(row):
        raise ValueError(f"El PNML/metadata y el grafo CSV difieren para {row.get('evaluation_id')}.")
    return {'pnml': text, 'metadata': metadata, 'pnml_sha256': hashlib.sha256(pnml).hexdigest()}


def import_export(store, content: bytes, supplementary: dict[str, bytes] | None = None) -> str:
    files = archive_files(content)
    supplementary = supplementary or {}
    if sum(len(v) for v in supplementary.values()) > MAX_BYTES:
        raise ValueError('Los originales complementarios superan los límites.')
    experiments = _rows(files, 'experiment.csv')
    if len(experiments) != 1:
        raise ValueError('Se requiere exactamente un experimento por colección.')
    experiment = {k: _cell(v) for k, v in experiments[0].items()}
    from constraints import normalize_constraints
    experiment['constraints'] = normalize_constraints(experiment.get('constraints'))
    rows = [{k: _cell(v) for k, v in r.items()} for r in _rows(files, 'solutions.csv')]
    if not rows or len(rows) > MAX_MODELS:
        raise ValueError(f'La colección debe contener entre 1 y {MAX_MODELS} individuos.')
    identities = [str(r.get('solution_id')) for r in rows]
    if any(not isinstance(r.get('solution_id'), int) or isinstance(r.get('solution_id'), bool) or r['solution_id'] <= 0 for r in rows) or len(set(identities)) != len(rows):
        raise ValueError('Faltan identidades de solución o están duplicadas.')
    manifest = {}
    if 'models/index.json' in files:
        index = json.loads(files['models/index.json'])
        for item in index['models']:
            if item['evaluation_id'] in manifest:
                raise ValueError('El manifiesto contiene evaluation_id duplicados.')
            manifest[item['evaluation_id']] = item
    originals = {}
    # Historical source files are accepted by basename, without accessing server paths.
    raw_files = {}
    for name, value in {**files, **supplementary}.items():
        basename = PurePosixPath(name).name
        if basename.endswith(('.pnml', '.json')) and basename != 'index.json':
            if basename in raw_files and raw_files[basename] != value:
                raise ValueError(f'Originales con nombres en conflicto: {basename}.')
            raw_files[basename] = value
    for row in rows:
        evaluation = row.get('evaluation_id')
        if not isinstance(evaluation, str) or not evaluation or len(evaluation) > 128:
            raise ValueError('Cada individuo debe referenciar un evaluation_id.')
        if row.get('experiment_id') != experiment.get('experiment_id'):
            raise ValueError('La colección mezcla experimentos.')
        item = manifest.get(evaluation, {})
        pnml = files.get(item.get('pnml_path', '')) or raw_files.get(evaluation + '.pnml')
        metadata_bytes = files.get(item.get('metadata_path', '')) or raw_files.get(evaluation + '.json')
        if not pnml or not metadata_bytes:
            raise ValueError(f'Falta el PNML original o su metadata para {evaluation}. Adjunta los pares originales.')
        metadata = json.loads(metadata_bytes)
        original = validate_original(row, pnml, metadata)
        from .analysis import validate_graph
        validate_graph(row)
        if item.get('pnml_sha256') and item['pnml_sha256'] != original['pnml_sha256']:
            raise ValueError(f'Hash de PNML incorrecto: {evaluation}.')
        if evaluation in originals and original != originals[evaluation]:
            raise ValueError('Originales incompatibles para el mismo evaluation_id.')
        originals[evaluation] = original
        row['original_pnml'] = original['pnml']
        row['original_metadata'] = original['metadata']
        row['metrics_status'] = row.get('metrics_status') or metadata.get('metrics_status', 'unknown')
        row['import_provenance'] = row.get('import_provenance') or {
            'experiment_id': experiment['experiment_id'], 'solution_id': row['solution_id'],
            'archive_sha256': hashlib.sha256(content).hexdigest(),
        }
    imported_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    def date(value):
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')) if value else now
    data = {
        **experiment, 'experiment_id': imported_id,
        'experiment_name': str(experiment.get('experiment_name') or 'Imported population')[:255],
        'start_at': date(experiment.get('start_at')), 'end_at': date(experiment.get('end_at')),
        'max_evals': int(experiment.get('max_evals') or 0), 'workers': int(experiment.get('workers') or 1),
        'log_path': str(experiment.get('log_path') or ''), 'pop_size': len(rows),
        'optimizer_config': {**(experiment.get('optimizer_config') or {}),
                             'import_source_experiment_id': experiment['experiment_id'], 'import_scope': 'final_population'},
    }
    # Exploration imports the final population only. Historical snapshots remain in the supplied export.
    store.save_completed_experiment(data, rows)
    return imported_id
