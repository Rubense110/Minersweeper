"""Alpha Miner family catalog."""

from __future__ import annotations

from typing import Dict

from .base import MinerSpec, ParamSpec, VariantSpec


ALPHA_PARAMS: Dict[str, ParamSpec] = {
    "alpha_version": ParamSpec(
        name="alpha_version",
        ptype="enum",
        choices=["CLASSIC", "PLUS", "PLUS_PLUS", "SHARP", "ROBUST", "DOLLAR"],
        default="CLASSIC",
        prom_field="AlphaMinerParameters.version",
        optimize=False,
    ),
    # Alpha+ / Alpha++
    "ignore_length_one_loops": ParamSpec(
        name="ignore_length_one_loops",
        ptype="bool",
        default=False,
        prom_field="AlphaPlusMinerParameters.ignoreLengthOneLoops",
    ),
    # AlphaR (robust)
    "causal_threshold": ParamSpec(
        name="causal_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=None,
        prom_field="AlphaRobustMinerParameters.causalThreshold",
    ),
    "noise_threshold_least_freq": ParamSpec(
        name="noise_threshold_least_freq",
        ptype="float",
        bounds=(0.0, 1.0),
        default=None,
        prom_field="AlphaRobustMinerParameters.noiseThresholdLeastFreq",
    ),
    "noise_threshold_most_freq": ParamSpec(
        name="noise_threshold_most_freq",
        ptype="float",
        bounds=(0.0, 1.0),
        default=None,
        prom_field="AlphaRobustMinerParameters.noiseThresholdMostFreq",
    ),
    # Optional: realizable places post-filtering (if applied)
    "realizability_threshold": ParamSpec(
        name="realizability_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=None,
        prom_field="RealizablePlacesParameters.realizabilityThreshold",
        optimize=False,
    ),
    "unrealizable_traces_threshold": ParamSpec(
        name="unrealizable_traces_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=None,
        prom_field="RealizablePlacesParameters.unrealizableTracesThreshold",
        optimize=False,
    ),
}

ALPHA_VARIANTS = [
    VariantSpec("classic", "Alpha", "AlphaVersion.CLASSIC", parameters=["alpha_version"]),
    VariantSpec(
        "plus",
        "Alpha+",
        "AlphaVersion.PLUS",
        parameters=["alpha_version", "ignore_length_one_loops"],
    ),
    VariantSpec(
        "plus_plus",
        "Alpha++",
        "AlphaVersion.PLUS_PLUS",
        parameters=["alpha_version", "ignore_length_one_loops"],
    ),
    VariantSpec("sharp", "Alpha#", "AlphaVersion.SHARP", parameters=["alpha_version"]),
    VariantSpec(
        "robust",
        "AlphaR",
        "AlphaVersion.ROBUST",
        parameters=[
            "alpha_version",
            "causal_threshold",
            "noise_threshold_least_freq",
            "noise_threshold_most_freq",
        ],
    ),
    VariantSpec("dollar", "Alpha$", "AlphaVersion.DOLLAR", parameters=["alpha_version"]),
]

ALPHA_SPEC = MinerSpec(
    key="alpha",
    family="alpha",
    prom_package="org.processmining.alphaminer",
    parameters=ALPHA_PARAMS,
    variants=ALPHA_VARIANTS,
    notes="Alpha Miner family with AlphaVersion enum and robust parameters.",
)
