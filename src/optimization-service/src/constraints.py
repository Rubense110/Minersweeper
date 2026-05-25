"""Constraint handling helpers for optimization experiments."""

from __future__ import annotations

import math
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
    if metrics is None:
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


def normalize_constraints(raw_constraints: Any) -> List[Dict[str, Any]]:
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
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"constraints[{index}].value must be a finite number") from None
        if not math.isfinite(value):
            raise ValueError(f"constraints[{index}].value must be a finite number")

        key = (metric, operator, value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"metric": metric, "operator": operator, "value": value})

    return normalized


def collect_required_metrics(objective_metrics: Sequence[str], constraints: Sequence[Dict[str, Any]]) -> List[str]:
    required: List[str] = []
    seen = set()
    for metric in list(objective_metrics or []):
        metric_name = str(metric or "").strip()
        if metric_name and metric_name not in seen:
            seen.add(metric_name)
            required.append(metric_name)
    for constraint in list(constraints or []):
        metric_name = str((constraint or {}).get("metric") or "").strip()
        if metric_name and metric_name not in seen:
            seen.add(metric_name)
            required.append(metric_name)
    return required


def evaluate_constraints(
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
        except (TypeError, ValueError):
            metric_value = float("nan")

        if not math.isfinite(metric_value):
            results.append(float("-inf"))
            continue

        if operator == ">=":
            results.append(metric_value - threshold)
        elif operator == ">":
            results.append(metric_value - threshold - equality_tolerance)
        elif operator == "<=":
            results.append(threshold - metric_value)
        elif operator == "<":
            results.append(threshold - metric_value - equality_tolerance)
        elif operator == "==":
            results.append(equality_tolerance - abs(metric_value - threshold))
        else:
            raise ValueError(f"unsupported constraint operator: {operator}")
    return results


def summarize_constraints(constraints: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for item in list(constraints or []):
        metric = str(item.get("metric") or "").strip()
        operator = str(item.get("operator") or "").strip()
        value = item.get("value")
        if not metric or not operator:
            continue
        parts.append(f"{metric}{operator}{value}")
    return ",".join(parts)


def is_feasible_constraint_values(values: Sequence[float]) -> bool:
    return all(float(value) >= 0.0 for value in list(values or []))
