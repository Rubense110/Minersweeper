"""Matrix Filter preprocessing catalog."""

from __future__ import annotations

from typing import Dict

from .base import ParamSpec, PreprocessingSpec, VariantSpec


MATRIX_FILTER_PARAMS: Dict[str, ParamSpec] = {
    "probability_of_removal_mf": ParamSpec(
        name="probability_of_removal_mf",
        ptype="float",
        bounds=(0.05, 0.25),
        default=0.15,
        prom_field="probabilityOfRemovalMF",
    ),
    "subsequence_length_mf": ParamSpec(
        name="subsequence_length_mf",
        ptype="int",
        bounds=(1, 3),
        default=2,
        prom_field="subsequenceLengthMF",
    ),
}

MATRIX_FILTER_VARIANTS = [
    VariantSpec(
        key="conditional_probabilities_mf",
        label="Conditional Probabilities (MF)",
        prom_ref="MatrixFilter.ConditionalProbabilities",
        parameters=list(MATRIX_FILTER_PARAMS.keys()),
    )
]

MATRIX_FILTER_SPEC = PreprocessingSpec(
    key="matrix_filter",
    method="Matrix Filtering",
    parameters=MATRIX_FILTER_PARAMS,
    variants=MATRIX_FILTER_VARIANTS,
    notes="Matrix-based trace repair/filtering stage.",
)
