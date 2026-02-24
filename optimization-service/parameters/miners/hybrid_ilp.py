"""Hybrid ILP Miner catalog."""

from __future__ import annotations

from typing import Dict

from .base import MinerSpec, ParamSpec, VariantSpec


HYBRID_ILP_PARAMS: Dict[str, ParamSpec] = {
    "lp_objective": ParamSpec(
        name="lp_objective",
        ptype="enum",
        choices=[
            "Minimize Arcs",
            "Unweighted Parikh values",
            "Weighted Parikh values, using absolute frequencies",
            "Weighted Parikh values, using relative frequencies",
        ],
        default="Minimize Arcs",
        prom_field="LPObjectiveType",
    ),
    "lp_variable_type": ParamSpec(
        name="lp_variable_type",
        ptype="enum",
        choices=[
            "Two variables per event",
            "One variable per event, two for an event which is potentially in a self loop",
            "One variable per event",
        ],
        default="Two variables per event",
        prom_field="LPVariableType",
    ),
    "lp_filter": ParamSpec(
        name="lp_filter",
        ptype="enum",
        choices=[
            "None",
            "Sequence Encoding Filter",
            "Slack Variable Filter",
        ],
        default="None",
        prom_field="LPFilterType",
    ),
    "slack_variable_filter_threshold": ParamSpec(
        name="slack_variable_filter_threshold",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.0,
        prom_field="LPFilter.SlackVariableFilter.threshold",
    ),
    "sequence_encoding_cutoff_level": ParamSpec(
        name="sequence_encoding_cutoff_level",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.0,
        prom_field="LPFilter.SequenceEncodingFilter.cutoff",
    ),
    "discovery_strategy": ParamSpec(
        name="discovery_strategy",
        ptype="enum",
        choices=[
            "Random",
            "Alpha",
            "Heuristics",
            "Fuzzy",
            "Standard",
            "Mini",
            "Midi",
            "Maxi",
            "Average",
            "Directly Follows",
        ],
        default="Random",
        prom_field="DiscoveryStrategyType",
    ),
}

HYBRID_ILP_BASE_PARAMS = [
    "lp_objective",
    "lp_variable_type",
    "lp_filter",
    "discovery_strategy",
]
HYBRID_ILP_FILTER_PARAMS = {
    "Slack Variable Filter": ["slack_variable_filter_threshold"],
    "Sequence Encoding Filter": ["sequence_encoding_cutoff_level"],
    "None": [],
}

def get_active_params_for_lp_filter(lp_filter: str) -> list[str]:
    params = list(HYBRID_ILP_BASE_PARAMS)
    params.extend(HYBRID_ILP_FILTER_PARAMS.get(lp_filter, []))
    return params

HYBRID_ILP_VARIANTS = [
    VariantSpec(
        "hybrid",
        "Hybrid ILPMiner",
        "HybridILPMiner",
        parameters=list(HYBRID_ILP_PARAMS.keys()),
    ),
]

HYBRID_ILP_SPEC = MinerSpec(
    key="hybrid_ilp",
    family="hybrid_ilp",
    prom_package="org.processmining.hybridilpminer",
    parameters=HYBRID_ILP_PARAMS,
    variants=HYBRID_ILP_VARIANTS,
    notes="LP filter thresholds are conditional on lp_filter choice.",
)
