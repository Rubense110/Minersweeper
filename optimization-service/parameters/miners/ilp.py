"""ILP Miner family catalog."""

from __future__ import annotations

from typing import Dict

from .base import MinerSpec, ParamSpec, VariantSpec


ILP_PARAMS: Dict[str, ParamSpec] = {
    "solver_type": ParamSpec(
        name="solver_type",
        ptype="enum",
        choices=["CPLEX", "JAVAILP_CPLEX", "JAVAILP_LPSOLVE"],
        default="JAVAILP_LPSOLVE",
        prom_field="ILPMinerSettings.SolverType",
        optimize=False,
    ),
    "license_dir": ParamSpec(
        name="license_dir",
        ptype="str",
        default="c:\\ILOG\\ILM",
        prom_field="ILPMinerSettings.SolverSetting.LICENSE_DIR",
        optimize=False,
    ),
    "search_type": ParamSpec(
        name="search_type",
        ptype="enum",
        choices=["BASIC", "PER_CD", "PER_TRANSITION", "PRE_PER_TRANSITION", "POST_PER_TRANSITION"],
        default="PER_CD",
        prom_field="PetriNetILPModelSettings.searchType",
    ),
    "separate_initial_places": ParamSpec(
        name="separate_initial_places",
        ptype="bool",
        default=True,
        prom_field="PetriNetILPModelSettings.separateInitialPlaces",
    ),
    "fitness": ParamSpec(
        name="fitness",
        ptype="float",
        bounds=(0.0, 1.0),
        default=0.0,
        prom_field="PetriNetVariableFitnessILPModelSettings.fitness",
    ),
}

ILP_COMMON_PARAMS = ["solver_type", "license_dir"]

ILP_VARIANTS = [
    VariantSpec(
        "petri_net",
        "Petri Net ILP",
        "PetriNetILPModel",
        parameters=ILP_COMMON_PARAMS + ["search_type", "separate_initial_places"],
    ),
    VariantSpec(
        "petri_net_variable_fitness",
        "Petri Net ILP (variable fitness)",
        "PetriNetVariableFitnessILPModel",
        parameters=ILP_COMMON_PARAMS + ["search_type", "separate_initial_places", "fitness"],
    ),
]

ILP_SPEC = MinerSpec(
    key="ilp",
    family="ilp",
    prom_package="org.processmining.plugins.ilpminer",
    parameters=ILP_PARAMS,
    variants=ILP_VARIANTS,
    notes="ILP Miner settings and PetriNet ILP model variants.",
)
