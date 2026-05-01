"""Split Miner family catalog."""

from __future__ import annotations

from typing import Dict

from .base import MinerSpec, ParamSpec, VariantSpec


SPLIT_PARAMS: Dict[str, ParamSpec] = {
    "epsilon": ParamSpec(
        name="epsilon",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.5,
        prom_field="SplitMiner.epsilon",
    ),
    "eta": ParamSpec(
        name="eta",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.5,
        prom_field="SplitMiner.eta",
    ),
}

SPLIT_PARAM_NAMES = list(SPLIT_PARAMS.keys())

SPLIT_VARIANTS = [
    VariantSpec("sm", "Split Miner", "SplitMiner", parameters=list(SPLIT_PARAM_NAMES)),
]

SPLIT_SPEC = MinerSpec(
    key="split",
    family="split",
    prom_package="processmining.splitminer",
    parameters=SPLIT_PARAMS,
    variants=SPLIT_VARIANTS,
    notes="Split Miner 1.7.1 with minimal optimization parameters (epsilon, eta).",
)
