import copy
import time
import unittest

import test_model_exploration as fixtures
from test_model_exploration import models, reseal, source, data
from model_exploration.analysis import analyze
from model_exploration.bpmn import convert_model, source_graph


def parallel(sid):
    row = source(sid)
    row['places'] = [{'id': f'p{i}', 'label': ''} for i in range(6)]
    row['transitions'] += [{'id': 'split', 'label': 'routing', 'invisible': True},
                           {'id': 'join', 'label': 'routing', 'invisible': True}]
    pairs = [('p0', 'split'), ('split', 'p1'), ('split', 'p2'), ('p1', 't0'), ('p2', 't1'),
             ('t0', 'p3'), ('t1', 'p4'), ('p3', 'join'), ('p4', 'join'), ('join', 'p5')]
    row['arcs'] = [{'id': f'a{i}', 'source': s, 'target': t, 'weight': 1} for i, (s, t) in enumerate(pairs)]
    row['final_marking'] = [{'place_id': 'p5', 'tokens': 1}]
    row['final_markings'] = [row['final_marking']]
    return reseal(row)


class BpmnConversionTest(unittest.TestCase):
    def test_reduction_preserves_source_coverage_and_explicit_invisibility(self):
        rows = [source(1, ('tau', 'B')), source(2, ('hidden', 'B'), invisible=True), parallel(3)]
        before = copy.deepcopy(rows)
        for model in models(rows):
            graph = source_graph(convert_model(model))
            items = graph['nodes'] + graph['edges']
            self.assertEqual(set(model['_nodes']), {nid for n in items for nid in n['original_ids']['node_ids']})
            self.assertEqual({a['id'] for a in model['arcs']}, {aid for n in items for aid in n['original_ids']['arc_ids']})
            labels = [n['label'] for n in graph['nodes'] if n['kind'] == 'task']
            self.assertCountEqual([t['label'] for t in model['transitions'] if not t['invisible']], labels)
        self.assertEqual(before, rows)

    def test_petri_order_and_repeated_conversions_do_not_change_ids_or_views(self):
        rows = [parallel(1), source(2, ('A', 'A', 'B'))]
        first = analyze(models(rows), representation='bpmn')
        shuffled = copy.deepcopy(rows[::-1])
        for row in shuffled:
            for field in ('places', 'transitions', 'arcs'):
                row[field].reverse()
        second = analyze(models(shuffled), representation='bpmn')
        self.assertEqual(first['views'], second['views'])
        self.assertEqual(first['derived_models'], second['derived_models'])
        self.assertEqual(first['models'], second['models'])

    def test_gateway_types_and_direction_distinguish_choice_from_parallel(self):
        choice = source(1)
        choice['places'] = [choice['places'][0], choice['places'][2]]
        choice['arcs'] = [{'id': f'a{i}{d}', 'source': s, 'target': t, 'weight': 1}
                          for i in range(2) for d, s, t in [('i', 'p0', f't{i}'), ('o', f't{i}', 'p2')]]
        result = analyze(models([reseal(choice), parallel(2)]), representation='bpmn')
        self.assertEqual(2, len(result['views']['variation']['regions'][0]['alternatives']))
        self.assertTrue(any(n['kind'] == 'exclusive_gateway' for n in result['derived_models']['m-1']['nodes']))
        self.assertEqual({'CONVERGING', 'DIVERGING'}, {n['gateway_direction'] for n in result['derived_models']['m-2']['nodes'] if n['kind'] == 'parallel_gateway'})

    def test_gateway_symbols_do_not_make_an_activity_label_ambiguous(self):
        row = parallel(2)
        row['transitions'][0]['label'] = '+'
        result = analyze(models([source(1, ('+', 'B')), reseal(row)]), representation='bpmn')
        plus = [n for n in result['views']['merging']['nodes'] if n['kind'] == 'task' and n['label'] == '+']
        self.assertEqual(1, len(plus))
        self.assertEqual(2, plus[0]['support'])
        self.assertEqual('activity_label', plus[0]['matching'])

    def test_adapter_matches_pm4py_conversion_structure(self):
        import networkx as nx
        import pm4py
        from pm4py.objects.bpmn.obj import BPMN
        from pm4py.objects.petri_net.obj import PetriNet, Marking
        from pm4py.objects.petri_net.utils.petri_utils import add_arc_from_to
        kinds = [(BPMN.Task, 'task'), (BPMN.StartEvent, 'start_event'), (BPMN.NormalEndEvent, 'end_event'),
                 (BPMN.ParallelGateway, 'parallel_gateway'), (BPMN.ExclusiveGateway, 'exclusive_gateway')]
        loop = source(4)
        loop['arcs'].append({'id': 'back', 'source': 't1', 'target': 'p0', 'weight': 1})
        for model in models([source(1), source(2, invisible=True), parallel(3), reseal(loop)]):
            net, objects = PetriNet(), {}
            for p in model['places']:
                objects[p['id']] = PetriNet.Place(p['id']); net.places.add(objects[p['id']])
            for t in model['transitions']:
                objects[t['id']] = PetriNet.Transition(t['id'], None if t['invisible'] else t['label']); net.transitions.add(objects[t['id']])
            for a in model['arcs']:
                add_arc_from_to(objects[a['source']], objects[a['target']], net, a['weight'])
            marking = lambda entries: Marking({objects[e['place_id']]: e['tokens'] for e in entries})
            native = pm4py.convert_to_bpmn(net, marking(model['initial_marking']), marking(model['final_marking']))
            expected = nx.MultiDiGraph()
            for n in native.get_nodes():
                kind = next(kind for cls, kind in kinds if isinstance(n, cls))
                expected.add_node(n.get_id(), signature=(kind, n.get_name() if kind == 'task' else '',
                                  n.get_gateway_direction().name if isinstance(n, BPMN.Gateway) else ''))
            for f in native.get_flows(): expected.add_edge(f.get_source().get_id(), f.get_target().get_id())
            actual = nx.MultiDiGraph()
            converted = source_graph(convert_model(model))
            for n in converted['nodes']: actual.add_node(n['id'], signature=(n['kind'], n['label'] if n['kind'] == 'task' else '', n.get('gateway_direction', '')))
            for f in converted['edges']: actual.add_edge(f['source'], f['target'])
            self.assertTrue(nx.is_isomorphic(expected, actual, node_match=lambda a, b: a['signature'] == b['signature']))

    def test_limitations_are_not_new_population_filters_and_cancel_is_cooperative(self):
        result = analyze(models([source(1, weight=2, finals=[[], [{'place_id': 'p2', 'tokens': 2}]])]), representation='bpmn')
        self.assertEqual(1, result['population_size'])
        with self.assertRaises(InterruptedError):
            analyze(models([source(1)]), cancel=lambda: True, representation='bpmn')
        with self.assertRaises(ValueError):
            analyze(models([source(1)]), representation='unknown')


class BpmnApiTest(unittest.TestCase):
    setUp = fixtures.ExplorationTest.setUp
    tearDown = fixtures.ExplorationTest.tearDown

    def test_representation_cache_and_http_originals(self):
        import api
        from api.manager import OptimizationJobManager
        previous = api.get_manager()
        manager = OptimizationJobManager('http://unused', 'sqlite:///' + self.directory.name + '/bpmn-api.db', 10)
        api.set_manager(manager)
        try:
            rows = [source(1), source(2, ('A', 'C'))]
            manager.job_store.save_completed_experiment(data(), rows)
            client = api.app.test_client()
            ids = {}
            for representation in ('petri', 'bpmn'):
                response = client.post('/experiments/original-exp/explorations', json={'representation': representation})
                self.assertEqual(202, response.status_code, response.json)
                eid = response.json['exploration_id']; ids[representation] = eid
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    status = client.get(f'/explorations/{eid}').json
                    if status['status'] != 'running': break
                    time.sleep(.01)
                self.assertEqual('completed', status['status'], status)
                self.assertEqual(representation, status['representation'])
                self.assertNotIn('derived_models', status)
                for kind in ('merging', 'variation', 'template'):
                    self.assertEqual(200, client.get(f'/explorations/{eid}/views/{kind}').status_code)
                mid = status['models'][0]['model_id']
                original = client.get(f'/explorations/{eid}/models/{mid}').json
                self.assertEqual(rows[0]['initial_marking'], original['initial_marking'])
                self.assertEqual(rows[0]['final_markings'], original['final_markings'])
                self.assertEqual(rows[0]['metrics'], original['metrics'])
                self.assertEqual(representation == 'bpmn', bool(original['bpmn']))
                self.assertEqual(rows[0]['original_pnml'].encode(), client.get(f'/explorations/{eid}/models/{mid}/pnml').data)
                self.assertEqual(eid, client.post('/experiments/original-exp/explorations', json={'representation': representation}).json['exploration_id'])
            self.assertNotEqual(ids['petri'], ids['bpmn'])
            self.assertEqual(400, client.post('/experiments/original-exp/explorations', json={'representation': 'invalid'}).status_code)
        finally:
            api.set_manager(previous)
            manager.job_store.engine.dispose()
