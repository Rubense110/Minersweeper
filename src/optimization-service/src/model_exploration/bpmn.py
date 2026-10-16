"""PM4Py 2.7.11.13 Petri-to-BPMN adaptation with stable IDs and provenance.

Uses PM4Py's BPMN objects and the same mapping as wf_net.variants.to_bpmn.
The small adapter is necessary because that API discards the Petri/BPMN map.
Pass-through XOR reduction follows pm4py.objects.bpmn.util.reduction, ordered
by source IDs, and carries the contracted Petri elements into sequence flows.
This is a descriptive conversion, not a behavioral-equivalence certificate.
"""
from collections import defaultdict

from .analysis import _check, digest


def convert_model(model, cancel=None):
    _check(cancel)
    # Reuse the renderer's guarded import (Docker exec can have parent PID 0).
    from api.petri import _ensure_pm4py_loaded
    _ensure_pm4py_loaded()
    from pm4py.objects.bpmn.obj import BPMN

    graph = BPMN(process_id='minersweeper-derived-bpmn')
    entering, exiting, provenance, flow_provenance = {}, {}, {}, {}
    incoming, outgoing = defaultdict(list), defaultdict(list)
    for arc in model['arcs']:
        incoming[arc['target']].append(arc)
        outgoing[arc['source']].append(arc)

    def node(cls, role, original=None, **kwargs):
        nid = 'b-' + digest([role, original])[:24]
        obj = cls(id=nid, **kwargs)
        graph.add_node(obj)
        provenance[nid] = {'node_ids': [original] if original else [], 'arc_ids': []}
        return obj

    def flow(source, target, origin, nodes=(), arcs=()):
        fid = 'bf-' + digest(origin)[:24]
        obj = BPMN.SequenceFlow(source, target, id=fid)
        graph.add_flow(obj)
        flow_provenance[fid] = {'node_ids': sorted(set(nodes)), 'arc_ids': sorted(set(arcs))}
        return obj

    for place in sorted(model['places'], key=lambda p: p['id']):
        _check(cancel)
        obj = node(BPMN.ExclusiveGateway, 'place', place['id'])
        entering[place['id']] = exiting[place['id']] = obj
    for trans in sorted(model['transitions'], key=lambda t: t['id']):
        _check(cancel)
        tid = trans['id']
        join, split = len(incoming[tid]) > 1, len(outgoing[tid]) > 1
        if trans['invisible']:
            cls = BPMN.ParallelGateway if join or split else BPMN.ExclusiveGateway
            direction = BPMN.Gateway.Direction.CONVERGING if join else BPMN.Gateway.Direction.DIVERGING if split else BPMN.Gateway.Direction.UNSPECIFIED
            obj = node(cls, 'invisible', tid, gateway_direction=direction)
            entering[tid] = exiting[tid] = obj
        else:
            before = node(BPMN.ParallelGateway if join else BPMN.ExclusiveGateway, 'before', tid,
                          gateway_direction=BPMN.Gateway.Direction.CONVERGING if join else BPMN.Gateway.Direction.UNSPECIFIED)
            after = node(BPMN.ParallelGateway if split else BPMN.ExclusiveGateway, 'after', tid,
                         gateway_direction=BPMN.Gateway.Direction.DIVERGING if split else BPMN.Gateway.Direction.UNSPECIFIED)
            task = node(BPMN.Task, 'task', tid, name=trans.get('label') or '')
            flow(before, task, ['before', tid], nodes=[tid])
            flow(task, after, ['after', tid], nodes=[tid])
            entering[tid], exiting[tid] = before, after
    for arc in sorted(model['arcs'], key=lambda a: a['id']):
        flow(exiting[arc['source']], entering[arc['target']], ['arc', arc['id']], arcs=[arc['id']])
    start = node(BPMN.StartEvent, 'start', name='Inicio', isInterrupting=True)
    end = node(BPMN.NormalEndEvent, 'end', name='Fin')
    for entry in sorted(model['initial_marking'], key=lambda e: e['place_id']):
        pid = entry['place_id']
        flow(start, entering[pid], ['initial', pid], nodes=[pid])
    # Same single-final convention as PM4Py. All original finals remain in PNML/metadata.
    for entry in sorted(model['final_marking'], key=lambda e: e['place_id']):
        pid = entry['place_id']
        flow(exiting[pid], end, ['final', pid], nodes=[pid])

    while True:
        _check(cancel)
        candidate = next((n for n in sorted(graph.get_nodes(), key=lambda n: n.get_id())
                          if isinstance(n, BPMN.ExclusiveGateway) and len(n.get_in_arcs()) == len(n.get_out_arcs()) == 1
                          and n.get_in_arcs()[0] is not n.get_out_arcs()[0]), None)
        if candidate is None:
            break
        first, second = candidate.get_in_arcs()[0], candidate.get_out_arcs()[0]
        sources = [flow_provenance[first.get_id()], provenance[candidate.get_id()], flow_provenance[second.get_id()]]
        ns = sorted({nid for src in sources for nid in src['node_ids']})
        ars = sorted({aid for src in sources for aid in src['arc_ids']})
        source, target = first.get_source(), second.get_target()
        graph.remove_flow(first); graph.remove_flow(second); graph.remove_node(candidate)
        flow(source, target, ['reduced', source.get_id(), target.get_id(), sorted([first.get_id(), second.get_id()])], ns, ars)

    nodes = []
    for obj in sorted(graph.get_nodes(), key=lambda n: n.get_id()):
        if isinstance(obj, BPMN.Task):
            kind, label = 'task', obj.get_name()
        elif isinstance(obj, BPMN.StartEvent):
            kind, label = 'start_event', 'Inicio'
        elif isinstance(obj, BPMN.NormalEndEvent):
            kind, label = 'end_event', 'Fin'
        elif isinstance(obj, BPMN.ParallelGateway):
            kind, label = 'parallel_gateway', '+'
        else:
            kind, label = 'exclusive_gateway', '×'
        nodes.append({'id': obj.get_id(), 'kind': kind, 'label': label, 'invisible': False,
                      **({'gateway_direction': obj.get_gateway_direction().name} if isinstance(obj, BPMN.Gateway) else {}),
                      'original_ids': provenance[obj.get_id()]})
    arcs = [{'id': f.get_id(), 'source': f.get_source().get_id(), 'target': f.get_target().get_id(), 'weight': 1,
             'original_ids': flow_provenance[f.get_id()]} for f in sorted(graph.get_flows(), key=lambda f: f.get_id())]
    converted = {**model, 'representation': 'bpmn', 'places': [], 'transitions': nodes, 'arcs': arcs,
                 'initial_marking': [{'place_id': start.get_id(), 'tokens': 1}],
                 'final_marking': [{'place_id': end.get_id(), 'tokens': 1}],
                 'final_markings': [[{'place_id': end.get_id(), 'tokens': 1}]],
                 '_nodes': {n['id']: n for n in nodes}}
    converted.pop('_mapping', None)
    converted.pop('_ambiguous', None)
    return converted


def source_graph(model):
    return {'representation': 'bpmn', 'nodes': model['transitions'], 'edges': model['arcs']}
