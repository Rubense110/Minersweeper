"""Constraint-aware Pareto helpers shared by optimization and serialization."""

from __future__ import annotations

from typing import Any, Iterable, List
import math

from jmetal.util.comparator import DominanceWithConstraintsComparator, overall_constraint_violation_degree
from jmetal.util.ranking import FastNonDominatedRanking


class SemanticConstraintDominanceComparator(DominanceWithConstraintsComparator):
    def compare(self, first, second):
        # Slot zero remains semantic feasibility/technical validity. User limits
        # must never make an unusable net preferable to a usable one.
        a, b = getattr(first, 'constraints', []), getattr(second, 'constraints', [])
        if len(a) > 1 or len(b) > 1:
            invalid_a, invalid_b = bool(a and a[0] < 0), bool(b and b[0] < 0)
            if invalid_a != invalid_b:
                return 1 if invalid_a else -1
        return super().compare(first, second)


CONSTRAINT_DOMINANCE_COMPARATOR = SemanticConstraintDominanceComparator()


def is_eligible_payload(payload):
    if has_evaluation_error(payload) or payload.get('is_feasible') is False:
        return False
    try:
        return all(math.isfinite(float(v)) and float(v) >= 0 for v in payload.get('constraints') or [])
    except (ValueError, TypeError, OverflowError):
        return False


def has_evaluation_error(payload: dict[str, Any]) -> bool:
    """Recognize failed evaluations independently of model feasibility."""
    return payload.get("evaluation_error") is not None or payload.get("evaluation_status") == "error"


def is_feasible_solution(solution: Any) -> bool:
    """Return whether a solution is eligible for the public Pareto front.

    New executions carry both the explicit feasibility metadata and the jMetalPy
    constraint.  Missing metadata/constraints remains readable as legacy data.
    """
    attributes = getattr(solution, "attributes", {}) or {}
    if has_evaluation_error(attributes):
        return False
    if attributes.get("is_feasible") is False:
        return False
    if getattr(solution, "constraints", None) is None:
        return True
    return overall_constraint_violation_degree(solution) == 0.0


def feasible_non_dominated(solutions: Iterable[Any]) -> List[Any]:
    feasible_solutions = [solution for solution in solutions if is_feasible_solution(solution)]
    if not feasible_solutions:
        return []

    ranking = FastNonDominatedRanking(CONSTRAINT_DOMINANCE_COMPARATOR)
    ranking.compute_ranking(feasible_solutions)
    return ranking.get_subfront(0)


def feasible_non_dominated_evaluation_ids(solutions: Iterable[Any]) -> set[str]:
    evaluation_ids: set[str] = set()
    for solution in feasible_non_dominated(solutions):
        attributes = getattr(solution, "attributes", {}) or {}
        evaluation_id = attributes.get("evaluation_id")
        if evaluation_id:
            evaluation_ids.add(str(evaluation_id))
    return evaluation_ids
