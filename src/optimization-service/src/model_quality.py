"""Versioned feasibility contract shared by optimization and artifact persistence."""

from __future__ import annotations

from typing import Any


V3_VIOLATIONS = frozenset({
    "NO_VISIBLE_TRANSITIONS",
    "MULTIPLE_FINAL_MARKINGS",
    "MULTIPLE_COMPONENTS",
    "QUALITY_CHECK_INCONCLUSIVE",
    "FINAL_NOT_REACHABLE",
    "NO_OPTION_TO_COMPLETE",
    "NO_NONTRIVIAL_COMPLETION",
    "DEAD_VISIBLE_TRANSITION",
    "DEAD_INVISIBLE_TRANSITION",
})


def validate_v3_feasibility(
    visible_transition_count: Any,
    is_feasible: Any,
    constraint_violations: Any,
) -> None:
    if not isinstance(visible_transition_count, int) or isinstance(visible_transition_count, bool) or visible_transition_count < 0:
        raise ValueError("v3 model has invalid visible_transition_count")
    if not isinstance(is_feasible, bool):
        raise ValueError("v3 model is missing is_feasible")
    if not isinstance(constraint_violations, list) or any(
        not isinstance(reason, str) or reason not in V3_VIOLATIONS for reason in constraint_violations
    ):
        raise ValueError("v3 model has invalid constraint_violations")
    if len(constraint_violations) != len(set(constraint_violations)):
        raise ValueError("v3 model has duplicate constraint_violations")
    if is_feasible != (len(constraint_violations) == 0):
        raise ValueError("v3 model feasibility does not match constraint_violations")
    if (visible_transition_count == 0) != ("NO_VISIBLE_TRANSITIONS" in constraint_violations):
        raise ValueError("v3 model visibility does not match constraint_violations")
