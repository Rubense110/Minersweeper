import copy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from job_store import JobStore, ModelArtifact
from model_exploration.analysis import analyze, prepare_models, digest, fragment
from model_exploration.importing import import_export, archive_files
from model_exploration.service import ExplorationService, ExplorationBusy
from model_exploration.variation import RegionIndex
from model_exploration.structure import structural_alternatives, comparison_graph, same_structure
from api.serialization import _build_experiment_export_archive


def source(sid, labels=('A', 'B'), invisible=False, weight=1, finals=None):
    places = [{'id': f'p{i}', 'label': f'p{i}'} for i in range(len(labels) + 1)]
    transitions = [{'id': f't{i}', 'label': label, 'invisible': invisible and i == 0} for i, label in enumerate(labels)]
    arcs = []
    for i in range(len(labels)):
        arcs.extend([{'id': f'a{i}i', 'source': f'p{i}', 'target': f't{i}', 'weight': weight},
                     {'id': f'a{i}o', 'source': f't{i}', 'target': f'p{i+1}', 'weight': weight}])
    initial = [{'place_id': 'p0', 'tokens': weight}]
    finals = finals or [[{'place_id': f'p{len(labels)}', 'tokens': weight}]]
    row = {'solution_id': sid, 'experiment_id': 'original-exp', 'evaluation_id': f'e-{sid}',
           'places': places, 'transitions': transitions, 'arcs': arcs, 'initial_marking': initial,
           'final_marking': finals[0], 'final_markings': finals, 'model_schema_version': 2,
           'visible_transition_count': sum(not t['invisible'] for t in transitions), 'is_feasible': True,
           'constraint_violations': [], 'metrics': {'fitness': .9, 'precision': .8}, 'metrics_status': 'computed', 'is_pareto': True}
    metadata = {k: row[k] for k in ('evaluation_id', 'model_schema_version', 'transitions', 'initial_marking', 'final_marking', 'final_markings', 'visible_transition_count', 'is_feasible', 'constraint_violations', 'metrics_status')}
    pnml = '<pnml><net id="n"><page id="page">' + ''.join(f'<place id="{p["id"]}"/>' for p in places)
    pnml += ''.join(f'<transition id="{t["id"]}"/>' for t in transitions)
    pnml += ''.join(f'<arc id="{a["id"]}" source="{a["source"]}" target="{a["target"]}"><inscription><text>{a["weight"]}</text></inscription></arc>' for a in arcs)
    pnml += '</page></net></pnml>\n'
    row['original_pnml'] = pnml
    row['original_metadata'] = metadata
    return row


def data():
    now = datetime.now(timezone.utc)
    return {'experiment_id': 'original-exp', 'experiment_name': 'Test', 'start_at': now, 'end_at': now,
            'max_evals': 100, 'pop_size': 3, 'workers': 1, 'log_path': 'log.xes'}


def models(rows):
    return prepare_models(rows, {r['evaluation_id']: {'pnml': r['original_pnml'], 'metadata': r['original_metadata']} for r in rows})


def reseal(row):
    """Rebuild test source bytes after mutating a graph; never production PNML."""
    row['visible_transition_count'] = sum(not t['invisible'] for t in row['transitions'])
    row['original_metadata'].update({k: row[k] for k in ('transitions', 'initial_marking', 'final_marking', 'final_markings', 'visible_transition_count')})
    row['original_pnml'] = '<pnml><net id="n"><page id="page">' + ''.join(f'<place id="{p["id"]}"/>' for p in row['places'])
    row['original_pnml'] += ''.join(f'<transition id="{t["id"]}"/>' for t in row['transitions'])
    row['original_pnml'] += ''.join(f'<arc id="{a["id"]}" source="{a["source"]}" target="{a["target"]}"><inscription><text>{a.get("weight",1)}</text></inscription></arc>' for a in row['arcs'])
    row['original_pnml'] += '</page></net></pnml>'
    return row


class ExplorationTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = JobStore('sqlite:///' + self.directory.name + '/test.db')
    def tearDown(self):
        self.store.engine.dispose()
        self.directory.cleanup()

    def test_export_import_preserves_original_bytes_all_individuals_and_markings(self):
        row = source(1, ('not-a-tau-label', 'B'), True, 2, [[], [{'place_id': 'p2', 'tokens': 2}]])
        duplicate = {**row, 'solution_id': 2}
        self.store.save_completed_experiment(data(), [row, duplicate])
        stored = self.store.get_experiment_solutions('original-exp')
        self.assertEqual(2, len(stored))
        self.assertTrue(all(r['original_pnml_available'] for r in stored))
        self.assertNotIn('original_pnml', stored[0])
        with self.store._session_factory() as session:
            self.assertEqual(1, session.query(ModelArtifact).count())
        originals = self.store.get_original_artifacts('original-exp')
        archive, _ = _build_experiment_export_archive(self.store.get_experiment('original-exp'), stored, [], originals)
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            pnml = z.read('models/e-1.pnml')
            self.assertEqual(row['original_pnml'].encode(), pnml)
            manifest = json.loads(z.read('models/index.json'))['models']
            self.assertEqual(hashlib.sha256(pnml).hexdigest(), manifest[0]['pnml_sha256'])
            exported = list(csv.DictReader(io.StringIO(z.read('solutions.csv').decode())))
            self.assertEqual('computed', exported[0]['metrics_status'])
        eid = import_export(self.store, archive)
        imported = self.store.get_experiment_solutions(eid)
        self.assertEqual(2, len(imported))
        self.assertEqual(row['final_markings'], imported[0]['final_markings'])
        self.assertTrue(imported[0]['transitions'][0]['invisible'])
        self.assertTrue(imported[0]['is_feasible'])
        self.assertTrue(imported[0]['is_pareto'])
        self.assertEqual(stored[0]['solution_id'], imported[0]['import_provenance']['solution_id'])
        self.assertEqual(row['original_pnml'], self.store.get_original_artifacts(eid)['e-1']['pnml'])

    def test_historical_import_requires_originals_and_rejects_mismatches(self):
        rows = [source(1)]
        archive, _ = _build_experiment_export_archive(data(), rows, [])
        with self.assertRaisesRegex(ValueError, 'Falta el PNML'):
            import_export(self.store, archive)
        supplementary = {'e-1.pnml': rows[0]['original_pnml'].encode(), 'e-1.json': json.dumps(rows[0]['original_metadata']).encode()}
        self.assertEqual(1, len(self.store.get_experiment_solutions(import_export(self.store, archive, supplementary))))
        supplementary['e-1.pnml'] = supplementary['e-1.pnml'].replace(b'<text>1</text>', b'<text>3</text>')
        with self.assertRaisesRegex(ValueError, 'difieren'):
            import_export(self.store, archive, supplementary)

    def test_unsafe_and_duplicate_archive_paths_are_rejected(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w') as z:
            z.writestr('../escape.pnml', 'x')
        with self.assertRaises(ValueError):
            archive_files(content.getvalue())

    def test_provenance_recovers_every_node_and_arc_without_dedup(self):
        rows = [source(1), source(2), source(3, ('B', 'A'))]
        result = analyze(models(rows))
        self.assertEqual(3, result['population_size'])
        self.assertEqual(2, sum(n['common'] and n['kind'] == 'transition' for n in result['views']['merging']['nodes']))
        for row in rows:
            mid = f"m-{row['solution_id']}"
            nodes = [original for n in result['views']['merging']['nodes'] for original in n['sources'].get(mid, [])]
            arcs = [original for a in result['views']['merging']['edges'] for original in a['sources'].get(mid, [])]
            self.assertCountEqual([n['id'] for n in row['places'] + row['transitions']], nodes)
            self.assertCountEqual([a['id'] for a in row['arcs']], arcs)
        root = result['views']['variation']['regions'][0]
        self.assertEqual([1, 2], sorted(a['support'] for a in root['alternatives']))
        self.assertTrue(any(n['context_varies'] for n in result['views']['merging']['nodes'] if n['kind'] == 'transition'))

    def test_input_order_does_not_change_views_and_marks_remain_separate(self):
        rows = [source(1), source(2, ('A', 'C')), source(3, ('B', 'A'), weight=2)]
        first, second = analyze(models(rows)), analyze(models(list(reversed(rows))))
        self.assertEqual(first['views'], second['views'])
        self.assertEqual(first['models'], second['models'])
        self.assertTrue(any(a.get('weight') == 2 for a in first['views']['merging']['edges']))

    def test_activity_paths_have_real_ordered_witnesses_and_stop_at_visible_activity(self):
        prepared = models([source(1, ('A', 'B', 'C')), source(2, ('A', 'B', 'C'))])
        result = analyze(prepared)
        graph = result['views']['merging']['activities']
        labels = {n['id']: n['label'] for n in graph['nodes']}
        self.assertEqual({('A', 'B'), ('B', 'C')}, {(labels[e['source']], labels[e['target']]) for e in graph['edges']})
        for edge in graph['edges']:
            self.assertEqual(2, edge['support'])
            for f in edge['sources']:
                m = next(m for m in prepared if m['model_id'] == f['model_id'])
                arcs = {a['id']: a for a in m['arcs']}
                path = [arcs[aid] for aid in f['arc_ids']]
                self.assertEqual(edge['source'], m['_mapping'][path[0]['source']])
                self.assertEqual(edge['target'], m['_mapping'][path[-1]['target']])
                for a, b in zip(path, path[1:]):
                    self.assertEqual(a['target'], b['source'])
                    n = m['_nodes'][a['target']]
                    self.assertTrue(n['kind'] == 'place' or n['invisible'])

    def test_activity_projection_does_not_recombine_models_and_handles_invisible_cycles(self):
        # The union has A→X→B, but X is visible: no original A→B path.
        result = analyze(models([source(1, ('A', 'X')), source(2, ('X', 'B'))]))
        graph = result['views']['merging']['activities']
        labels = {n['id']: n['label'] for n in graph['nodes']}
        self.assertNotIn(('A', 'B'), {(labels[e['source']], labels[e['target']]) for e in graph['edges']})
        row = source(3, ('A', 'route', 'B'))
        row['transitions'][1]['invisible'] = True
        row['arcs'].append({'id': 'cycle', 'source': 't1', 'target': 'p1', 'weight': 1})
        row['arcs'].append({'id': 'self-loop', 'source': 't0', 'target': 'p0', 'weight': 1})
        row['visible_transition_count'] = 2
        row['original_metadata'].update(transitions=row['transitions'], visible_transition_count=2)
        row['original_pnml'] = row['original_pnml'].replace('</page>', '<arc id="cycle" source="t1" target="p1"/><arc id="self-loop" source="t0" target="p0"/></page>')
        graph = analyze(models([row]))['views']['merging']['activities']
        labels = {n['id']: n['label'] for n in graph['nodes']}
        self.assertEqual({('A', 'A'), ('A', 'B')}, {(labels[e['source']], labels[e['target']]) for e in graph['edges']})
        self.assertTrue(any('t1' in f['node_ids'] for e in graph['edges'] for f in e['sources']))

    def test_empty_common_core_and_repeated_activity_are_supported(self):
        result = analyze(models([source(1, ('A',)), source(2, ('B',))]))
        # Places may align only if their structural contexts agree: these do not.
        self.assertTrue(result['views']['template']['common_core_empty'])
        repeated = analyze(models([source(1, ('A', 'A')), source(2, ('A', 'A'))]))
        for mid in ('m-1', 'm-2'):
            original_ids = [nid for n in repeated['views']['merging']['nodes'] for nid in n['sources'].get(mid, [])]
            self.assertEqual(len(original_ids), len(set(original_ids)))

    def test_symmetric_routing_is_marked_ambiguous_not_arbitrarily_merged(self):
        row = source(1)
        row['places'].append({'id': 'isolated-1', 'label': ''})
        row['places'].append({'id': 'isolated-2', 'label': ''})
        row['original_pnml'] = row['original_pnml'].replace('</page>', '<place id="isolated-1"/><place id="isolated-2"/></page>')
        result = analyze(models([row]))
        self.assertEqual(2, result['statistics']['ambiguous_original_nodes'])
        self.assertEqual(2, sum(n['matching'] == 'ambiguous' for n in result['views']['merging']['nodes']))

    def test_region_interfaces_include_every_crossing_arc_and_children_are_nested(self):
        prepared = models([source(1, ('A', 'B', 'C')), source(2, ('A', 'D', 'C')), source(3, ('A', 'B', 'C'))])
        result = analyze(prepared)
        by_mid = {m['model_id']: m for m in prepared}
        regions = {r['id']: r for r in result['views']['variation']['regions']}
        self.assertGreater(len(regions), 1)
        for region in regions.values():
            parent = regions.get(region['parent_id'])
            parents = {f['model_id']: set(f['node_ids']) for a in parent['alternatives'] for f in a['sources']} if parent else {}
            for alt in region['alternatives']:
                for f in alt['sources']:
                    recalculated = fragment(by_mid[f['model_id']], f['node_ids'])
                    self.assertEqual(recalculated, {k: f[k] for k in recalculated})
                    if parent:
                        self.assertLess(set(f['node_ids']), parents[f['model_id']])
                        self.assertEqual(list(region['entries']), f['entries'])
                        self.assertEqual(list(region['exits']), f['exits'])

    def test_local_variation_is_detected_with_global_boundary_checks(self):
        result = analyze(models([source(1, ('A', 'B', 'C')), source(2, ('A', 'D', 'C')), source(3, ('A', 'B', 'C'))]))
        variation = result['views']['variation']
        points = [r for r in variation['regions'] if r['is_variation_point']]
        self.assertEqual(1, len(points))
        self.assertEqual(3, points[0]['support'])
        self.assertEqual(2, len(points[0]['alternatives']))
        lookup = {n['id']: n['label'] for n in result['views']['merging']['nodes']}
        self.assertEqual(['A'], [lookup[n] for n in points[0]['entries']])
        self.assertEqual(['C'], [lookup[n] for n in points[0]['exits']])
        self.assertTrue(all(points[0]['validation'].values()))
        self.assertFalse(variation['regions'][0]['is_variation_point'])

    def test_same_interfaces_in_subset_do_not_satisfy_global_shared_boundary(self):
        prepared = models([source(1, ('A', 'B', 'C')), source(2, ('A', 'D', 'C')), source(3, ('A', 'X', 'C'))])
        analyze(prepared)
        selection = {mid: {'a0o', 'a1i', 'a1o', 'a2i'} for mid in ('m-1', 'm-2')}
        region, reason = RegionIndex(prepared).validate(selection)
        self.assertIsNone(region)
        self.assertEqual('boundary_model_set', reason)

    def test_whole_net_except_one_activity_is_not_a_local_variation_region(self):
        prepared = models([source(1, ('A', 'B', 'C')), source(2, ('A', 'D', 'C'))])
        result = analyze(prepared)
        selection = {m['model_id']: {a['id'] for a in m['arcs']} for m in prepared}
        region, reason = RegionIndex(prepared).validate(selection)
        self.assertIsNone(region)
        self.assertEqual('process_marking_boundary', reason)
        for r in result['views']['variation']['regions'][1:]:
            for alt in r['alternatives']:
                for f in alt['sources']:
                    m = next(m for m in prepared if m['model_id'] == f['model_id'])
                    used = set(f['node_ids'] + f['entry_ids'] + f['exit_ids'])
                    marked = {e['place_id'] for marking in [m['initial_marking'], *m['final_markings']] for e in marking}
                    self.assertFalse(used & marked)

    def test_shared_entry_and_exit_may_be_the_same_activity_for_a_real_local_loop(self):
        rows = [source(1, ('A', 'B', 'C')), source(2, ('A', 'B', 'C'))]
        for row in rows:
            row['places'] += [{'id': 'r1', 'label': ''}, {'id': 'r2', 'label': ''}]
            row['transitions'].append({'id': 'silent', 'label': 'route', 'invisible': True})
            row['arcs'] += [{'id': f'l{i}', 'source': a, 'target': b, 'weight': 1} for i, (a,b) in enumerate([('t0','r1'),('r1','silent'),('silent','r2'),('r2','t0')])]
            reseal(row)
        prepared = models(rows); analyze(prepared)
        region, reason = RegionIndex(prepared).validate({m['model_id']: {f'l{i}' for i in range(4)} for m in prepared})
        self.assertIsNone(reason)
        self.assertEqual(region['entries'], region['exits'])
        self.assertEqual(1, len(region['entries']))
        self.assertTrue(all(region['validation'].values()))

    def test_mixed_entry_exit_role_across_models_is_rejected(self):
        rows = [source(1, ('A', 'B', 'C')), source(2, ('A', 'B', 'C'))]
        for row in rows:
            row['arcs'].append({'id': 'bypass', 'source': 't0', 'target': 'p3', 'weight': 1})
        rows[0]['places'].append({'id': 'return', 'label': ''})
        rows[0]['arcs'] += [{'id': 'return-in', 'source': 't1', 'target': 'return', 'weight': 1}, {'id': 'return-out', 'source': 'return', 'target': 't0', 'weight': 1}]
        prepared = models([reseal(r) for r in rows]); analyze(prepared)
        selection = {'m-1': {'a0o','a1i','a1o','a2i','return-in','return-out'}, 'm-2': {'a0o','a1i','a1o','a2i'}}
        region, reason = RegionIndex(prepared).validate(selection)
        self.assertIsNone(region)
        self.assertEqual('boundary_direction', reason)

    def test_weakly_connected_fragment_with_unreachable_branch_is_rejected(self):
        rows = [source(1, ('A', 'B', 'C')), source(2, ('A', 'B', 'C'))]
        for row in rows:
            row['places'].append({'id': 'dead', 'label': ''})
            row['arcs'].append({'id': 'dead-in', 'source': 'dead', 'target': 't1', 'weight': 1})
        prepared = models([reseal(r) for r in rows]); analyze(prepared)
        region, reason = RegionIndex(prepared).validate({m['model_id']: {'a0o','a1i','a1o','a2i','dead-in'} for m in prepared})
        self.assertIsNone(region)
        self.assertEqual('not_on_directed_entry_exit_routes', reason)

    def test_external_context_colors_do_not_create_false_local_alternatives(self):
        prepared = models([source(1, ('A', 'B', 'C')), source(2, ('A', 'B', 'C'))])
        analyze(prepared)
        for nid in ('p1', 't1', 'p2'):
            prepared[1]['_mapping'][nid] += '-changed-outside-context'
        fragments = [fragment(m, {'p1','t1','p2'}) for m in prepared]
        groups, comparison = structural_alternatives(fragments, {m['model_id']: m for m in prepared}, 2)
        self.assertEqual('verified', comparison['status'])
        self.assertEqual(1, len(groups))
        self.assertEqual(2, groups[0]['support'])
        self.assertEqual(2, len(groups[0]['sources']))

    def test_structural_comparison_limit_is_unknown_not_a_proven_difference(self):
        prepared = models([source(1), source(2)])
        analyze(prepared)
        fragments = [fragment(m, m['_nodes']) for m in prepared]
        first, second = [comparison_graph(m, f) for m, f in zip(prepared, fragments)]
        self.assertIsNone(same_structure(first, second, max_states=0))
        with patch('model_exploration.structure.same_structure', return_value=None):
            groups, comparison = structural_alternatives(fragments, {m['model_id']: m for m in prepared}, 2)
        self.assertEqual('unresolved', comparison['status'])
        self.assertEqual(2, sum(g['support'] for g in groups))
        self.assertTrue(comparison['unknown_pairs'])

    def test_complete_model_comparison_preserves_correlated_final_markings(self):
        finals1 = [[{'place_id':'p0','tokens':1},{'place_id':'p1','tokens':1}], [{'place_id':'p2','tokens':1}]]
        finals2 = [[{'place_id':'p0','tokens':1},{'place_id':'p2','tokens':1}], [{'place_id':'p1','tokens':1}]]
        result = analyze(models([source(1, finals=finals1), source(2, finals=finals2)]))
        self.assertEqual(2, len(result['views']['variation']['regions'][0]['alternatives']))

    def test_cycles_and_choice_parallel_routing_stay_distinct(self):
        sequential = source(1)
        loop = source(2)
        loop['arcs'].append({'id': 'back', 'source': 't1', 'target': 'p0', 'weight': 1})
        loop['original_pnml'] = loop['original_pnml'].replace('</page>', '<arc id="back" source="t1" target="p0"><inscription><text>1</text></inscription></arc></page>')
        result = analyze(models([sequential, loop]))
        self.assertEqual(2, len(result['views']['variation']['regions'][0]['alternatives']))
        self.assertTrue(any('back' in a['sources'].get('m-2', []) for a in result['views']['merging']['edges']))
        choice = source(3)
        choice['arcs'] = [
            {'id': 'a0i', 'source': 'p0', 'target': 't0', 'weight': 1},
            {'id': 'a0o', 'source': 't0', 'target': 'p2', 'weight': 1},
            {'id': 'a1i', 'source': 'p0', 'target': 't1', 'weight': 1},
            {'id': 'a1o', 'source': 't1', 'target': 'p2', 'weight': 1},
        ]
        parallel = source(4)
        parallel['places'] = [{'id': f'p{i}', 'label': ''} for i in range(6)]
        parallel['transitions'] += [{'id': 'split', 'label': 'route', 'invisible': True}, {'id': 'join', 'label': 'route', 'invisible': True}]
        pairs = [('p0','split'),('split','p1'),('split','p2'),('p1','t0'),('p2','t1'),('t0','p3'),('t1','p4'),('p3','join'),('p4','join'),('join','p5')]
        parallel['arcs'] = [{'id': f'e{i}', 'source': a, 'target': b, 'weight': 1} for i, (a,b) in enumerate(pairs)]
        parallel['final_marking'] = [{'place_id': 'p5', 'tokens': 1}]
        parallel['final_markings'] = [parallel['final_marking']]
        for row in (choice, parallel):
            row['original_metadata'].update({k: row[k] for k in ('transitions', 'final_marking', 'final_markings')})
            pnml = '<pnml><net id="n"><page id="page">' + ''.join(f'<place id="{p["id"]}"/>' for p in row['places'])
            pnml += ''.join(f'<transition id="{t["id"]}"/>' for t in row['transitions'])
            pnml += ''.join(f'<arc id="{a["id"]}" source="{a["source"]}" target="{a["target"]}"/>' for a in row['arcs'])
            row['original_pnml'] = pnml + '</page></net></pnml>'
        result = analyze(models([choice, parallel]))
        self.assertEqual(2, len(result['views']['variation']['regions'][0]['alternatives']))
        self.assertEqual(2, sum(n['common'] and n['kind'] == 'transition' for n in result['views']['merging']['nodes']))

    def test_marking_changes_are_not_consolidated_as_same_structure(self):
        rows = [source(1), source(2)]
        rows[1]['initial_marking'] = [{'place_id': 'p1', 'tokens': 1}]
        rows[1]['original_metadata']['initial_marking'] = rows[1]['initial_marking']
        result = analyze(models(rows))
        self.assertEqual(2, len(result['views']['variation']['regions'][0]['alternatives']))

    def test_analysis_cancel_checks_and_worker_releases_capacity(self):
        prepared = models([source(1)])
        with self.assertRaises(InterruptedError):
            analyze(prepared, cancel=lambda: True)
        self.store.save_completed_experiment(data(), [source(1)])
        service = ExplorationService(self.store)
        def blocked(models, cancel, progress):
            while not cancel():
                time.sleep(.01)
            raise InterruptedError('cancelled')
        with patch('model_exploration.service.analyze', blocked):
            first = service.start('original-exp')
            self.assertEqual(first['exploration_id'], service.start('original-exp')['exploration_id'])
            self.assertEqual('cancelling', service.cancel(first['exploration_id'])['status'])
            deadline = time.monotonic() + 3
            while service.get(first['exploration_id'])['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertEqual('cancelled', service.get(first['exploration_id'])['status'])
        self.store.delete_experiment('original-exp')
        with self.assertRaises(KeyError):
            service.get(first['exploration_id'])

    def test_api_import_views_source_download_and_cache(self):
        import api
        from api.manager import OptimizationJobManager
        previous = api.get_manager()
        manager = OptimizationJobManager('http://unused', 'sqlite:///' + self.directory.name + '/api.db', 10)
        api.set_manager(manager)
        try:
            rows = [source(1), source(2, ('A', 'C'))]
            originals = {r['evaluation_id']: {'pnml': r['original_pnml'], 'metadata': r['original_metadata']} for r in rows}
            archive, _ = _build_experiment_export_archive(data(), rows, [], originals)
            client = api.app.test_client()
            response = client.post('/explorations/import', data={'archive': (io.BytesIO(archive), 'export.zip')})
            self.assertEqual(201, response.status_code, response.json)
            eid = response.json['experiment_id']
            response = client.post(f'/experiments/{eid}/explorations')
            self.assertEqual(202, response.status_code, response.json)
            aid = response.json['exploration_id']
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                status = client.get(f'/explorations/{aid}').json
                if status['status'] != 'running':
                    break
                time.sleep(.01)
            self.assertEqual('completed', status['status'], status)
            self.assertEqual(2, status['population_size'])
            self.assertNotIn('views', status)
            for kind in ('merging', 'variation', 'template'):
                self.assertEqual(200, client.get(f'/explorations/{aid}/views/{kind}').status_code)
            mid = status['models'][0]['model_id']
            original = client.get(f'/explorations/{aid}/models/{mid}/pnml')
            self.assertEqual(rows[0]['original_pnml'].encode(), original.data)
            self.assertEqual(200, client.get(f'/explorations/{aid}/models/{mid}').status_code)
            self.assertEqual(404, client.get(f'/explorations/{aid}/models/unknown').status_code)
            self.assertEqual(aid, client.post(f'/experiments/{eid}/explorations').json['exploration_id'])
        finally:
            api.set_manager(previous)
            manager.job_store.engine.dispose()


if __name__ == '__main__':
    unittest.main()
