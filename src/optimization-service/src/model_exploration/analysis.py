"""Three provenance-preserving structural adaptations; outputs are not Petri nets.

La Rosa et al. (2013): node correspondences and annotated overlay.
Assy et al. (2017): verified shared interfaces and nested fragment exploration.
Ilahi et al. (2017): strict common core and variable template blocks.
See docs session for departures from the published algorithms.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
import hashlib
import json
import time

from .importing import GRAPH_FIELDS, validate_original

VERSION = 'structural-exploration-v1.4'
REPRESENTATIONS = ('petri', 'bpmn')
REFERENCES = {
    'merging': {'title': 'La Rosa et al. (2013)', 'url': 'https://doi.org/10.1145/2430545.2430547'},
    'variation': {'title': 'Assy et al. (2017)', 'url': 'https://www.vdaalst.rwth-aachen.de/publications/p916.pdf'},
    'template': {'title': 'Ilahi et al. (2017), BPFlexTemplate', 'url': 'https://ijispm.sciencesphere.org/archive/ijispm-050304.pdf'},
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def is_activity(node):
    return node['kind'] == 'task' or (node['kind'] == 'transition' and not node.get('invisible'))


def validate_graph(row):
    nodes = row['places'] + row['transitions']
    ids = [n['id'] for n in nodes]
    if len(ids) != len(set(ids)) or any(not i for i in ids):
        raise ValueError('IDs de nodos vacíos o duplicados.')
    kinds = {p['id']: 'place' for p in row['places']}
    kinds.update({t['id']: 'transition' for t in row['transitions']})
    arcs = row['arcs']
    if len({a['id'] for a in arcs}) != len(arcs):
        raise ValueError('IDs de arcos duplicados.')
    for a in arcs:
        w = a.get('weight', 1)
        if a['source'] not in kinds or a['target'] not in kinds or kinds[a['source']] == kinds[a['target']]:
            raise ValueError('Arco inválido: la red debe ser bipartita y referenciar nodos existentes.')
        if isinstance(w, bool) or not isinstance(w, int) or w < 1:
            raise ValueError('Peso de arco inválido.')
    for marking in [row['initial_marking'], *row['final_markings']]:
        seen = set()
        for e in marking:
            if kinds.get(e['place_id']) != 'place' or e['place_id'] in seen or not isinstance(e['tokens'], int) or isinstance(e['tokens'], bool) or e['tokens'] < 1:
                raise ValueError('Marking inválido.')
            seen.add(e['place_id'])


def prepare_models(solutions, originals):
    models = []
    for index, row in enumerate(sorted(solutions, key=lambda r: str(r['solution_id'])), 1):
        artifact = originals.get(row.get('evaluation_id'), {})
        if not artifact.get('pnml') or not artifact.get('metadata'):
            raise ValueError(f"Falta PNML original/metadata de {row.get('evaluation_id')}. Importa los originales históricos.")
        original = validate_original(row, artifact['pnml'].encode('utf-8'), artifact['metadata'])
        validate_graph(row)
        mid = f"m-{row['solution_id']}"
        model = {**row, 'model_id': mid, 'display_name': f'M{index:02d}', 'pnml_sha256': original['pnml_sha256']}
        model['_nodes'] = {n['id']: {**n, 'kind': 'place'} for n in row['places']}
        model['_nodes'].update({n['id']: {**n, 'kind': 'transition'} for n in row['transitions']})
        models.append(model)
    if not models or len({m['model_id'] for m in models}) != len(models):
        raise ValueError('Población vacía o identidades duplicadas.')
    return models


def _check(cancel):
    if cancel and cancel():
        raise InterruptedError('Exploración cancelada.')


def _components(nodes, edges):
    adjacency = {n: set() for n in nodes}
    for e in edges:
        a, b = e['source'], e['target']
        if a in adjacency and b in adjacency:
            adjacency[a].add(b)
            adjacency[b].add(a)
    remaining = set(nodes)
    components = []
    while remaining:
        seed = min(remaining)
        todo, found = [seed], set()
        while todo:
            n = todo.pop()
            if n in found:
                continue
            found.add(n)
            todo.extend(adjacency[n] - found)
        remaining -= found
        components.append(found)
    return components


def align(models, cancel=None):
    """Visible labels are activity anchors; anonymous routing requires context.

    Three directed refinement rounds. Symmetric nodes stay separate in each
    source: no arbitrary one-to-many correspondences or cross-model ID matching.
    """
    for m in models:
        _check(cancel)
        nodes = m['_nodes']
        labels = Counter(n.get('label') for n in nodes.values() if is_activity(n))
        initial = {e['place_id']: e['tokens'] for e in m['initial_marking']}
        finals = [{e['place_id']: e['tokens'] for e in f} for f in m['final_markings']]
        base = {}
        for nid, n in nodes.items():
            if n['kind'] == 'place':
                base[nid] = ['place', initial.get(nid, 0), sorted(f.get(nid, 0) for f in finals)]
            elif n.get('invisible'):
                base[nid] = ['invisible']
            elif not is_activity(n):
                base[nid] = [n['kind'], n.get('gateway_direction', '')]
            else:
                base[nid] = ['activity', n.get('label')]
        colors = {nid: digest(b) for nid, b in base.items()}
        for _ in range(3):
            neighbours = {n: [] for n in nodes}
            for a in m['arcs']:
                neighbours[a['source']].append(['out', a.get('weight', 1), colors[a['target']]])
                neighbours[a['target']].append(['in', a.get('weight', 1), colors[a['source']]])
            colors = {nid: digest([base[nid], sorted(neighbours[nid])])
                      if not is_activity(n) or labels[n.get('label')] > 1
                      else digest(base[nid]) for nid, n in nodes.items()}
        counts = Counter(colors.values())
        m['_mapping'] = {}
        m['_ambiguous'] = set()
        for nid in sorted(nodes):
            key = colors[nid]
            if counts[key] > 1:
                m['_ambiguous'].add(nid)
                key = digest([key, m['model_id'], nid])
            m['_mapping'][nid] = 'n-' + key[:24]
    total = len(models)
    nodes, edges = {}, {}
    for m in models:
        _check(cancel)
        for nid, n in sorted(m['_nodes'].items()):
            key = m['_mapping'][nid]
            item = nodes.setdefault(key, {
                'id': key, 'kind': n['kind'], 'label': n.get('label') if n['kind'] != 'place' and not n.get('invisible') else ('τ' if n.get('invisible') else '○'),
                **({'gateway_direction': n['gateway_direction']} if 'gateway_direction' in n else {}),
                'invisible': n.get('invisible', False), 'sources': {},
                'matching': 'ambiguous' if nid in m['_ambiguous'] else ('activity_label' if is_activity(n) else 'structural_context'),
            })
            item['sources'][m['model_id']] = [nid]
        occurrences = Counter()
        for a in sorted(m['arcs'], key=lambda x: x['id']):
            signature = (m['_mapping'][a['source']], m['_mapping'][a['target']], a.get('weight', 1))
            occurrence = occurrences[signature]
            occurrences[signature] += 1
            key = 'a-' + digest([*signature, occurrence])[:24]
            item = edges.setdefault(key, {'id': key, 'source': signature[0], 'target': signature[1], 'weight': signature[2], 'sources': {}})
            item['sources'][m['model_id']] = [a['id']]
    for item in [*nodes.values(), *edges.values()]:
        item['model_ids'] = sorted(item['sources'])
        item['support'] = len(item['model_ids'])
        item['common'] = item['support'] == total
    # Shared labels may have changing context; do not describe them as identical subnets.
    by_id = {m['model_id']: m for m in models}
    for n in nodes.values():
        contexts = set()
        for mid, original_ids in n['sources'].items():
            m = by_id[mid]
            nid = original_ids[0]
            contexts.add(digest(sorted([('out' if a['source'] == nid else 'in', a.get('weight', 1), m['_mapping'][a['target'] if a['source'] == nid else a['source']])
                                       for a in m['arcs'] if nid in (a['source'], a['target'])])))
        n['context_varies'] = len(contexts) > 1
    return {'nodes': sorted(nodes.values(), key=lambda n: n['id']), 'edges': sorted(edges.values(), key=lambda n: n['id'])}


def fragment(model, nodes):
    nodes = set(nodes)
    incoming, outgoing, arc_ids = set(), set(), []
    for a in model['arcs']:
        inside_s, inside_t = a['source'] in nodes, a['target'] in nodes
        if inside_s or inside_t:
            arc_ids.append(a['id'])
        if not inside_s and inside_t:
            incoming.add(a['source'])
        if inside_s and not inside_t:
            outgoing.add(a['target'])
    mapping = model['_mapping']
    return {'model_id': model['model_id'], 'node_ids': sorted(nodes), 'arc_ids': sorted(arc_ids),
            'entry_ids': sorted(incoming), 'exit_ids': sorted(outgoing),
            'entries': sorted(mapping[n] for n in incoming), 'exits': sorted(mapping[n] for n in outgoing)}


def activity_projection(models, overlay, cancel=None):
    """Readable overlay of activities, with one real path witness per model/pair.

    Walk each original separately, through places and invisible transitions only,
    stopping at the first visible transition. This is directed connectivity,
    not a directly-follows log, enabledness, or behavioral equivalence. BFS avoids
    enumerating paths in cyclic nets; retained witnesses preserve source IDs.
    """
    edges = {}
    for model in models:
        _check(cancel)
        nodes, mapping = model['_nodes'], model['_mapping']
        visible = {nid for nid, n in nodes.items() if is_activity(n)}
        outgoing = defaultdict(list)
        for arc in sorted(model['arcs'], key=lambda a: a['id']):
            outgoing[arc['source']].append(arc)
        for start in sorted(visible):
            _check(cancel)
            queue = deque([(start, [start], [])])
            visited, reached = {start}, set()
            while queue:
                current, path_nodes, path_arcs = queue.popleft()
                for arc in outgoing[current]:
                    target = arc['target']
                    next_nodes, next_arcs = [*path_nodes, target], [*path_arcs, arc['id']]
                    if target in visible:
                        if target in reached:
                            continue
                        reached.add(target)
                        pair = (mapping[start], mapping[target])
                        item = edges.setdefault(pair, {'id': 'path-' + digest(pair)[:24],
                            'source': pair[0], 'target': pair[1], 'kind': 'structural_path',
                            'label': f"{nodes[start].get('label')} → {nodes[target].get('label')}", 'sources': []})
                        item['sources'].append({'model_id': model['model_id'], 'node_ids': list(dict.fromkeys(next_nodes)),
                                                'arc_ids': next_arcs, 'entry_ids': [], 'exit_ids': []})
                    elif target not in visited:
                        visited.add(target)
                        queue.append((target, next_nodes, next_arcs))
    for edge in edges.values():
        edge['sources'].sort(key=lambda f: (f['model_id'], f['node_ids'], f['arc_ids']))
        edge['model_ids'] = sorted({f['model_id'] for f in edge['sources']})
        edge['support'] = len(edge['model_ids'])
        edge['common'] = edge['support'] == len(models)
    return {'nodes': [n for n in overlay['nodes'] if is_activity(n)],
            'edges': sorted(edges.values(), key=lambda e: e['id']),
            'semantics': 'directed_original_paths_without_intermediate_visible_transitions',
            'witness_policy': 'one_shortest_path_per_original_transition_pair; not_all_routing_alternatives'}


def alternatives(fragments, by_id, total, boundary_markings=False):
    groups = {}
    for f in fragments:
        m = by_id[f['model_id']]
        mapping = m['_mapping']
        arcs = [a for a in m['arcs'] if a['id'] in set(f['arc_ids'])]
        selected = set(f['node_ids'])
        annotated = selected | set(f.get('entry_ids', [])) | set(f.get('exit_ids', [])) if boundary_markings else selected
        def marking(mark):
            return sorted((mapping[e['place_id']], e['tokens']) for e in mark if e['place_id'] in annotated)
        key = digest({'nodes': sorted(mapping[n] for n in selected),
                      'arcs': sorted((mapping[a['source']], mapping[a['target']], a.get('weight', 1)) for a in arcs),
                      'initial': marking(m['initial_marking']), 'finals': sorted(marking(fm) for fm in m['final_markings'])})
        item = groups.setdefault(key, {'id': 'alt-' + key[:24], 'sources': [], 'model_ids': [], 'structural_status': 'same_mapped_structure',
                                      'visible_activities': sorted({m['_nodes'][n].get('label') or '' for n in selected if is_activity(m['_nodes'][n])}),
                                      'node_count': len(selected), 'arc_count': len(arcs),
                                      'invisible_transitions': sum(m['_nodes'][n].get('invisible', False) for n in selected)})
        item['sources'].append(f)
        item['model_ids'].append(f['model_id'])
    for item in groups.values():
        item['sources'].sort(key=lambda f: f['model_id'])
        item['model_ids'] = sorted(set(item['model_ids']))
        item['support'] = len(item['model_ids'])
        item['common'] = item['support'] == total
    return sorted(groups.values(), key=lambda a: (-a['support'], a['id']))


def variation_regions(models, cancel=None):
    from .variation import detect_regions
    return detect_regions(models, cancel)


def common_template(models, overlay, cancel=None):
    total, by_id = len(models), {m['model_id']: m for m in models}
    core = {n['id'] for n in overlay['nodes'] if n['common']}
    groups = defaultdict(list)
    for m in models:
        _check(cancel)
        variable = {n for n, key in m['_mapping'].items() if key not in core}
        for nodes in _components(variable, m['arcs']):
            f = fragment(m, nodes)
            groups[(tuple(f['entries']), tuple(f['exits']))].append(f)
    blocks, nodes, edges = [], [n for n in overlay['nodes'] if n['id'] in core], [e for e in overlay['edges'] if e['common'] and e['source'] in core and e['target'] in core]
    for interface, fragments in sorted(groups.items()):
        key = 'block-' + digest(interface)[:24]
        mids = sorted({f['model_id'] for f in fragments})
        counts = Counter(f['model_id'] for f in fragments)
        block = {'id': key, 'label': f'Bloque variable {len(blocks) + 1}', 'entries': list(interface[0]), 'exits': list(interface[1]),
                 'alternatives': alternatives(fragments, by_id, total), 'model_ids': mids, 'support': len(mids),
                 'missing_model_ids': sorted(set(by_id) - set(mids)), 'multiple_occurrences': any(v > 1 for v in counts.values())}
        blocks.append(block)
        nodes.append({'id': key, 'kind': 'block', 'label': block['label'], 'support': len(mids), 'common': False,
                      'model_ids': mids, 'sources': {}, 'matching': 'verified_interface'})
        for direction, boundary in [('in', interface[0]), ('out', interface[1])]:
            for endpoint in boundary:
                source, target = (endpoint, key) if direction == 'in' else (key, endpoint)
                # These are abstract interface links, not executable Petri arcs.
                edges.append({'id': 'link-' + digest([source, target])[:24], 'source': source, 'target': target,
                              'kind': 'interface', 'model_ids': mids, 'support': len(mids), 'common': False, 'sources': {}})
    # Common endpoints can be linked variably with no variable node between them.
    edges.extend({**e, 'kind': 'variable_connection'} for e in overlay['edges'] if not e['common'] and e['source'] in core and e['target'] in core)
    return {'nodes': nodes, 'edges': edges, 'blocks': blocks, 'common_core_empty': not core,
            'common_definition': 'present_in_every_population_individual'}


def analyze(models, cancel=None, progress=None, representation='petri'):
    if representation not in REPRESENTATIONS:
        raise ValueError('Representación desconocida: usa petri o bpmn.')
    started = time.perf_counter()
    originals = models
    if representation == 'bpmn':
        from .bpmn import convert_model
        if progress:
            progress('Conversión BPMN')
        models = [convert_model(m, cancel) for m in originals]
    if progress:
        progress('Correspondencias estructurales')
    overlay = align(models, cancel)
    overlay['activities'] = activity_projection(models, overlay, cancel)
    if progress:
        progress('Regiones con interfaces compartidas')
    variation = variation_regions(models, cancel)
    if progress:
        progress('Plantilla común y variable')
    template = common_template(models, overlay, cancel)
    manifest = [{k: m.get(k) for k in ('model_id', 'display_name', 'solution_id', 'evaluation_id', 'import_provenance',
                 'metrics', 'metrics_status', 'pipeline', 'pipeline_full', 'is_feasible', 'is_pareto', 'pnml_sha256', 'logical_attempt_id')}
                | {'places': len(m['places']), 'transitions': len(m['transitions']), 'invisible_transitions': sum(t['invisible'] for t in m['transitions']), 'arcs': len(m['arcs'])} for m in originals]
    derived = {}
    if representation == 'bpmn':
        from .bpmn import source_graph
        derived = {m['model_id']: source_graph(m) for m in models}
    return {'version': VERSION, 'representation': representation, 'population_size': len(models), 'models': manifest, 'references': REFERENCES,
            'derived_models': derived,
            'views': {'merging': overlay, 'variation': variation, 'template': template},
            'statistics': {'analysis_seconds': time.perf_counter() - started, 'merged_nodes': len(overlay['nodes']),
                           'merged_arcs': len(overlay['edges']), 'ambiguous_original_nodes': sum(len(m['_ambiguous']) for m in models),
                           'common_nodes': sum(n['common'] for n in overlay['nodes']), 'common_arcs': sum(e['common'] for e in overlay['edges']),
                           'variation_regions': len(variation['regions']), 'variation_depth': variation['max_depth'],
                           'template_blocks': len(template['blocks'])},
            'limitations': ['Comparación estructural; no demuestra equivalencia conductual.',
                            'La superposición y la plantilla son representaciones, no redes ejecutables.',
                            'Regiones con fronteras compartidas verificadas; enumeración conservadora sobre grafos Petri, sin equivalencia conductual.',
                            'Los elementos ambiguos permanecen separados y trazables.']}
