"""Catalog of preprocessing methods and their parameter spaces."""

from __future__ import annotations

from typing import Dict, List

from .base import ParamSpec, PreprocessingSpec, VariantSpec
from .matrix_filter import MATRIX_FILTER_SPEC
from .projection_filter import PROJECTION_FILTER_SPEC
from .repair_log_filter import REPAIR_LOG_FILTER_SPEC
from .variant_filter import VARIANT_FILTER_SPEC


PREPROCESSING_CATALOG: Dict[str, PreprocessingSpec] = {
    spec.key: spec
    for spec in [
        MATRIX_FILTER_SPEC,
        REPAIR_LOG_FILTER_SPEC,
        VARIANT_FILTER_SPEC,
        PROJECTION_FILTER_SPEC,
    ]
}


def list_preprocessings() -> List[str]:
    return list(PREPROCESSING_CATALOG.keys())


def get_preprocessing_spec(preprocessing_key: str) -> PreprocessingSpec:
    return PREPROCESSING_CATALOG[preprocessing_key]


__all__ = [
    "ParamSpec",
    "VariantSpec",
    "PreprocessingSpec",
    "PREPROCESSING_CATALOG",
    "list_preprocessings",
    "get_preprocessing_spec",
]
