"""Exact local structure comparison, independent of outside routing contexts.

VF2 matches typed directed graphs, fixed boundary identities, visible labels,
invisibility and arc-weight multisets. This does not compare execution behavior.
The state budget is deterministic; an interrupted comparison is unknown, never
evidence that two fragments differ.
"""
from collections import Counter, defaultdict

import networkx as nx

from .analysis import _check, digest, is_activity

MAX_MATCH_STATES = 10000


class ComparisonLimit(RuntimeError):
    pass


def comparison_graph(model, fragment, full_markings=False):
    used = set(fragment['node_ids'] + fragment['entry_ids'] + fragment['exit_ids'])
    boundary = set(fragment['entries'] + fragment['exits'])
    initial = {e['place_id']: e['tokens'] for e in model['initial_marking']} if full_markings else {}
    graph = nx.DiGraph()
    for nid in sorted(used):
        node = model['_nodes'][nid]
        attrs = (node['kind'], node.get('invisible', False),
                 node.get('label') if is_activity(node) else '',
                 model['_mapping'][nid] if model['_mapping'][nid] in boundary else '', initial.get(nid, 0),
                 node.get('gateway_direction', ''))
        graph.add_node(nid, signature=attrs)
    weights = defaultdict(list)
    ids = set(fragment['arc_ids'])
    for arc in model['arcs']:
        if arc['id'] in ids: weights[(arc['source'], arc['target'])].append(arc.get('weight', 1))
    for (source, target), values in sorted(weights.items()): graph.add_edge(source, target, weights=tuple(sorted(values)))
    if full_markings:
        # Private comparison annotations, not Petri nodes or generated PNML.
        # Separate marker nodes preserve correlations between places in each
        # alternative final marking; empty markings remain explicit.
        finals = sorted({tuple(sorted((e['place_id'], e['tokens']) for e in marking)) for marking in model['final_markings']})
        for number, marking in enumerate(finals):
            marker = ('final-marking', number)
            graph.add_node(marker, signature=('final_marking_annotation', False, '', '', 0))
            for pid, tokens in marking: graph.add_edge(marker, pid, weights=(tokens,))
    return graph


def fingerprint(graph):
    colors = {n: digest(a['signature']) for n, a in graph.nodes(data=True)}
    for _ in range(min(6, len(graph))):
        colors = {n: digest([a['signature'], sorted(('in', graph[p][n]['weights'], colors[p]) for p in graph.predecessors(n)),
                            sorted(('out', graph[n][t]['weights'], colors[t]) for t in graph.successors(n))]) for n, a in graph.nodes(data=True)}
    return digest([sorted(Counter(colors.values()).items()), sorted((colors[s], colors[t], a['weights']) for s, t, a in graph.edges(data=True))])


def same_structure(first, second, cancel=None, max_states=MAX_MATCH_STATES):
    class BoundedMatcher(nx.algorithms.isomorphism.DiGraphMatcher):
        checks = 0
        def syntactic_feasibility(self, n1, n2):
            _check(cancel)
            self.checks += 1
            if self.checks > max_states: raise ComparisonLimit()
            return super().syntactic_feasibility(n1, n2)
    matcher = BoundedMatcher(first, second, node_match=lambda a, b: a['signature'] == b['signature'],
                             edge_match=lambda a, b: a['weights'] == b['weights'])
    try:
        return matcher.is_isomorphic()
    except (ComparisonLimit, RecursionError):
        return None
    finally:
        matcher.reset_recursion_limit()


def structural_alternatives(fragments, models, total, cancel=None, full_markings=False):
    groups, unknown = [], []
    for f in sorted(fragments, key=lambda f: (f['model_id'], f['arc_ids'])):
        _check(cancel)
        model = models[f['model_id']]
        graph = comparison_graph(model, f, full_markings)
        key = fingerprint(graph)
        found = None
        for group in groups:
            if group['_fingerprint'] != key: continue
            answer = same_structure(graph, group['_graph'], cancel)
            if answer:
                found = group; break
            if answer is None: unknown.append([f['model_id'], group['model_ids'][0]])
        if found is None:
            selected = set(f['node_ids'])
            found = {'id': 'alt-local-' + key[:20] + '-' + str(sum(g['_fingerprint'] == key for g in groups)),
                     'sources': [], 'model_ids': [], 'structural_status': 'exact_typed_local_isomorphism',
                     'visible_activities': sorted({model['_nodes'][n].get('label') or '' for n in selected
                                                  if is_activity(model['_nodes'][n])}),
                     'node_count': len(selected), 'arc_count': len(f['arc_ids']),
                     'invisible_transitions': sum(model['_nodes'][n].get('invisible', False) for n in selected),
                     '_fingerprint': key, '_graph': graph}
            groups.append(found)
        found['sources'].append(f); found['model_ids'].append(f['model_id'])
    for group in groups:
        group.pop('_graph'); group.pop('_fingerprint')
        group['model_ids'] = sorted(set(group['model_ids']))
        group['support'] = len(group['model_ids']); group['common'] = group['support'] == total
        if unknown: group['structural_status'] = 'comparison_incomplete'
    return sorted(groups, key=lambda g: (-g['support'], g['id'])), {
        'status': 'verified' if not unknown else 'unresolved', 'unknown_pairs': unknown, 'max_match_states': MAX_MATCH_STATES,
        'method': 'typed_directed_isomorphism_fixed_boundaries_weights_markings'}
