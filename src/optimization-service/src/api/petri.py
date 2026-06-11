from __future__ import annotations

import os
import sys
import threading
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


_PM4PY_IMPORT_LOCK = threading.Lock()


def _local_xml_name(tag: str) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _xml_node_label(element: ET.Element) -> str:
    for child in element.iter():
        if _local_xml_name(child.tag) == "text":
            text = (child.text or "").strip()
            if text:
                return text
    return ""


def _petri_from_pnml(pnml_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not pnml_text:
        return [], [], []

    try:
        root = ET.fromstring(pnml_text)
    except ET.ParseError:
        return [], [], []

    places: List[Dict[str, Any]] = []
    transitions: List[Dict[str, Any]] = []
    arcs: List[Dict[str, Any]] = []

    for node in root.iter():
        tag = _local_xml_name(node.tag)
        if tag == "place":
            places.append(
                {
                    "id": (node.attrib.get("id") or "").strip(),
                    "label": _xml_node_label(node),
                }
            )
        elif tag == "transition":
            transitions.append(
                {
                    "id": (node.attrib.get("id") or "").strip(),
                    "label": _xml_node_label(node),
                }
            )
        elif tag == "arc":
            arcs.append(
                {
                    "id": (node.attrib.get("id") or "").strip(),
                    "source": (node.attrib.get("source") or "").strip(),
                    "target": (node.attrib.get("target") or "").strip(),
                }
            )

    return places, transitions, arcs


def _ensure_pm4py_loaded() -> None:
    if "pm4py" in sys.modules:
        return

    with _PM4PY_IMPORT_LOCK:
        if "pm4py" in sys.modules:
            return

        import importlib

        if os.getppid() == 0:
            original_getppid = os.getppid
            try:
                os.getppid = lambda: 1  # type: ignore[assignment]
                importlib.import_module("pm4py")
            finally:
                os.getppid = original_getppid  # type: ignore[assignment]
        else:
            importlib.import_module("pm4py")


def _extract_node_id(raw: Any, prefix: str, index: int) -> str:
    text = str(raw or "").strip()
    if text:
        return text
    return f"{prefix}-{index + 1}"


def _normalize_transition_label(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.lower() in {"tau", "silent", "invisible"}:
        return None
    return text


def _build_petri_net_from_payload(
    places_payload: Any, transitions_payload: Any, arcs_payload: Any
) -> Tuple[Any, Dict[str, Any]]:
    _ensure_pm4py_loaded()
    from pm4py.objects.petri_net.obj import PetriNet
    from pm4py.objects.petri_net.utils.petri_utils import add_arc_from_to

    places = places_payload if isinstance(places_payload, list) else []
    transitions = transitions_payload if isinstance(transitions_payload, list) else []
    arcs = arcs_payload if isinstance(arcs_payload, list) else []

    net = PetriNet("rendered-net")
    place_nodes: Dict[str, Any] = {}
    transition_nodes: Dict[str, Any] = {}

    for index, item in enumerate(places):
        if not isinstance(item, dict):
            continue
        place_id = _extract_node_id(item.get("id"), "place", index)
        if place_id in place_nodes:
            continue
        place = PetriNet.Place(place_id)
        net.places.add(place)
        place_nodes[place_id] = place

    for index, item in enumerate(transitions):
        if not isinstance(item, dict):
            continue
        transition_id = _extract_node_id(item.get("id"), "transition", index)
        if transition_id in transition_nodes:
            continue
        transition_label = _normalize_transition_label(item.get("label"))
        transition = PetriNet.Transition(transition_id, transition_label)
        net.transitions.add(transition)
        transition_nodes[transition_id] = transition

    if not place_nodes and not transition_nodes:
        raise ValueError("petri net payload is empty")

    for item in arcs:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source") or "").strip()
        target_id = str(item.get("target") or "").strip()
        if not source_id or not target_id:
            continue

        source_node = place_nodes.get(source_id) or transition_nodes.get(source_id)
        target_node = place_nodes.get(target_id) or transition_nodes.get(target_id)
        if source_node is None or target_node is None:
            continue

        is_source_place = source_id in place_nodes
        is_target_place = target_id in place_nodes
        if is_source_place == is_target_place:
            continue

        add_arc_from_to(source_node, target_node, net)

    return net, place_nodes


def _marking_from_payload(payload: Any, place_nodes: Dict[str, Any]) -> Any:
    _ensure_pm4py_loaded()
    from pm4py.objects.petri_net.obj import Marking

    marking = Marking()
    if payload is None:
        return marking

    entries: List[Tuple[str, Any]] = []
    if isinstance(payload, dict):
        entries = [(str(key), value) for key, value in payload.items()]
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            place_id = str(item.get("place") or item.get("id") or "").strip()
            entries.append((place_id, item.get("tokens")))
    else:
        raise ValueError("marking must be an object or a list")

    for place_id, tokens_raw in entries:
        place_id = str(place_id or "").strip()
        if not place_id:
            continue
        if place_id not in place_nodes:
            raise ValueError(f"unknown place in marking: '{place_id}'")
        try:
            tokens = int(tokens_raw)
        except (TypeError, ValueError):
            raise ValueError(f"invalid token count for place '{place_id}'") from None
        if tokens < 0:
            raise ValueError(f"negative token count for place '{place_id}'")
        if tokens == 0:
            continue
        marking[place_nodes[place_id]] = tokens

    return marking


def _render_petri_image_bytes(
    places_payload: Any,
    transitions_payload: Any,
    arcs_payload: Any,
    initial_marking_payload: Any,
    final_marking_payload: Any,
    output_format: str,
) -> Tuple[bytes, str]:
    _ensure_pm4py_loaded()
    from pm4py.visualization.petri_net import visualizer as pn_visualizer

    normalized_format = str(output_format or "svg").strip().lower()
    if normalized_format not in {"svg", "png"}:
        raise ValueError("format must be 'svg' or 'png'")

    net, place_nodes = _build_petri_net_from_payload(places_payload, transitions_payload, arcs_payload)
    initial_marking = _marking_from_payload(initial_marking_payload, place_nodes)
    final_marking = _marking_from_payload(final_marking_payload, place_nodes)

    variant = pn_visualizer.Variants.WO_DECORATION
    parameters = {variant.value.Parameters.FORMAT: normalized_format}
    rankdir_parameter = getattr(variant.value.Parameters, "RANKDIR", None)
    if rankdir_parameter is not None:
        parameters[rankdir_parameter] = "LR"
    else:
        parameters["rankdir"] = "LR"
    graph = pn_visualizer.apply(net, initial_marking, final_marking, parameters=parameters, variant=variant)
    if hasattr(graph, "graph_attr"):
        graph.graph_attr["rankdir"] = "LR"
    rendered = graph.pipe(format=normalized_format)
    if isinstance(rendered, str):
        rendered = rendered.encode("utf-8")

    mimetype = "image/svg+xml" if normalized_format == "svg" else "image/png"
    return rendered, mimetype
