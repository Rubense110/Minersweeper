"""Heuristics Miner family catalog."""

from __future__ import annotations

from typing import Dict

from .base import MinerSpec, ParamSpec, VariantSpec


HEURISTICS_PARAMS: Dict[str, ParamSpec] = {
    "relative_to_best_threshold": ParamSpec(
        name="relative_to_best_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.05,
        prom_field="HeuristicsMinerSettings.relativeToBestThreshold",
    ),
    "positive_observation_threshold": ParamSpec(
        name="positive_observation_threshold",
        ptype="int",
        bounds=(1, 1000),
        default=1,
        prom_field="HeuristicsMinerSettings.positiveObservationThreshold",
    ),
    "dependency_threshold": ParamSpec(
        name="dependency_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.90,
        prom_field="HeuristicsMinerSettings.dependencyThreshold",
    ),
    "l1l_threshold": ParamSpec(
        name="l1l_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.90,
        prom_field="HeuristicsMinerSettings.l1lThreshold",
    ),
    "l2l_threshold": ParamSpec(
        name="l2l_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.90,
        prom_field="HeuristicsMinerSettings.l2lThreshold",
    ),
    "long_distance_threshold": ParamSpec(
        name="long_distance_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.90,
        prom_field="HeuristicsMinerSettings.longDistanceThreshold",
    ),
    "dependency_divisor": ParamSpec(
        name="dependency_divisor",
        ptype="int",
        bounds=(1, 10),
        default=1,
        prom_field="HeuristicsMinerSettings.dependencyDivisor",
    ),
    "and_threshold": ParamSpec(
        name="and_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.10,
        prom_field="HeuristicsMinerSettings.andThreshold",
    ),
    "extra_info": ParamSpec(
        name="extra_info",
        ptype="bool",
        default=False,
        prom_field="HeuristicsMinerSettings.extraInfo",
        optimize=False,
    ),
    "use_all_connected_heuristics": ParamSpec(
        name="use_all_connected_heuristics",
        ptype="bool",
        default=True,
        prom_field="HeuristicsMinerSettings.useAllConnectedHeuristics",
    ),
    "use_long_distance_dependency": ParamSpec(
        name="use_long_distance_dependency",
        ptype="bool",
        default=False,
        prom_field="HeuristicsMinerSettings.useLongDistanceDependency",
    ),
    "check_best_against_l2l": ParamSpec(
        name="check_best_against_l2l",
        ptype="bool",
        default=True,
        prom_field="HeuristicsMinerSettings.checkBestAgainstL2L",
    ),
}

HEURISTICS_PARAM_NAMES = list(HEURISTICS_PARAMS.keys())

HEURISTICS_VARIANTS = [
    VariantSpec(
        "hm",
        "Heuristics Miner",
        "HeuristicsMiner",
        parameters=list(HEURISTICS_PARAM_NAMES),
    ),
    VariantSpec(
        "fhm",
        "Flexible Heuristics Miner",
        "FlexibleHeuristicsMiner",
        parameters=list(HEURISTICS_PARAM_NAMES),
    ),
]

HEURISTICS_SPEC = MinerSpec(
    key="heuristics",
    family="heuristics",
    prom_package="org.processmining.plugins.heuristicsnet",
    parameters=HEURISTICS_PARAMS,
    variants=HEURISTICS_VARIANTS,
    notes="Heuristics Miner settings apply to both HM and Flexible HM.",
)
