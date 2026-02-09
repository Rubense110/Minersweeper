"""Inductive Miner family catalog."""

from __future__ import annotations

from typing import Dict

from .base import MinerSpec, ParamSpec, VariantSpec


INDUCTIVE_PARAMS: Dict[str, ParamSpec] = {
    "noise_threshold": ParamSpec(
        name="noise_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.2,
        prom_field="MiningParametersAbstract.noiseThreshold",
    ),
    "is_debug": ParamSpec(
        name="is_debug",
        ptype="bool",
        default=False,
        prom_field="MiningParametersAbstract.isDebug",
        optimize=False,
    ),
    "use_multithreading": ParamSpec(
        name="use_multithreading",
        ptype="bool",
        default=True,
        prom_field="MiningParametersAbstract.isUseMultithreading",
        optimize=False,
    ),
}

INDUCTIVE_COMMON_PARAMS = ["is_debug", "use_multithreading"]
INDUCTIVE_NOISE_PARAMS = ["noise_threshold"]

INDUCTIVE_VARIANTS = [
    VariantSpec(
        "im",
        "Inductive Miner (IM)",
        "MiningParametersIM",
        parameters=list(INDUCTIVE_COMMON_PARAMS),
    ),
    VariantSpec(
        "imf",
        "Inductive Miner - infrequent (IMf)",
        "MiningParametersIMInfrequent",
        parameters=list(INDUCTIVE_COMMON_PARAMS) + INDUCTIVE_NOISE_PARAMS,
    ),
    VariantSpec(
        "imlc",
        "Inductive Miner - life cycle (IMlc)",
        "MiningParametersIMLifeCycle",
        parameters=list(INDUCTIVE_COMMON_PARAMS),
    ),
    VariantSpec(
        "imflc",
        "Inductive Miner - infrequent & life cycle (IMflc)",
        "MiningParametersIMInfrequentLifeCycle",
        parameters=list(INDUCTIVE_COMMON_PARAMS) + INDUCTIVE_NOISE_PARAMS,
    ),
    VariantSpec(
        "impt",
        "Inductive Miner - partial traces (IMpt)",
        "MiningParametersIMPartialTraces",
        parameters=list(INDUCTIVE_COMMON_PARAMS),
    ),
    VariantSpec(
        "imfpt",
        "Inductive Miner - infrequent & partial traces (IMfpt)",
        "MiningParametersIMInfrequentPartialTraces",
        parameters=list(INDUCTIVE_COMMON_PARAMS) + INDUCTIVE_NOISE_PARAMS,
    ),
    VariantSpec(
        "imfpta",
        "Inductive Miner - infrequent & partial traces Ali (IMfpta)",
        "MiningParametersIMInfrequentPartialTracesAli",
        parameters=list(INDUCTIVE_COMMON_PARAMS) + INDUCTIVE_NOISE_PARAMS,
    ),
]

INDUCTIVE_SPEC = MinerSpec(
    key="inductive",
    family="inductive",
    prom_package="org.processmining.plugins.inductiveminer2",
    parameters=INDUCTIVE_PARAMS,
    variants=INDUCTIVE_VARIANTS,
    notes="Inductive Miner v2 variants (IM, IMf, IMlc, IMflc, IMpt, IMfpt, IMfpta).",
)
