"""Static PM4Py BPMN images using the existing variability conversion."""
from .petri import (_build_petri_net_from_payload, _marking_from_payload,
                    _final_marking_payload, _ensure_pm4py_loaded)


def _render_bpmn_image_bytes(places_payload, transitions_payload, arcs_payload,
                             initial_marking_payload, final_marking_payload,
                             output_format, final_markings_payload=None):
    normalized_format = str(output_format or 'svg').strip().lower()
    if normalized_format not in {'svg', 'png'}:
        raise ValueError("format must be 'svg' or 'png'")
    _ensure_pm4py_loaded()
    from model_exploration.bpmn import _convert_model_graph
    from pm4py.visualization.bpmn import visualizer

    net, places = _build_petri_net_from_payload(places_payload, transitions_payload, arcs_payload)
    initial = _marking_from_payload(initial_marking_payload, places)
    final = _marking_from_payload(_final_marking_payload(final_marking_payload, final_markings_payload), places)
    model = {
        'places': [{'id': place.name} for place in net.places],
        'transitions': [{'id': transition.name, 'label': transition.label or '',
                         'invisible': transition.label is None} for transition in net.transitions],
        'arcs': [{'id': f'a{index}', 'source': arc.source.name, 'target': arc.target.name,
                  'weight': arc.weight} for index, arc in enumerate(sorted(
                      net.arcs, key=lambda arc: (arc.source.name, arc.target.name, arc.weight)))],
        'initial_marking': [{'place_id': place.name, 'tokens': tokens} for place, tokens in initial.items()],
        'final_marking': [{'place_id': place.name, 'tokens': tokens} for place, tokens in final.items()],
    }
    graph, *_ = _convert_model_graph(model)
    drawing = visualizer.apply(graph, parameters={'format': normalized_format, 'rankdir': 'LR', 'font_size': 14})
    rendered = drawing.pipe(format=normalized_format)
    if isinstance(rendered, str):
        rendered = rendered.encode('utf-8')
    return rendered, 'image/svg+xml' if normalized_format == 'svg' else 'image/png'
