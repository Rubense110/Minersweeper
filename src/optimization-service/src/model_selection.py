"""Weighted model selection helpers for completed experiments."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


DEFAULT_SLIDER_WEIGHT = 50.0


class ModelSelectionUnavailable(RuntimeError):
    """Raised when an experiment cannot produce a weighted selection."""


def _coerce_slider_weight(value: Any, default: float = DEFAULT_SLIDER_WEIGHT) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return min(100.0, max(0.0, number))


def normalize_slider_weights(
    metrics: List[str],
    raw_weights: Dict[str, Any] | None,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    if not metrics:
        raise ModelSelectionUnavailable("experiment does not define metrics for model selection")

    source = raw_weights if isinstance(raw_weights, dict) else {}
    slider_weights: Dict[str, float] = {}
    for metric in metrics:
        slider_weights[metric] = _coerce_slider_weight(source.get(metric))

    total_weight = sum(slider_weights.values())
    if total_weight > 0:
        normalized = {metric: value / total_weight for metric, value in slider_weights.items()}
    else:
        uniform = 1.0 / len(metrics)
        normalized = {metric: uniform for metric in metrics}

    return slider_weights, normalized


def _scalarize_objectives(objectives: List[Any], metrics: List[str], normalized_weights: Dict[str, float]) -> float | None:
    if len(objectives) != len(metrics):
        return None

    scalarized = 0.0
    for index, metric in enumerate(metrics):
        try:
            value = float(objectives[index])
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        scalarized += value * normalized_weights[metric]
    return scalarized


def select_weighted_model(
    experiment: Dict[str, Any],
    solutions: List[Dict[str, Any]],
    raw_weights: Dict[str, Any] | None,
    scope: str,
    feasible_only: bool = False,
) -> Dict[str, Any]:
    metrics = [str(item) for item in list(experiment.get("metrics") or []) if str(item).strip()]
    slider_weights, normalized_weights = normalize_slider_weights(metrics, raw_weights)

    valid_candidates: List[Tuple[float, Dict[str, Any]]] = []
    for solution in solutions:
        if feasible_only and not bool(solution.get("is_feasible", True)):
            continue
        scalarized = _scalarize_objectives(list(solution.get("objectives") or []), metrics, normalized_weights)
        if scalarized is None:
            continue
        valid_candidates.append((scalarized, solution))

    if not valid_candidates:
        if feasible_only:
            raise ModelSelectionUnavailable("experiment has no feasible valid solutions for weighted model selection")
        raise ModelSelectionUnavailable("experiment has no valid solutions for weighted model selection")

    best_score, best_solution = min(valid_candidates, key=lambda item: item[0])
    return {
        "experiment_id": experiment.get("experiment_id"),
        "scope": scope,
        "selection_method": "weighted_sum",
        "metrics": metrics,
        "slider_weights": slider_weights,
        "normalized_weights": normalized_weights,
        "feasible_only": bool(feasible_only),
        "candidate_count": len(valid_candidates),
        "selected_solution_id": best_solution.get("solution_id"),
        "selected_solution": best_solution,
        "scalarized_objective": best_score,
    }
