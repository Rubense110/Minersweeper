"""Log-aware safeguards for preprocessing parameter spaces."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import xml.etree.ElementTree as ET


def _local_name(tag: str) -> str:
    if not tag:
        return ""
    return tag.rsplit("}", 1)[-1]


@lru_cache(maxsize=32)
def _variant_filter_min_keep_threshold(log_path: str) -> Optional[int]:
    path = Path(log_path)
    if not path.exists():
        return None

    total_traces = 0
    top_variant_count = 0
    variant_counts: Dict[Tuple[str, ...], int] = {}
    stack: list[str] = []
    current_trace: Optional[list[str]] = None
    current_event_name: Optional[str] = None

    for event, elem in ET.iterparse(str(path), events=("start", "end")):
        tag = _local_name(elem.tag)
        if event == "start":
            stack.append(tag)
            if tag == "trace":
                current_trace = []
            elif tag == "event":
                current_event_name = None
            continue

        if tag == "string":
            parent = stack[-2] if len(stack) >= 2 else ""
            if parent == "event" and elem.attrib.get("key") == "concept:name":
                current_event_name = elem.attrib.get("value") or ""
        elif tag == "event":
            if current_trace is not None and current_event_name:
                current_trace.append(current_event_name)
            current_event_name = None
        elif tag == "trace":
            if current_trace:
                total_traces += 1
                variant = tuple(current_trace)
                count = variant_counts.get(variant, 0) + 1
                variant_counts[variant] = count
                if count > top_variant_count:
                    top_variant_count = count
            current_trace = None
            elem.clear()

        if stack:
            stack.pop()

    if total_traces <= 0 or top_variant_count <= 0:
        return None
    return max(1, min(100, int(ceil((top_variant_count * 100.0) / total_traces))))


def adjusted_bounds(
    prep_key: str,
    param_name: str,
    bounds: Optional[Tuple[float, float]],
    log_path: Optional[str] = None,
) -> Optional[Tuple[float, float]]:
    if bounds is None:
        return None

    low, high = bounds
    if prep_key == "projection_filter" and param_name == "keep_threshold_p":
        return max(1.0, low), high
    if prep_key == "variant_filter" and param_name == "keep_threshold_vf" and log_path:
        min_keep = _variant_filter_min_keep_threshold(log_path)
        if min_keep is not None:
            return max(float(min_keep), low), high
    return bounds


def repair_pipeline_preprocessing(log_path: str, pipeline: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(pipeline, dict):
        return pipeline

    repaired = deepcopy(pipeline)
    preprocessing = repaired.get("preprocessing")
    if not isinstance(preprocessing, dict):
        return repaired

    key = preprocessing.get("key")
    parameters = preprocessing.get("parameters")
    if not isinstance(parameters, dict):
        return repaired

    if key == "projection_filter":
        value = parameters.get("keep_threshold_p")
        if isinstance(value, (int, float)) and value < 1:
            parameters["keep_threshold_p"] = 1
    elif key == "variant_filter":
        min_keep = _variant_filter_min_keep_threshold(log_path)
        value = parameters.get("keep_threshold_vf")
        if min_keep is not None and isinstance(value, (int, float)) and value < min_keep:
            parameters["keep_threshold_vf"] = min_keep

    repaired["preprocessing"] = preprocessing
    return repaired
