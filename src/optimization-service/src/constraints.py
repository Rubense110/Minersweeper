"""Constraint handling helpers for optimization experiments."""

from __future__ import annotations

import math
import json
from typing import Any, Dict, Iterable, List, Sequence


SUPPORTED_METRICS = {
    "fitness",
    "precision",
    "simplicity",
    "generalisation",
    "places",
    "transitions",
    "arcs",
    "t_edges",
    "cycl_complx",
    "cfc",
    "elc",
    "ratio",
    "joins",
    "splits",
}

SUPPORTED_OPERATORS = {"<", "<=", ">", ">=", "=="}


def normalize_metric_names(metrics: Iterable[Any]) -> List[str]:
    if not isinstance(metrics, (list, tuple)):
        raise ValueError("metrics must contain at least one metric")

    normalized: List[str] = []
    seen = set()
    for metric in metrics:
        metric_name = str(metric or "").strip()
        if not metric_name:
            continue
        if metric_name not in SUPPORTED_METRICS:
            raise ValueError(f"unsupported metric: {metric_name}")
        if metric_name in seen:
            continue
        seen.add(metric_name)
        normalized.append(metric_name)

    if not normalized:
        raise ValueError("metrics must contain at least one metric")
    return normalized


def _normalize_flat_constraints(raw_constraints: Any) -> List[Dict[str, Any]]:
    if raw_constraints is None:
        return []
    if not isinstance(raw_constraints, list):
        raise ValueError("constraints must be a list")

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for index, item in enumerate(raw_constraints):
        if not isinstance(item, dict):
            raise ValueError(f"constraints[{index}] must be an object")

        metric = str(item.get("metric") or "").strip()
        if not metric:
            raise ValueError(f"constraints[{index}].metric is required")
        if metric not in SUPPORTED_METRICS:
            raise ValueError(f"unsupported metric: {metric}")

        operator = str(item.get("operator") or "").strip()
        if operator not in SUPPORTED_OPERATORS:
            raise ValueError(
                f"constraints[{index}].operator must be one of {', '.join(sorted(SUPPORTED_OPERATORS))}"
            )

        raw_value = item.get("value")
        if isinstance(raw_value, bool):
            raise ValueError(f"constraints[{index}].value must be a finite number")
        try:
            value = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"constraints[{index}].value must be a finite number") from None
        if not math.isfinite(value):
            raise ValueError(f"constraints[{index}].value must be a finite number")

        key = (metric, operator, value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"metric": metric, "operator": operator, "value": value})

    return normalized


CONSTRAINT_POLICY_VERSION = "minersweeper-constraints-v2"
MAX_CONSTRAINT_DEPTH = 8
MAX_CONSTRAINT_NODES = 256


def normalize_constraints(raw_constraints: Any) -> List[Dict[str, Any]]:
    """An existing list remains AND; all/any nodes may contain nested rules."""
    if raw_constraints is None:
        return []
    if not isinstance(raw_constraints, list):
        raise ValueError("constraints must be a list")
    count = 0

    def normalize(node, depth):
        nonlocal count
        count += 1
        if count > MAX_CONSTRAINT_NODES or depth > MAX_CONSTRAINT_DEPTH:
            raise ValueError("constraints exceed the depth or node limit")
        if not isinstance(node, dict):
            raise ValueError("each constraint must be an object")
        groups = [key for key in ("all", "any") if key in node]
        if groups:
            if len(groups) != 1 or set(node) != {groups[0]}:
                raise ValueError("constraint groups must contain only all or only any")
            key = groups[0]
            children = node[key]
            if not isinstance(children, list) or not children:
                raise ValueError("constraint groups must contain a non-empty list")
            return {key: deduplicate([normalize(child, depth + 1) for child in children])}
        if set(node) - {"metric", "operator", "value"}:
            raise ValueError("unknown fields in metric constraint")
        return _normalize_flat_constraints([node])[0]

    def deduplicate(nodes):
        result, seen = [], set()
        for node in nodes:
            identity = json.dumps(node, sort_keys=True)
            if identity not in seen:
                seen.add(identity)
                result.append(node)
        return result

    return deduplicate([normalize(node, 1) for node in raw_constraints])


def constraint_leaves(node):
    for key in ("all", "any"):
        if key in node:
            for child in node[key]:
                yield from constraint_leaves(child)
            return
    yield node


def collect_required_metrics(objective_metrics: Sequence[str], constraints: Sequence[Dict[str, Any]]) -> List[str]:
    required: List[str] = []
    seen = set()
    for metric in list(objective_metrics or []):
        metric_name = str(metric or "").strip()
        if metric_name and metric_name not in seen:
            seen.add(metric_name)
            required.append(metric_name)
    for node in constraints or []:
        for constraint in constraint_leaves(node):
            metric_name = str(constraint.get("metric") or "").strip()
            if metric_name and metric_name not in seen:
                seen.add(metric_name)
                required.append(metric_name)
    return required


def _evaluate_leaf_constraints(
    metric_values: Dict[str, Any],
    constraints: Sequence[Dict[str, Any]],
    *,
    equality_tolerance: float = 1e-9,
) -> List[float]:
    results: List[float] = []
    for constraint in list(constraints or []):
        metric_name = str(constraint.get("metric") or "").strip()
        operator = str(constraint.get("operator") or "").strip()
        threshold = float(constraint.get("value"))
        raw_metric_value = metric_values.get(metric_name)
        try:
            metric_value = float(raw_metric_value)
        except (TypeError, ValueError, OverflowError):
            metric_value = float("nan")

        if not math.isfinite(metric_value):
            # Finite penalty: safe for JSON persistence and jMetal ranking.
            results.append(-1.0)
            continue

        if operator == ">=":
            results.append(metric_value - threshold)
        elif operator == ">":
            margin = metric_value - threshold
            results.append(margin if metric_value > threshold else min(-equality_tolerance, margin))
        elif operator == "<=":
            results.append(threshold - metric_value)
        elif operator == "<":
            margin = threshold - metric_value
            results.append(margin if metric_value < threshold else min(-equality_tolerance, margin))
        elif operator == "==":
            results.append(equality_tolerance - abs(metric_value - threshold))
        else:
            raise ValueError(f"unsupported constraint operator: {operator}")
    # Subtraction of extreme finite inputs can overflow; never persist Infinity.
    return [value if math.isfinite(value) else math.copysign(1e308, value) for value in results]


def evaluate_constraints(metric_values, constraints, *, equality_tolerance=1e-9):
    """One margin per top-level rule, with native feasibility kept separately.

    Flat rules retain their historical raw margins. Group leaves use fixed
    threshold scales; min implements AND, max implements OR. All required
    metrics must be available, even in an otherwise satisfied OR branch.
    """
    def evaluate(node):
        for key, aggregate in (("all", min), ("any", max)):
            if key in node:
                return aggregate(evaluate(child) for child in node[key])
        margin = _evaluate_leaf_constraints(metric_values, [node], equality_tolerance=equality_tolerance)[0]
        scaled = margin / max(abs(float(node["value"])), 1.0)
        # Preserve the sign if dividing a subnormal nonzero margin underflows.
        return scaled if scaled != 0 or margin == 0 else math.copysign(math.ulp(0.0), margin)

    results = []
    for node in constraints or []:
        if not any(key in node for key in ("all", "any")):
            results.extend(_evaluate_leaf_constraints(metric_values, [node], equality_tolerance=equality_tolerance))
            continue
        try:
            complete = all(math.isfinite(float(metric_values.get(leaf["metric"])))
                           for leaf in constraint_leaves(node))
        except (TypeError, ValueError, OverflowError):
            complete = False
        results.append(evaluate(node) if complete else -1.0)
    return results


def summarize_constraints(constraints: Sequence[Dict[str, Any]]) -> str:
    def describe(node):
        for key, separator in (("all", " AND "), ("any", " OR ")):
            if key in node:
                return "(" + separator.join(describe(child) for child in node[key]) + ")"
        return f"{node['metric']}{node['operator']}{node['value']}"
    return ",".join(describe(node) for node in constraints or [])


def is_feasible_constraint_values(values: Sequence[float]) -> bool:
    return all(float(value) >= 0.0 for value in list(values or []))
