"""
Catalog of ProM miners and their parameter spaces.

This catalog is intended to drive a hierarchical/gated encoding where the
optimizer selects the miner (and variant) and only activates the parameters
relevant to that choice.

Sources: parameters extracted from ProM Lite packages under prom-lite-1.4-all-platforms.
"""

from __future__ import annotations

from typing import Dict, List

from .alpha import ALPHA_SPEC
from .base import MinerSpec, ParamSpec, VariantSpec
from .heuristics import HEURISTICS_SPEC
from .hybrid_ilp import HYBRID_ILP_SPEC
from .ilp import ILP_SPEC
from .inductive import INDUCTIVE_SPEC
from .split import SPLIT_SPEC

MINER_CATALOG: Dict[str, MinerSpec] = {
    spec.key: spec
    for spec in [
        ALPHA_SPEC,
        INDUCTIVE_SPEC,
        HEURISTICS_SPEC,
        SPLIT_SPEC,
        ILP_SPEC,
        HYBRID_ILP_SPEC,
    ]
}


def list_miners() -> List[str]:
    return list(MINER_CATALOG.keys())


def get_miner_spec(miner_key: str) -> MinerSpec:
    return MINER_CATALOG[miner_key]


__all__ = [
    "MinerSpec",
    "ParamSpec",
    "VariantSpec",
    "MINER_CATALOG",
    "list_miners",
    "get_miner_spec",
]
