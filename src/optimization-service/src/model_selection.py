"""ASF-based model selection helpers for completed experiments."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

import numpy as np
from pymoo.decomposition.asf import ASF


DEFAULT_SLIDER_WEIGHT = 50.0
MIN_ASF_WEIGHT = 1e-12


class ModelSelectionUnavailable(RuntimeError):
    """Raised when an experiment cannot produce an ASF-based selection."""


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


def _coerce_objective_vector(objectives: List[Any], metrics: List[str]) -> List[float] | None:
    if len(objectives) != len(metrics):
        return None

    parsed: List[float] = []
    for index, _metric in enumerate(metrics):
        try:
            value = float(objectives[index])
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value):
            return None
        parsed.append(value)
    return parsed


def _normalize_objectives(objective_vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    approx_ideal = objective_vectors.min(axis=0)
    approx_nadir = objective_vectors.max(axis=0)
    denom = approx_nadir - approx_ideal
    # If one objective is constant across candidates, normalization should not fail.
    safe_denom = np.where(np.abs(denom) > 0.0, denom, 1.0)
    normalized = (objective_vectors - approx_ideal) / safe_denom
    return normalized, approx_ideal, approx_nadir


def _asf_weights(metrics: List[str], normalized_weights: Dict[str, float]) -> np.ndarray:
    positive = np.array([max(normalized_weights[metric], MIN_ASF_WEIGHT) for metric in metrics], dtype=float)
    return 1.0 / positive


def select_weighted_model(
    experiment: Dict[str, Any],
    solutions: List[Dict[str, Any]],
    raw_weights: Dict[str, Any] | None,
    scope: str,
) -> Dict[str, Any]:
    metrics = [str(item) for item in list(experiment.get("metrics") or []) if str(item).strip()]
    slider_weights, normalized_weights = normalize_slider_weights(metrics, raw_weights)

    valid_candidates: List[Dict[str, Any]] = []
    objective_vectors: List[List[float]] = []
    for solution in solutions:
        objective_vector = _coerce_objective_vector(list(solution.get("objectives") or []), metrics)
        if objective_vector is None:
            continue
        valid_candidates.append(solution)
        objective_vectors.append(objective_vector)

    if not valid_candidates:
        raise ModelSelectionUnavailable("experiment has no valid solutions for ASF model selection")

    objective_matrix = np.asarray(objective_vectors, dtype=float)
    normalized_objectives, approx_ideal, approx_nadir = _normalize_objectives(objective_matrix)
    decomposition = ASF()
    asf_values = np.asarray(
        decomposition.do(normalized_objectives, _asf_weights(metrics, normalized_weights)),
        dtype=float,
    ).reshape(-1)
    best_index = int(np.argmin(asf_values))
    best_score = float(asf_values[best_index])
    best_solution = valid_candidates[best_index]

    return {
        "experiment_id": experiment.get("experiment_id"),
        "scope": scope,
        "selection_method": "asf",
        "metrics": metrics,
        "slider_weights": slider_weights,
        "normalized_weights": normalized_weights,
        "candidate_count": len(valid_candidates),
        "selected_solution_id": best_solution.get("solution_id"),
        "selected_solution": best_solution,
        "scalarized_objective": best_score,
        "approx_ideal": approx_ideal.tolist(),
        "approx_nadir": approx_nadir.tolist(),
    }
