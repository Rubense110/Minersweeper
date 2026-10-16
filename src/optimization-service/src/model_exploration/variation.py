"""Validated edge regions on the annotated Petri overlay.

Assy et al. (2017), Definitions 3--5: local/shared boundary, shared entry/exit.
This uses existing typed nets, not mined causal graphs. Marking-bearing places
are protected process endpoints. Candidate enumeration is conservative: cut all
nodes of each exact incident-model set, then merge validated adjacent fragments.
It is not an exhaustive enumeration of every maximal SHESHE.
"""
from collections import Counter, defaultdict

from .analysis import _check, _components, alternatives, digest, fragment, is_activity
from .structure import structural_alternatives


class RegionIndex:
    def __init__(self, models):
        self.models = {m['model_id']: m for m in models}
        self.arcs = {mid: {a['id']: a for a in m['arcs']} for mid, m in self.models.items()}
        self.incident = defaultdict(lambda: {'in': defaultdict(set), 'out': defaultdict(set)})
        self.protected = set()
        for mid, m in self.models.items():
            for marking in [m['initial_marking'], *m['final_markings']]:
                self.protected.update(m['_mapping'][e['place_id']] for e in marking)
            for a in m['arcs']:
                self.incident[m['_mapping'][a['source']]]['out'][mid].add(a['id'])
                self.incident[m['_mapping'][a['target']]]['in'][mid].add(a['id'])
        self.members = {key: frozenset(set(d['in']) | set(d['out'])) for key, d in self.incident.items()}

    def boundary_details(self, keys):
        details = {}
        place_number = invisible_number = 0
        for key in sorted(keys):
            sources, before, after = {}, set(), set()
            example = None
            for mid, m in sorted(self.models.items()):
                ids = [nid for nid, mapped in m['_mapping'].items() if mapped == key]
                if not ids: continue
                sources[mid] = ids
                example = m['_nodes'][ids[0]]
                for direction, labels in [('in', before), ('out', after)]:
                    frontier = set(ids)
                    for _ in range(2):
                        next_nodes = set()
                        for a in m['arcs']:
                            current, other = (a['target'], a['source']) if direction == 'in' else (a['source'], a['target'])
                            if current not in frontier: continue
                            node = m['_nodes'][other]
                            if is_activity(node):
                                labels.add(node.get('label') or '')
                            else: next_nodes.add(other)
                        frontier = next_nodes
            if example['kind'] == 'place':
                place_number += 1; label = f'P{place_number}'
            elif example.get('invisible'):
                invisible_number += 1; label = f'τ{invisible_number}'
            elif 'gateway' in example['kind']:
                invisible_number += 1; label = f'{example.get("label", "◇")}{invisible_number}'
            else: label = example.get('label') or key
            context = ('después de ' + ', '.join(sorted(before))) if before else ('hacia ' + ', '.join(sorted(after))) if after else ''
            details[key] = {'label': label, 'description': f'{label} · {context}' if context else label,
                            'kind': example['kind'], 'invisible': example.get('invisible', False),
                            'before_activities': sorted(before), 'after_activities': sorted(after), 'sources': sources}
        return details

    def validate(self, selected, cancel=None):
        """Validate globally, including arcs from models outside this candidate.

        selected = {model_id: set(original_arc_ids)}. No union-graph walks can
        satisfy the per-original reachability checks.
        """
        members = set(selected)
        if len(members) < 2 or any(not ids for ids in selected.values()):
            return None, 'insufficient_participation'
        inside = defaultdict(lambda: {'in': set(), 'out': set()})
        adjacency = defaultdict(set)
        for mid, ids in sorted(selected.items()):
            _check(cancel)
            m = self.models[mid]
            for aid in sorted(ids):
                a = self.arcs[mid][aid]
                s, t = m['_mapping'][a['source']], m['_mapping'][a['target']]
                inside[s]['out'].add(mid); inside[t]['in'].add(mid)
                adjacency[s].add(t); adjacency[t].add(s)
        if self.protected.intersection(inside):
            return None, 'process_marking_boundary'
        reached, todo = set(), [min(inside)]
        while todo:
            key = todo.pop()
            if key not in reached:
                reached.add(key); todo.extend(adjacency[key] - reached)
        if reached != set(inside):
            return None, 'disconnected_region'
        entries, exits, local = set(), set(), set()
        for key, directions in sorted(inside.items()):
            outside = {direction: {mid for mid, ids in self.incident[key][direction].items()
                                   if ids - selected.get(mid, set())} for direction in ('in', 'out')}
            if not outside['in'] and not outside['out']:
                local.add(key)
                continue
            if set(self.members[key]) != members:
                return None, 'boundary_model_set'
            # Definition 4 permits a boundary to be both entry and exit, but
            # requires matching inside/outside directions in every participant.
            entry = outside['in'] == directions['out'] == members and (
                not (outside['out'] & directions['in']) or outside['out'] == directions['in'] == members)
            exit = outside['out'] == directions['in'] == members and (
                not (outside['in'] & directions['out']) or outside['in'] == directions['out'] == members)
            if not entry and not exit:
                return None, 'boundary_direction'
            if entry: entries.add(key)
            if exit: exits.add(key)
        if not entries or not exits:
            return None, 'missing_entry_or_exit'
        sources = []
        for mid, ids in sorted(selected.items()):
            _check(cancel)
            m = self.models[mid]
            used = set()
            forward, backward = defaultdict(set), defaultdict(set)
            for aid in ids:
                a = self.arcs[mid][aid]
                used.update((a['source'], a['target']))
                forward[a['source']].add(a['target']); backward[a['target']].add(a['source'])
            incoming = {nid for nid in used if m['_mapping'][nid] in entries}
            outgoing = {nid for nid in used if m['_mapping'][nid] in exits}
            def reachable(seeds, links):
                seen, todo = set(), list(seeds)
                while todo:
                    nid = todo.pop()
                    if nid not in seen:
                        seen.add(nid); todo.extend(links[nid] - seen)
                return seen
            if used != reachable(incoming, forward) or used != reachable(outgoing, backward):
                return None, 'not_on_directed_entry_exit_routes'
            interior = {nid for nid in used if m['_mapping'][nid] in local}
            sources.append({'model_id': mid, 'node_ids': sorted(interior), 'arc_ids': sorted(ids),
                            'entry_ids': sorted(incoming), 'exit_ids': sorted(outgoing),
                            'boundary_mapping': {nid: m['_mapping'][nid] for nid in sorted(incoming | outgoing)},
                            'entries': sorted(entries), 'exits': sorted(exits)})
        return {'sources': sources, 'entries': sorted(entries), 'exits': sorted(exits),
                'model_ids': sorted(members), 'edges': frozenset((mid, aid) for mid, ids in selected.items() for aid in ids),
                'nodes': frozenset(inside), 'scope': 'local',
                'validation': {'shared_boundary_model_sets': True, 'shared_entry_exit_directions': True,
                               'every_original_on_directed_entry_exit_routes': True, 'process_markings_excluded': True}}, None


def detect_regions(models, cancel=None):
    index = RegionIndex(models)
    total, rejected = len(models), Counter()
    candidates = {}
    for members in sorted({s for s in index.members.values() if len(s) >= 2}, key=lambda s: (len(s), sorted(s))):
        _check(cancel)
        boundaries = {key for key, mids in index.members.items() if mids == members}
        groups, direct = defaultdict(list), defaultdict(lambda: defaultdict(set))
        for mid in sorted(members):
            m = index.models[mid]
            inner = {nid for nid in m['_nodes'] if m['_mapping'][nid] not in boundaries}
            for component in _components(inner, m['arcs']):
                f = fragment(m, component)
                if f['arc_ids']:
                    groups[(tuple(f['entries']), tuple(f['exits']))].append(f)
            for a in m['arcs']:
                s, t = m['_mapping'][a['source']], m['_mapping'][a['target']]
                if s in boundaries and t in boundaries:
                    direct[(s, t)][mid].add(a['id'])
        selections = []
        for fragments in groups.values():
            mids = [f['model_id'] for f in fragments]
            if set(mids) != set(members) or len(mids) != len(set(mids)):
                rejected['incomplete_or_multiple_occurrences'] += 1
                continue
            selections.append({f['model_id']: set(f['arc_ids']) for f in fragments})
        selections.extend(dict(selection) for selection in direct.values() if set(selection) == set(members))
        for selection in selections:
            region, reason = index.validate(selection, cancel)
            if region is None:
                rejected[reason] += 1
            else:
                candidates[region['edges']] = region

    # Maximal within the enumerated candidate family, not maximality over every
    # possible edge subset. Validate every union rather than assuming a theorem
    # transfers unchanged from causal graphs to typed Petri input.
    changed = True
    while changed:
        changed = False
        ordered = sorted(candidates.values(), key=lambda r: sorted(r['edges']))
        for i, first in enumerate(ordered):
            for second in ordered[i + 1:]:
                _check(cancel)
                if first['model_ids'] != second['model_ids'] or not first['nodes'].intersection(second['nodes']):
                    continue
                selected = defaultdict(set)
                for mid, aid in first['edges'] | second['edges']: selected[mid].add(aid)
                union, reason = index.validate(dict(selected), cancel)
                if union is None:
                    continue
                candidates.pop(first['edges'], None); candidates.pop(second['edges'], None)
                candidates[union['edges']] = union
                changed = True
                break
            if changed: break

    root_sources = [fragment(m, m['_nodes']) for m in models]
    root_alternatives, root_comparison = structural_alternatives(root_sources, index.models, total, cancel, full_markings=True)
    root = {'id': 'vp-root-' + digest(sorted(index.models))[:20], 'parent_id': None, 'depth': 0,
            'label': 'Población completa', 'entries': [], 'exits': [], 'model_ids': sorted(index.models), 'support': total,
            'alternatives': root_alternatives, 'comparison': root_comparison, 'children': [], 'scope': 'global',
            'is_variation_point': False, 'interface_status': 'whole_models', 'decomposition_status': 'validated_edge_regions'}
    regions, accepted, extra = [root], [], []
    for candidate in sorted(candidates.values(), key=lambda r: (-len(r['edges']), sorted(r['edges']))):
        _check(cancel)
        alts, comparison = structural_alternatives(candidate['sources'], index.models, total, cancel)
        item = {k: candidate[k] for k in ('entries', 'exits', 'model_ids', 'scope', 'validation')}
        item.update(id='vp-' + digest(sorted(candidate['edges']))[:24], support=len(candidate['model_ids']),
                    alternatives=alts, comparison=comparison, children=[], is_variation_point=len(alts) > 1 and comparison['status'] == 'verified',
                    interface_status='validated_shared_entry_exit', decomposition_status='validated_edge_regions')
        crossing = [r for r in accepted if candidate['edges'] & r['_edges'] and not candidate['edges'] <= r['_edges']]
        if crossing:
            item.update(parent_id=root['id'], depth=1, label=f'Región adicional {len(extra) + 1}',
                        hierarchy_status='crossing_candidate', overlapping_region_ids=[r['id'] for r in crossing])
            extra.append(item)
            continue
        parents = [r for r in accepted if candidate['edges'] < r['_edges']]
        parent = min(parents, key=lambda r: (len(r['_edges']), r['id'])) if parents else root
        item.update(parent_id=parent['id'], depth=parent['depth'] + 1, label=f'Región {len(accepted) + 1}', _edges=candidate['edges'])
        parent['children'].append(item['id']); accepted.append(item); regions.append(item)
    for r in accepted: r.pop('_edges')
    boundaries = {key for r in [*regions, *extra] for key in r['entries'] + r['exits']}
    return {'regions': regions, 'additional_regions': extra, 'boundary_details': index.boundary_details(boundaries), 'max_depth': max(r['depth'] for r in regions),
            'depth_limit': None, 'unencapsulated_candidate_fragments': sum(rejected.values()),
            'rejected_candidates': dict(sorted(rejected.items())),
            'detection': 'validated_typed_shared_entry_exit_regions',
            'candidate_policy': 'exact_incident_model_sets; all_shared_node_cuts; validated_adjacent_unions',
            'maximality': 'within_enumerated_candidate_family; not_exhaustive',
            'variation_points': sum(r['is_variation_point'] for r in regions) + sum(r['is_variation_point'] for r in extra)}
