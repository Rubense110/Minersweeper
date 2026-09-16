"""Constraint-aware Pareto helpers shared by optimization and serialization."""

from __future__ import annotations

from typing import Any, Iterable, List

from jmetal.util.comparator import DominanceWithConstraintsComparator, overall_constraint_violation_degree
from jmetal.util.ranking import FastNonDominatedRanking


CONSTRAINT_DOMINANCE_COMPARATOR = DominanceWithConstraintsComparator()


def is_feasible_solution(solution: Any) -> bool:
    """Return whether a solution is eligible for the public Pareto front.

    New executions carry both the explicit feasibility metadata and the jMetalPy
    constraint.  Missing metadata/constraints remains readable as legacy data.
    """
    attributes = getattr(solution, "attributes", {}) or {}
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
