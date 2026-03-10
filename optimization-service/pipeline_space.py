"""Decision-space builder and decoder for pipeline optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from parameters.miners import MINER_CATALOG
from parameters.miners.hybrid_ilp import get_active_params_for_lp_filter
from parameters.preprocessing import PREPROCESSING_CATALOG
from preprocessing_constraints import adjusted_bounds


@dataclass(frozen=True)
class DecisionVariable:
    key: str
    ptype: str
    min_val: float
    max_val: float
    choices: Optional[List[str]] = None


class PipelineSearchSpace:
    """Builds a flat float search space and decodes it into pipeline configs."""

    def __init__(self, excluded_miners: Optional[Sequence[str]] = None, log_path: Optional[str] = None):
        excluded = set(excluded_miners or [])
        self.log_path = log_path

        self.preprocessing_keys = list(PREPROCESSING_CATALOG.keys())
        self.miner_keys = [key for key in MINER_CATALOG.keys() if key not in excluded]
        if not self.preprocessing_keys:
            raise ValueError("Preprocessing catalog is empty")
        if not self.miner_keys:
            raise ValueError("Miner catalog is empty after exclusions")

        self.variables: List[DecisionVariable] = []
        self.index_by_key: Dict[str, int] = {}
        self._build()

    def _add_variable(
        self,
        key: str,
        ptype: str,
        min_val: float,
        max_val: float,
        choices: Optional[List[str]] = None,
    ) -> None:
        self.index_by_key[key] = len(self.variables)
        self.variables.append(
            DecisionVariable(
                key=key,
                ptype=ptype,
                min_val=min_val,
                max_val=max_val,
                choices=choices,
            )
        )

    def _bounds_for_param(self, ptype: str, bounds: Optional[Tuple[float, float]], choices: Optional[List[str]]) -> Tuple[float, float]:
        if ptype == "float":
            return bounds if bounds is not None else (0.0, 1.0)
        if ptype == "int":
            if bounds is None:
                raise ValueError("Integer parameter requires bounds")
            return float(bounds[0]), float(bounds[1])
        if ptype == "bool":
            return 0.0, 1.0
        if ptype == "enum":
            if not choices:
                raise ValueError("Enum parameter requires choices")
            return 0.0, float(len(choices) - 1)
        raise ValueError(f"Unsupported optimizable parameter type: {ptype}")

    def _build(self) -> None:
        self._add_variable(
            key="preprocessing::selected",
            ptype="enum",
            min_val=0.0,
            max_val=float(len(self.preprocessing_keys) - 1),
            choices=self.preprocessing_keys,
        )

        # Pasos del preprocesado
        for prep_key in self.preprocessing_keys:
            prep_spec = PREPROCESSING_CATALOG[prep_key]

            # Si tiene variantes añade gen de variantes (Ninguno tiene)
            if len(prep_spec.variants) > 1:
                variant_choices = [variant.key for variant in prep_spec.variants]
                self._add_variable(
                    key=f"preprocessing::{prep_key}::variant",
                    ptype="enum",
                    min_val=0.0,
                    max_val=float(len(variant_choices) - 1),
                    choices=variant_choices,
                )
            # Genes para los parámetros del preprocesado (para cada uno)
            for param_name, param_spec in prep_spec.parameters.items():
                if not param_spec.optimize:
                    continue
                bounds = adjusted_bounds(prep_key, param_name, param_spec.bounds, self.log_path)
                min_val, max_val = self._bounds_for_param(param_spec.ptype, bounds, param_spec.choices)
                self._add_variable(
                    key=f"preprocessing::{prep_key}::param::{param_name}",
                    ptype=param_spec.ptype,
                    min_val=min_val,
                    max_val=max_val,
                    choices=param_spec.choices,
                )

        # Gen del minero elegido. Siempre presente
        self._add_variable(
            key="miner::selected",
            ptype="enum",
            min_val=0.0,
            max_val=float(len(self.miner_keys) - 1),
            choices=self.miner_keys,
        )

        # Para cada minero añadimos los genes de sus variantes
        for miner_key in self.miner_keys:
            miner_spec = MINER_CATALOG[miner_key]
            variant_choices = [variant.key for variant in miner_spec.variants]
            self._add_variable(
                key=f"miner::{miner_key}::variant",
                ptype="enum",
                min_val=0.0,
                max_val=float(len(variant_choices) - 1),
                choices=variant_choices,
            )

            # Genes para los parámetros
            for param_name, param_spec in miner_spec.parameters.items():
                if not param_spec.optimize:
                    continue
                if param_spec.ptype == "str":
                    continue
                low, high = self._bounds_for_param(param_spec.ptype, param_spec.bounds, param_spec.choices)
                self._add_variable(
                    key=f"miner::{miner_key}::param::{param_name}",
                    ptype=param_spec.ptype,
                    min_val=low,
                    max_val=high,
                    choices=param_spec.choices,
                )

    def lower_bounds(self) -> List[float]:
        return [var.min_val for var in self.variables]

    def upper_bounds(self) -> List[float]:
        return [var.max_val for var in self.variables]

    def _get_raw(self, values: Sequence[float], key: str) -> float:
        return values[self.index_by_key[key]]

    def _decode_value(self, raw: float, ptype: str, bounds: Optional[Tuple[float, float]], choices: Optional[List[str]]) -> Any:
        if ptype == "float":
            low, high = bounds if bounds is not None else (0.0, 1.0)
            return float(min(max(raw, low), high))
        if ptype == "int":
            if bounds is None:
                raise ValueError("Integer parameter requires bounds")
            low, high = int(bounds[0]), int(bounds[1])
            return int(min(max(round(raw), low), high))
        if ptype == "bool":
            return raw >= 0.5
        if ptype == "enum":
            if not choices:
                raise ValueError("Enum parameter requires choices")
            idx = int(min(max(round(raw), 0), len(choices) - 1))
            return choices[idx]
        if ptype == "str":
            return str(raw)
        raise ValueError(f"Unsupported parameter type: {ptype}")

    def _decode_preprocessing(self, values: Sequence[float]) -> Dict[str, Any]:
        selected_key = self._decode_value(
            raw=self._get_raw(values, "preprocessing::selected"),
            ptype="enum",
            bounds=None,
            choices=self.preprocessing_keys,
        )
        prep_spec = PREPROCESSING_CATALOG[selected_key]

        if len(prep_spec.variants) > 1:
            variant_key = self._decode_value(
                raw=self._get_raw(values, f"preprocessing::{selected_key}::variant"),
                ptype="enum",
                bounds=None,
                choices=[variant.key for variant in prep_spec.variants],
            )
            variant = next(item for item in prep_spec.variants if item.key == variant_key)
        else:
            variant = prep_spec.variants[0]

        active_param_names = variant.parameters if variant.parameters else list(prep_spec.parameters.keys())
        params: Dict[str, Any] = {}
        for name in active_param_names:
            spec = prep_spec.parameters[name]
            if spec.optimize:
                raw = self._get_raw(values, f"preprocessing::{selected_key}::param::{name}")
                params[name] = self._decode_value(raw, spec.ptype, spec.bounds, spec.choices)
            else:
                params[name] = spec.default

        return {
            "key": selected_key,
            "method": prep_spec.method,
            "variant": variant.label,
            "parameters": params,
        }

    def _decode_miner(self, values: Sequence[float]) -> Dict[str, Any]:
        selected_key = self._decode_value(
            raw=self._get_raw(values, "miner::selected"),
            ptype="enum",
            bounds=None,
            choices=self.miner_keys,
        )
        miner_spec = MINER_CATALOG[selected_key]

        variant_key = self._decode_value(
            raw=self._get_raw(values, f"miner::{selected_key}::variant"),
            ptype="enum",
            bounds=None,
            choices=[variant.key for variant in miner_spec.variants],
        )
        variant = next(item for item in miner_spec.variants if item.key == variant_key)

        active_param_names = variant.parameters if variant.parameters else list(miner_spec.parameters.keys())
        params: Dict[str, Any] = {}
        for name in active_param_names:
            spec = miner_spec.parameters[name]
            if spec.optimize and spec.ptype != "str":
                raw = self._get_raw(values, f"miner::{selected_key}::param::{name}")
                params[name] = self._decode_value(raw, spec.ptype, spec.bounds, spec.choices)
            else:
                params[name] = spec.default

        # Conditional parameters for Hybrid ILP based on selected filter type.
        if selected_key == "hybrid_ilp" and "lp_filter" in params:
            active_for_filter = set(get_active_params_for_lp_filter(params["lp_filter"]))
            params = {name: value for name, value in params.items() if name in active_for_filter}

        return {
            "key": selected_key,
            "family": miner_spec.family,
            "variant": variant.label,
            "parameters": params,
        }

    def decode(self, values: Sequence[float]) -> Dict[str, Any]:
        return {
            "preprocessing": self._decode_preprocessing(values),
            "miner": self._decode_miner(values),
        }
