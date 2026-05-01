"""Repair Log Filter preprocessing catalog."""

from __future__ import annotations

from typing import Dict

from .base import ParamSpec, PreprocessingSpec, VariantSpec


REPAIR_LOG_FILTER_PARAMS: Dict[str, ParamSpec] = {
    "probability_of_removal_rl": ParamSpec(
        name="probability_of_removal_rl",
        ptype="float",
        bounds=(0.05, 0.25),
        default=0.15,
        prom_field="probabilityOfRemovalRL",
    ),
    "subsequence_length_rl": ParamSpec(
        name="subsequence_length_rl",
        ptype="int",
        bounds=(1, 3),
        default=2,
        prom_field="subsequenceLengthRL",
    ),
}

REPAIR_LOG_FILTER_VARIANTS = [
    VariantSpec(
        key="repair_log_filter_rlf",
        label="Repair Log Filter (RLF)",
        prom_ref="RepairLogFilter.RLF",
        parameters=list(REPAIR_LOG_FILTER_PARAMS.keys()),
    )
]

REPAIR_LOG_FILTER_SPEC = PreprocessingSpec(
    key="repair_log_filter",
    method="Repair Log Filter",
    parameters=REPAIR_LOG_FILTER_PARAMS,
    variants=REPAIR_LOG_FILTER_VARIANTS,
    notes="Repairs inconsistent fragments before discovery.",
)
