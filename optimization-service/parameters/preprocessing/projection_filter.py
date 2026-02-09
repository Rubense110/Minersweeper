"""Projection Log Filter preprocessing catalog."""

from __future__ import annotations

from typing import Dict

from .base import ParamSpec, PreprocessingSpec, VariantSpec


PROJECTION_FILTER_PARAMS: Dict[str, ParamSpec] = {
    "keep_threshold_p": ParamSpec(
        name="keep_threshold_p",
        ptype="int",
        bounds=(0, 100),
        default=50,
        prom_field="keepThresholdP",
    ),
}

PROJECTION_FILTER_VARIANTS = [
    VariantSpec(
        key="projection_log_filter",
        label="Projection Log Filter",
        prom_ref="ProjectionFilter.Default",
        parameters=list(PROJECTION_FILTER_PARAMS.keys()),
    )
]

PROJECTION_FILTER_SPEC = PreprocessingSpec(
    key="projection_filter",
    method="Projection Log Filter",
    parameters=PROJECTION_FILTER_PARAMS,
    variants=PROJECTION_FILTER_VARIANTS,
    notes="Projects traces to retained activity subsets by threshold.",
)
