"""Variant Log Filter preprocessing catalog."""

from __future__ import annotations

from typing import Dict

from .base import ParamSpec, PreprocessingSpec, VariantSpec


VARIANT_FILTER_PARAMS: Dict[str, ParamSpec] = {
    "keep_threshold_vf": ParamSpec(
        name="keep_threshold_vf",
        ptype="int",
        bounds=(1, 100),
        default=50,
        prom_field="keepThresholdVF",
    ),
}

VARIANT_FILTER_VARIANTS = [
    VariantSpec(
        key="variant_log_filter",
        label="Variant Log Filter",
        prom_ref="VariantFilter.Default",
        parameters=list(VARIANT_FILTER_PARAMS.keys()),
    )
]

VARIANT_FILTER_SPEC = PreprocessingSpec(
    key="variant_filter",
    method="Variant Log Filter",
    parameters=VARIANT_FILTER_PARAMS,
    variants=VARIANT_FILTER_VARIANTS,
    notes="LogFiltering variant coverage percentage; effective minimum is log-dependent and repaired before evaluation.",
)
