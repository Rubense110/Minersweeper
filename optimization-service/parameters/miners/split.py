"""Split Miner family catalog.

Note: Split Miner is not present in the current ProM Lite distribution in this repo.
The parameters below are common in the Split Miner literature and should be verified
against the ProM SplitMiner package once available.
"""

from __future__ import annotations

from typing import Dict

from .base import MinerSpec, ParamSpec, VariantSpec


SPLIT_PARAMS: Dict[str, ParamSpec] = {
    "epsilon": ParamSpec(
        name="epsilon",
        ptype="float",
        bounds=(0.0, 1.0),
        default=None,
        prom_field="SplitMinerParameters.epsilon",
    ),
    "eta": ParamSpec(
        name="eta",
        ptype="float",
        bounds=(0.0, 1.0),
        default=None,
        prom_field="SplitMinerParameters.eta",
    ),
}

SPLIT_PARAM_NAMES = list(SPLIT_PARAMS.keys())

SPLIT_VARIANTS = [
    VariantSpec("sm", "Split Miner", "SplitMiner", parameters=list(SPLIT_PARAM_NAMES)),
    VariantSpec("sm2", "Split Miner 2", "SplitMiner2", parameters=list(SPLIT_PARAM_NAMES)),
]

SPLIT_SPEC = MinerSpec(
    key="split",
    family="split",
    prom_package="org.processmining.plugins.splitminer",
    parameters=SPLIT_PARAMS,
    variants=SPLIT_VARIANTS,
    notes="Split Miner not present in prom-lite; verify parameters when package is added.",
)
